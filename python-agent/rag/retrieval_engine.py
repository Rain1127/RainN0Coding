"""
多路检索引擎 —— 意图定向 + 全局向量双通道并行

架构:
  输入 (RetrievalContext)
    ├── 通道 A: IntentDirectedRetriever (意图定向 → 特定 Collection)
    ├── 通道 B: GlobalVectorRetriever  (全局向量 → 全部 Collection)
    └── 后处理: PostProcessor (去重 → 重排序 → 格式化)

通道选择策略:
  - code + retry=0  → 双通道全开
  - code + retry>0  → 仅通道 A
  - pm / arch        → 仅通道 B
  - review / 其他    → 仅通道 A
"""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from rag.embedding_service import embedding_service
from rag.milvus_client import milvus_store
from rag.rag_cache import rag_cache
from rag.retrieval_common import PostProcessor, RetrievalContext, RetrievalResult
from config import config, get_lang_config


# ============ 通道 A: 意图定向检索 ============

class IntentDirectedRetriever:
    """根据 phase 路由到特定 Collection，精准检索 路由表是硬编码的"""

    ROUTE_TABLE: dict[str, list[dict]] = {
        "code": [
            {"collection": "component_library", "top_k": 5},
            {"collection": "framework_api", "top_k": 5},
            {"collection": "code_store", "top_k": 3},
        ],
        "arch": [
            {"collection": "design_pattern", "top_k": 5},
            {"collection": "component_library", "top_k": 5},
        ],
        "pm": [
            {"collection": "code_store", "top_k": 5},
            {"collection": "design_pattern", "top_k": 3},
        ],
        "review": [
            {"collection": "error_pattern", "top_k": 5},
            {"collection": "framework_api", "top_k": 3},
        ],
    }

    def _build_query_text(self, ctx: RetrievalContext, target_collection: str) -> str:
        """针对不同 Collection 构造定向查询文本"""
        parts = [ctx.user_request]

        arch = ctx.architecture or {}
        tech_stack = arch.get("tech_stack", {})
        lang_cfg = get_lang_config(ctx.code_gen_type)
        framework = tech_stack.get("framework") or lang_cfg.get("framework", "Vue 3")

        if target_collection == "component_library":
            parts.append(f"framework:{framework}")
            if ctx.file_info:
                parts.append(ctx.file_info.get("description", ""))
        elif target_collection == "framework_api":
            parts.append(f"{framework} composition api typescript")
            if ctx.file_info:
                parts.append(ctx.file_info.get("description", ""))
        elif target_collection == "code_store":
            if ctx.file_info:
                parts.append(ctx.file_info.get("path", ""))
                parts.append(ctx.file_info.get("description", ""))
        elif target_collection == "design_pattern":
            if arch:
                features = arch.get("component_tree", [])
                if features:
                    parts.append(str(features)[:500])
        elif target_collection == "error_pattern":
            if ctx.file_info:
                parts.append(ctx.file_info.get("description", ""))

        return " ".join(parts)

    def retrieve(self, ctx: RetrievalContext) -> list[RetrievalResult]:
        routes = self.ROUTE_TABLE.get(ctx.phase, [{"collection": "code_store", "top_k": 5}])
        results: list[RetrievalResult] = []

        # 准备并行查询
        queries = []
        for route in routes:
            col = route["collection"]
            top_k = route.get("top_k", 5)
            query_text = self._build_query_text(ctx, col)
            try:
                query_vector = embedding_service.embed(query_text)
            except Exception:
                continue
            queries.append((col, query_vector, top_k))

        if not queries:
            return []

        # 并行执行
        raw_results = milvus_store.search_multi(queries)

        for query, hits in zip(queries, raw_results):
            col = query[0]
            for hit in hits:
                entity = hit.get("entity", {})
                content = self._extract_content(col, entity)
                if not content:
                    continue
                results.append(RetrievalResult(
                    content=content,
                    source_collection=col,
                    source_channel="intent_directed",
                    score=hit.get("distance", 0.0),
                    metadata={k: v for k, v in entity.items()},
                ))

        return results

    def _extract_content(self, collection: str, entity: dict) -> str:
        """从 Milvus entity 中提取可用文本内容"""
        if collection == "component_library":
            name = entity.get("component_name", "")
            snippet = entity.get("code_snippet", "")
            return f"组件 {name}\n{snippet}" if snippet else ""
        elif collection == "code_store":
            path = entity.get("file_path", "")
            code = entity.get("content", "")
            return f"文件 {path}\n{code}" if code else ""
        elif collection == "design_pattern":
            name = entity.get("pattern_name", "")
            desc = entity.get("description", "")
            example = entity.get("example_code", "")
            return f"模式 {name}: {desc}\n{example}" if name else ""
        elif collection == "error_pattern":
            sig = entity.get("error_signature", "")
            fix = entity.get("fix_code", "")
            return f"错误 {sig}\n修复 {fix}" if sig else ""
        elif collection == "framework_api":
            api = entity.get("api_name", "")
            sig = entity.get("signature", "")
            example = entity.get("example", "")
            return f"API {api}: {sig}\n{example}" if api else ""
        return ""


