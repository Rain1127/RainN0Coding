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
import hashlib
import json
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

from rag.embedding_service import embedding_service
from rag.milvus_client import milvus_store
from rag.rag_cache import rag_cache
from config import config, get_lang_config


# ============ 数据模型 ============

@dataclass
class RetrievalResult:
    """单条检索结果"""
    content: str
    source_collection: str
    source_channel: str          # "intent_directed" | "global_vector"
    score: float                 # 语义相似度 (Cosine distance, 0~1)
    metadata: dict = field(default_factory=dict)
    vector: list[float] | None = None  # 原始向量，用于语义去重

    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


@dataclass
class RetrievalContext:
    """检索上下文"""
    phase: str                   # pm | arch | code | review
    user_request: str
    file_info: dict | None = None
    architecture: dict | None = None
    retry_count: int = 0
    code_gen_type: str = "vue_project"  # 用于框架感知的 query 改写
    app_id: str = ""             # 当前应用 ID，用于反馈追踪 (P2)


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


# ============ 后处理流水线 ============

class PostProcessor:
    """去重 → 重排序 → 格式化"""

    def __init__(self):
        self.top_k = config.RAG_TOP_K
        self.semantic_threshold = config.RAG_SEMANTIC_DEDUP_THRESHOLD

    # ---- 去重 ----

    def dedup(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """三步去重：内容哈希 + 语义相似度 + 来源去重"""
        if len(results) <= 1:
            return results

        # Step 1: 精确哈希去重（按 score 降序排列，保留 score 高者）
        seen_hashes: set[str] = set()
        hash_deduped: list[RetrievalResult] = []
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        for r in sorted_results:
            h = r.content_hash()
            if h not in seen_hashes:
                seen_hashes.add(h)
                hash_deduped.append(r)

        # Step 2: 来源去重（同 collection + 同 name/path → 保留 score 高者）
        if len(hash_deduped) <= 1:
            return hash_deduped
        return self._source_dedup(hash_deduped)

    def _semantic_dedup(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """基于向量的语义去重"""
        keep: list[RetrievalResult] = []
        discarded: set[int] = set()
        for i, r1 in enumerate(results):
            if i in discarded:
                continue
            keep.append(r1)
            for j, r2 in enumerate(results):
                if j <= i or j in discarded:
                    continue
                sim = self._cosine_similarity(r1.vector, r2.vector)
                if sim > self.semantic_threshold:
                    discarded.add(j)
        return keep

    def _source_dedup(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """同 Collection 内去重（同名组件/文件保留 score 高者）"""
        seen: dict[str, RetrievalResult] = {}
        for r in sorted(results, key=lambda x: x.score, reverse=True):
            key = self._source_key(r)
            if key and key in seen:
                if r.score > seen[key].score:
                    seen[key] = r
            elif key:
                seen[key] = r
            else:
                # 无法确定来源 key 的结果保留
                seen[f"__{id(r)}"] = r
        return sorted(seen.values(), key=lambda x: x.score, reverse=True)

    def _source_key(self, r: RetrievalResult) -> str:
        """生成来源唯一键"""
        meta = r.metadata
        col = r.source_collection
        if col == "component_library":
            return f"{col}:{meta.get('component_name', '')}"
        elif col == "code_store":
            return f"{col}:{meta.get('file_path', '')}"
        elif col == "design_pattern":
            return f"{col}:{meta.get('pattern_name', '')}"
        elif col == "error_pattern":
            return f"{col}:{meta.get('error_signature', '')}"
        elif col == "framework_api":
            return f"{col}:{meta.get('api_name', '')}"
        return ""

    @staticmethod
    def _cosine_similarity(v1: list[float] | None, v2: list[float] | None) -> float:
        """计算两个向量的 Cosine 相似度"""
        if v1 is None or v2 is None or len(v1) != len(v2):
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    # ---- 重排序 ----

    def rerank(self, results: list[RetrievalResult],
               query_vector: list[float] | None = None) -> list[RetrievalResult]:
        """四因子加权重排序"""
        for r in results:
            semantic_score = r.score  # Milvus 返回的 Cosine 距离 (0~1)
            source_score = 1.0 if r.source_channel == "intent_directed" else 0.6
            success_score = self._success_score(r)
            freshness_score = 0.5  # 暂用固定值（Collection 无 created_at 字段）

            r.score = (
                0.40 * semantic_score +
                0.25 * source_score +
                0.20 * success_score +
                0.15 * freshness_score
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:self.top_k]

    def _success_score(self, r: RetrievalResult) -> float:
        """提取成功记录因子（P2：code_store 使用反馈追踪的真实质量分）"""
        meta = r.metadata
        col = r.source_collection
        if col == "code_store":
            # 尝试从反馈追踪器读取真实质量分
            rag_app_id = meta.get("app_id", "")
            rag_file_path = meta.get("file_path", "")
            if rag_app_id and rag_file_path:
                try:
                    from rag.feedback_tracker import feedback_tracker
                    score = feedback_tracker.get_quality_score(rag_app_id, rag_file_path)
                    if score is not None:
                        return score / 100.0
                except Exception:
                    pass
            return 0.7  # 回退默认值（无质量记录时假设为中等质量）
        elif col == "error_pattern":
            count = meta.get("occurrence_count", 1)
            return min(float(count) / 10.0, 1.0)  # 出现次数越多越值得参考
        elif col == "component_library":
            use_count = meta.get("use_count", 1)
            return min(float(use_count) / 20.0, 1.0)
        return 0.5

    # ---- 格式化 ----

    def format(self, ranked_results: list[RetrievalResult]) -> str:
        """分类封装为 Prompt 注入块"""
        if not ranked_results:
            return ""

        blocks: dict[str, list[str]] = {
            "component": [],
            "api": [],
            "error": [],
            "code": [],
            "pattern": [],
        }

        coll_to_type = {
            "component_library": "component",
            "framework_api": "api",
            "error_pattern": "error",
            "code_store": "code",
            "design_pattern": "pattern",
        }

        for r in ranked_results:
            rtype = coll_to_type.get(r.source_collection, "code")
            blocks[rtype].append(r.content[:800])  # 截断长文本

        sections: list[str] = []

        if blocks["component"]:
            sections.append(
                "## 可用组件白名单（优先使用，禁止编造）\n\n"
                + "\n---\n".join(blocks["component"])
            )
        if blocks["api"]:
            sections.append(
                "## 框架 API 约束清单（只能使用以下 API）\n\n"
                + "\n---\n".join(blocks["api"])
            )
        if blocks["error"]:
            sections.append(
                "## 常见错误预防（避免重复以下错误）\n\n"
                + "\n---\n".join(blocks["error"])
            )
        if blocks["code"]:
            sections.append(
                "## 参考实现（已验证可构建的代码）\n\n"
                + "\n---\n".join(blocks["code"])
            )
        if blocks["pattern"]:
            sections.append(
                "## 推荐设计模式\n\n"
                + "\n---\n".join(blocks["pattern"])
            )

        if not sections:
            return ""

        return (
            "## 可复用资源（来自 RAG 多路检索 —— 优先使用，避免造轮子）\n\n"
            + "\n\n".join(sections)
        )


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