# ============ 通道 B: 全局向量检索 ============

class GlobalVectorRetriever:
    """全 Collection 并行语义检索，覆盖盲区"""

    ALL_COLLECTIONS = [
        "code_store", "component_library", "design_pattern",
        "error_pattern", "framework_api",
    ]

    def _build_query_text(self, ctx: RetrievalContext) -> str:
        parts = [ctx.user_request]
        if ctx.file_info:
            parts.append(ctx.file_info.get("description", ""))
            parts.append(ctx.file_info.get("path", ""))
        parts.append(f"phase:{ctx.phase}")
        return " ".join(p for p in parts if p)

    def retrieve(self, ctx: RetrievalContext) -> list[RetrievalResult]:
        query_text = self._build_query_text(ctx)
        try:
            query_vector = embedding_service.embed(query_text)
        except Exception:
            return []

        # 构造并行查询
        queries = [(col, query_vector, 5) for col in self.ALL_COLLECTIONS]
        raw_results = milvus_store.search_multi(queries)

        results: list[RetrievalResult] = []
        for query, hits in zip(queries, raw_results):
            col = query[0]
            for hit in hits:
                entity = hit.get("entity", {})
                content = self._extract_content(col, entity)
                if not content:
                    continue
                results.append(RetrievalResult(
                    content=content,
                    source_collection=col,
                    source_channel="global_vector",
                    score=hit.get("distance", 0.0),
                    metadata={k: v for k, v in entity.items()},
                ))
        return results

    def _extract_content(self, collection: str, entity: dict) -> str:
        """同 IntentDirectedRetriever._extract_content"""
        if collection == "component_library":
            name = entity.get("component_name", "")
            snippet = entity.get("code_snippet", "")
            return f"组件 {name}\n{snippet}" if snippet else ""
        elif collection == "code_store":
            path = entity.get("file_path", "")
            code = entity.get("content", "")
            return f"文件 {path}\n{code}" if code else ""
        elif collection == "design_pattern":
            name = entity.get("pattern_name", "")
            desc = entity.get("description", "")
            example = entity.get("example_code", "")
            return f"模式 {name}: {desc}\n{example}" if name else ""
        elif collection == "error_pattern":
            sig = entity.get("error_signature", "")
            fix = entity.get("fix_code", "")
            return f"错误 {sig}\n修复 {fix}" if sig else ""
        elif collection == "framework_api":
            api = entity.get("api_name", "")
            sig = entity.get("signature", "")
            example = entity.get("example", "")
            return f"API {api}: {sig}\n{example}" if api else ""
        return ""


# ============ 检索引擎门面 ============

class RetrievalEngine:
    """多路检索引擎 —— 统一入口"""

    def __init__(self):
        self.channel_a = IntentDirectedRetriever()
        self.channel_b = GlobalVectorRetriever()
        self.postprocessor = PostProcessor()

    def select_channels(self, phase: str, retry_count: int) -> dict[str, bool]:
        """动态通道选择"""
        if phase == "code" and retry_count == 0:
            return {"intent_directed": True, "global_vector": True}
        if phase == "code" and retry_count > 0:
            return {"intent_directed": True, "global_vector": False}
        if phase in ("pm", "arch"):
            return {"intent_directed": False, "global_vector": True}
        return {"intent_directed": True, "global_vector": False}

    def retrieve(self, ctx: RetrievalContext) -> str:
        """执行检索，返回格式化 Prompt 文本。

        每个通道独立缓存：rag_cache:{version}:{phase}:{channel}:{query_md5}
        """
        channels = self.select_channels(ctx.phase, ctx.retry_count)
        all_results: list[RetrievalResult] = []

        # 双通道检索（使用 ThreadPoolExecutor 并行）
        futures = {}
        _cache_meta: dict = {}  # future → (channel_name, query_text)
        phase = ctx.phase

        lang_cfg = get_lang_config(ctx.code_gen_type)
        framework = lang_cfg.get("framework", "")

        with ThreadPoolExecutor(max_workers=2) as ex:
            if channels["intent_directed"]:
                ia_query = ctx.user_request + str(ctx.file_info or "") + framework
                ia_cached = rag_cache.get(phase, "intent_directed", ia_query)
                if ia_cached is not None:
                    ia_results = self._deserialize_results(ia_cached)
                    if ia_results:
                        print(f"[RetrievalEngine] cache HIT intent_directed: {len(ia_results)} 条")
                        all_results.extend(ia_results)
                else:
                    f = ex.submit(self.channel_a.retrieve, ctx)
                    futures[f] = "A"
                    _cache_meta[f] = ("intent_directed", ia_query)

            if channels["global_vector"]:
                gv_query = ctx.user_request + str(ctx.file_info or "") + phase
                gv_cached = rag_cache.get(phase, "global_vector", gv_query)
                if gv_cached is not None:
                    gv_results = self._deserialize_results(gv_cached)
                    if gv_results:
                        print(f"[RetrievalEngine] cache HIT global_vector: {len(gv_results)} 条")
                        all_results.extend(gv_results)
                else:
                    f = ex.submit(self.channel_b.retrieve, ctx)
                    futures[f] = "B"
                    _cache_meta[f] = ("global_vector", gv_query)

            for f in as_completed(futures):
                channel_name = futures[f]
                try:
                    channel_results = f.result()
                    print(f"[RetrievalEngine] 通道 {channel_name}: {len(channel_results)} 条结果")
                    all_results.extend(channel_results)
                    # 回写缓存
                    meta = _cache_meta.get(f)
                    if meta and channel_results:
                        ch, query_text = meta
                        serialized = self._serialize_results(channel_results)
                        rag_cache.set(phase, ch, query_text, serialized)
                except Exception as e:
                    print(f"[RetrievalEngine] 通道 {channel_name} 失败: {e}")

        if not all_results:
            return ""

        # === 反馈追踪 (P2)：记录检索到的 code_store 条目 ===
        if ctx.app_id:
            try:
                from rag.feedback_tracker import feedback_tracker
                for r in all_results:
                    if r.source_collection == "code_store":
                        rag_app_id = r.metadata.get("app_id", "")
                        rag_file_path = r.metadata.get("file_path", "")
                        if rag_app_id and rag_file_path:
                            feedback_tracker.record_to_session(
                                ctx.app_id, rag_app_id, rag_file_path)
            except Exception:
                pass  # 反馈追踪失败不影响检索

        # 后处理流水线
        deduped = self.postprocessor.dedup(all_results)
        print(f"[RetrievalEngine] 去重: {len(all_results)} → {len(deduped)}")

        # RAGAS 在线评估（轻量，不调 LLM）
        try:
            from rag.ragas_evaluator import evaluate_online
            ragas_metrics = evaluate_online(deduped)
            print(f"[RetrievalEngine] RAGAS: precision={ragas_metrics.context_precision:.0%}, "
                  f"hit_rate={ragas_metrics.context_hit_rate:.0%}, "
                  f"avg_score={ragas_metrics.avg_retrieval_score:.2f}")
        except Exception:
            ragas_metrics = None

        ranked = self.postprocessor.rerank(deduped)
        print(f"[RetrievalEngine] 重排序: top {len(ranked)}")

        formatted = self.postprocessor.format(ranked)
        return formatted


    # ========== 缓存序列化 ==========

    @staticmethod
    def _serialize_results(results: list[RetrievalResult]) -> str:
        """将 RetrievalResult 列表序列化为 JSON（不含 vector 字段）。"""
        items = []
        for r in results:
            items.append({
                "content": r.content,
                "source_collection": r.source_collection,
                "source_channel": r.source_channel,
                "score": r.score,
                "metadata": r.metadata,
            })
        return json.dumps(items, ensure_ascii=False)

    @staticmethod
    def _deserialize_results(json_str: str) -> list[RetrievalResult] | None:
        """从 JSON 反序列化为 RetrievalResult 列表。"""
        try:
            items = json.loads(json_str)
        except json.JSONDecodeError:
            return None
        results = []
        for item in items:
            results.append(RetrievalResult(
                content=item.get("content", ""),
                source_collection=item.get("source_collection", ""),
                source_channel=item.get("source_channel", ""),
                score=item.get("score", 0.0),
                metadata=item.get("metadata", {}),
            ))
        return results


# 全局单例
retrieval_engine = RetrievalEngine()
