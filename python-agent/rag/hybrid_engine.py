"""
混合检索引擎 —— grep 精确匹配 + Milvus 语义检索

并行检索路线：
  Grep 通道: SQLite FTS5 (framework_api / error_pattern / component_library)
             + ripgrep (code_store 文件系统)
  Semantic 通道: Milvus (design_pattern + component_library)

用法：
    engine = HybridEngine()
    ctx = RetrievalContext(phase="code", user_request="写一个用户管理接口", ...)
    prompt_text = engine.retrieve(ctx)
"""

import os
import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from rag.sqlite_store import sqlite_store
from rag.code_grep import code_grep
from rag.rag_cache import rag_cache
from config import config, get_lang_config

# 延迟导入 Milvus 相关模块，确保 grep 通道在无 pymilvus 时也能工作
_retrieval_result: type | None = None
_post_processor: type | None = None
_retrieval_context: type | None = None
_semantic_retriever = None


def _lazy_import_rag():
    global _retrieval_result, _post_processor, _retrieval_context, _semantic_retriever
    if _retrieval_result is None:
        try:
            from rag.retrieval_engine import RetrievalResult, PostProcessor, RetrievalContext
            _retrieval_result = RetrievalResult
            _post_processor = PostProcessor
            _retrieval_context = RetrievalContext
        except ImportError:
            # 降级：定义最小数据类
            from dataclasses import dataclass, field

            @dataclass
            class _RetrievalResult:
                content: str
                source_collection: str
                source_channel: str
                score: float
                metadata: dict = field(default_factory=dict)

            _retrieval_result = _RetrievalResult
            _post_processor = _MinimalPostProcessor
            _retrieval_context = None

    if _semantic_retriever is None:
        try:
            from rag.semantic_engine import semantic_retriever as sr
            _semantic_retriever = sr
        except ImportError:
            _semantic_retriever = None


class _MinimalPostProcessor:
    """降级后处理：无 Milvus 时的最小实现"""
    def dedup(self, results):
        seen = set()
        unique = []
        for r in results:
            h = hash(r.content)
            if h not in seen:
                seen.add(h)
                unique.append(r)
        return unique

    def rerank(self, results):
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:8]

    def format(self, results):
        if not results:
            return ""
        blocks = []
        for r in results:
            blocks.append(r.content[:800])
        return "## 可复用资源\n\n" + "\n---\n".join(blocks)


class HybridEngine:
    """混合检索引擎门面 —— 三段并行：SQLite + ripgrep + Milvus"""

    # 每阶段的检索路由
    PHASE_ROUTE = {
        "code": {
            "grep": {"framework_api", "component_library", "code_store"},
            "semantic": True,
        },
        "arch": {
            "grep": {"component_library"},
            "semantic": True,
        },
        "pm": {
            "grep": {"code_store"},
            "semantic": True,
        },
        "review": {
            "grep": {"error_pattern", "framework_api"},
            "semantic": False,
        },
    }

    def __init__(self):
        _lazy_import_rag()
        self._postprocessor = _post_processor() if _post_processor else _MinimalPostProcessor()
        self._sqlite_ready = False

    def _ensure_sqlite(self):
        """延迟初始化 SQLite (等待种子数据就绪)"""
        if not self._sqlite_ready:
            sqlite_store.connect()
            sqlite_store.init_tables()
            self._sqlite_ready = True

    def retrieve(self, ctx) -> str:
        """
        混合检索入口 —— 与 RetrievalEngine.retrieve() 签名完全一致。

        每个子通道独立缓存：rag_cache:{version}:{phase}:{channel}:{query_md5}

        Args:
            ctx: RetrievalContext (复用现有数据模型)

        Returns:
            格式化后的 Prompt 注入文本
        """
        route = self.PHASE_ROUTE.get(ctx.phase, {"grep": set(), "semantic": False})
        grep_cols = route["grep"]
        use_semantic = route["semantic"]

        # 重试时关闭语义通道（与原逻辑一致）
        if ctx.retry_count > 0 and ctx.phase == "code":
            use_semantic = False

        all_results: list = []
        futures = {}
        _cache_meta: dict = {}  # future → (channel_name, query_text)

        # 提取共用的搜索关键词
        keywords = self._extract_keywords(ctx)
        phase = ctx.phase

        with ThreadPoolExecutor(max_workers=3) as ex:
            # === Grep 通道：SQLite FTS5 ===
            if "framework_api" in grep_cols:
                lang_cfg = get_lang_config(ctx.code_gen_type)
                fw_keywords = keywords + self._framework_tokens(
                    lang_cfg.get("framework", ""))
                fa_query = " ".join(fw_keywords)
                fa_cached = rag_cache.get(phase, "grep_fa", fa_query)
                if fa_cached is not None:
                    fa_results = self._deserialize_results(fa_cached, "grep:framework_api")
                    if fa_results:
                        print(f"[HybridEngine] cache HIT grep_fa: {len(fa_results)} 条")
                        all_results.extend(fa_results)
                else:
                    f = ex.submit(self._grep_framework_api, keywords, ctx)
                    futures[f] = "grep:framework_api"
                    _cache_meta[f] = ("grep_fa", fa_query)

            if "component_library" in grep_cols:
                lang_cfg = get_lang_config(ctx.code_gen_type)
                fw_keywords = keywords + self._framework_tokens(
                    lang_cfg.get("framework", ""))
                cl_query = " ".join(fw_keywords)
                cl_cached = rag_cache.get(phase, "grep_cl", cl_query)
                if cl_cached is not None:
                    cl_results = self._deserialize_results(cl_cached, "grep:component_library")
                    if cl_results:
                        print(f"[HybridEngine] cache HIT grep_cl: {len(cl_results)} 条")
                        all_results.extend(cl_results)
                else:
                    f = ex.submit(self._grep_component, keywords, ctx)
                    futures[f] = "grep:component_library"
                    _cache_meta[f] = ("grep_cl", cl_query)

            if "error_pattern" in grep_cols:
                error_text = self._extract_error_text(ctx)
                ep_cached = rag_cache.get(phase, "grep_ep", error_text) if error_text else None
                if ep_cached is not None:
                    ep_results = self._deserialize_results(ep_cached, "grep:error_pattern")
                    if ep_results:
                        print(f"[HybridEngine] cache HIT grep_ep: {len(ep_results)} 条")
                        all_results.extend(ep_results)
                elif error_text:
                    f = ex.submit(self._grep_error, error_text)
                    futures[f] = "grep:error_pattern"
                    _cache_meta[f] = ("grep_ep", error_text)

            if "code_store" in grep_cols:
                cs_query = " ".join(keywords[:3])
                cs_cached = rag_cache.get(phase, "grep_cs", cs_query)
                if cs_cached is not None:
                    cs_results = self._deserialize_results(cs_cached, "grep:code_store")
                    if cs_results:
                        print(f"[HybridEngine] cache HIT grep_cs: {len(cs_results)} 条")
                        all_results.extend(cs_results)
                else:
                    f = ex.submit(self._grep_code_store, keywords, ctx)
                    futures[f] = "grep:code_store"
                    _cache_meta[f] = ("grep_cs", cs_query)

            # === Semantic 通道：Milvus ===
            if use_semantic and _semantic_retriever is not None:
                sem_query = ctx.user_request + str(ctx.file_info or "")
                sem_cached = rag_cache.get(phase, "semantic", sem_query)
                if sem_cached is not None:
                    sem_results = self._deserialize_results(sem_cached, "semantic")
                    if sem_results:
                        print(f"[HybridEngine] cache HIT semantic: {len(sem_results)} 条")
                        all_results.extend(sem_results)
                else:
                    f = ex.submit(
                        _semantic_retriever.retrieve,
                        ctx.user_request,
                        ctx.file_info,
                        ctx.architecture,
                    )
                    futures[f] = "semantic"
                    _cache_meta[f] = ("semantic", sem_query)

            # === 收集结果 & 回写缓存 ===
            for f in as_completed(futures):
                source = futures[f]
                try:
                    results = f.result()
                    if results:
                        print(f"[HybridEngine] {source}: {len(results)} 条结果")
                        all_results.extend(results)
                        # 回写缓存
                        meta = _cache_meta.get(f)
                        if meta:
                            channel, query_text = meta
                            serialized = self._serialize_results(results)
                            rag_cache.set(phase, channel, query_text, serialized)
                except Exception as e:
                    print(f"[HybridEngine] {source} 失败: {e}")

        if not all_results:
            return ""

        # 后处理流水线（复用 PostProcessor 或降级实现）
        deduped = self._postprocessor.dedup(all_results)
        print(f"[HybridEngine] 去重: {len(all_results)} → {len(deduped)}")

        ranked = self._postprocessor.rerank(deduped)
        print(f"[HybridEngine] 重排序: top {len(ranked)}")

        formatted = self._postprocessor.format(ranked)
        return formatted

    # ========== Grep 子通道 ==========

    def _grep_framework_api(self, keywords: list[str], ctx) -> list:
        """SQLite FTS5 搜索 framework_api"""
        self._ensure_sqlite()
        lang_cfg = get_lang_config(ctx.code_gen_type)
        framework = lang_cfg.get("framework", "")
        # 把框架名也加入关键词（如 "Vue", "Spring"）
        fw_keywords = keywords + self._framework_tokens(framework)
        rows = sqlite_store.search_framework_api(fw_keywords, limit=5)
        return [
            _retrieval_result(
                content=self._fmt_api(row),
                source_collection="framework_api",
                source_channel="grep",
                score=0.9,  # 精确匹配高分
                metadata=row,
            )
            for row in rows
        ]

    def _grep_component(self, keywords: list[str], ctx) -> list:
        """SQLite FTS5 搜索 component_library"""
        self._ensure_sqlite()
        lang_cfg = get_lang_config(ctx.code_gen_type)
        framework = lang_cfg.get("framework", "")
        fw_keywords = keywords + self._framework_tokens(framework)
        rows = sqlite_store.search_component(fw_keywords, limit=5)
        return [
            _retrieval_result(
                content=self._fmt_component(row),
                source_collection="component_library",
                source_channel="grep",
                score=0.85,
                metadata=row,
            )
            for row in rows
        ]

    def _grep_error(self, error_text: str) -> list:
        """SQLite FTS5 搜索 error_pattern"""
        self._ensure_sqlite()
        if not error_text:
            return []
        rows = sqlite_store.search_error(error_text, limit=5)
        return [
            _retrieval_result(
                content=self._fmt_error(row),
                source_collection="error_pattern",
                source_channel="grep",
                score=0.9,
                metadata=row,
            )
            for row in rows
        ]

    def _grep_code_store(self, keywords: list[str], ctx) -> list:
        """ripgrep 搜索已验证代码"""
        results = []
        for kw in keywords[:3]:
            files = code_grep.search(kw, max_files=3)
            for f in files:
                results.append(_retrieval_result(
                    content=f"文件 {f['file_path']}\n{f['content'][:2000]}",
                    source_collection="code_store",
                    source_channel="grep",
                    score=0.8,
                    metadata={"file_path": f["file_path"]},
                ))

        # === 反馈追踪 (P2)：记录 grep 侧检索到的 code_store 条目 ===
        app_id = getattr(ctx, 'app_id', '')
        if app_id:
            try:
                from rag.feedback_tracker import feedback_tracker
                store_dir_str = str(code_grep.store_dir)
                for f in files[:5]:
                    fpath = f.get("file_path", "")
                    if fpath.startswith(store_dir_str):
                        rel = os.path.relpath(fpath, store_dir_str).replace("\\", "/")
                        parts = rel.split("/", 1)
                        if len(parts) >= 2:
                            feedback_tracker.record_to_session(
                                app_id, parts[0], parts[1])
            except Exception:
                pass  # 反馈追踪失败不影响检索

        return results[:5]

    # ========== 关键词提取 ==========

    def _extract_keywords(self, ctx) -> list[str]:
        """从 RetrievalContext 提取 grep 搜索关键词"""
        tokens = set()

        # 1. CamelCase 标识符（类名/函数名/API 名）
        for text in [ctx.user_request, ctx.file_info.get("description", "") if ctx.file_info else ""]:
            if not text:
                continue
            camel_matches = re.findall(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b', text)
            tokens.update(camel_matches)

            # 2. 常见技术关键词
            tech_terms = re.findall(
                r'\b(Controller|Service|Repository|DTO|Mapper|VO|Entity|'
                r'Component|Plugin|Middleware|Guard|Interceptor|Filter|'
                r'Router|Store|Config|Util|Helper|Factory|Builder|'
                r'CRUD|分页|权限|登录|缓存|事务|幂等|分布式|'
                r'JWT|Redis|OAuth|REST|API|SSE|WebSocket)\b',
                text, re.IGNORECASE,
            )
            tokens.update(tech_terms)

        # 3. 文件路径中的关键词
        if ctx.file_info:
            fpath = ctx.file_info.get("path", "")
            path_tokens = re.findall(r'([A-Z][a-zA-Z]+)', fpath)
            tokens.update(path_tokens)

        # 4. 中文分词简化版：取 2-4 字连续词
        chinese_words = re.findall(r'[一-鿿]{2,4}', ctx.user_request)
        tokens.update(chinese_words)

        return list(tokens)

    def _extract_error_text(self, ctx) -> str:
        """构建 error_pattern 搜索的报错文本"""
        parts = []
        if ctx.file_info:
            parts.append(ctx.file_info.get("description", ""))
        if parts:
            return " ".join(parts)
        return ""

    @staticmethod
    def _framework_tokens(framework: str) -> list[str]:
        """提取框架名的搜索 token"""
        tokens = []
        for token in re.split(r'[\s/]+', framework):
            if token and not token.lower() in ("3", "x", "2", "composition", "api", "script"):
                tokens.append(token)
        return tokens

    # ========== 格式化 ==========

    @staticmethod
    def _fmt_api(row: dict) -> str:
        api = row.get("api_name", "")
        sig = row.get("signature", "")
        imp = row.get("import_statement", "")
        example = row.get("example", "")
        return f"API {api}: {sig}\nimport: {imp}\n{example}"

    @staticmethod
    def _fmt_component(row: dict) -> str:
        name = row.get("component_name", "")
        snippet = row.get("code_snippet", "")
        return f"组件 {name}\n{snippet}" if snippet else ""

    @staticmethod
    def _fmt_error(row: dict) -> str:
        sig = row.get("error_signature", "")
        fix = row.get("fix_code", "")
        return f"错误 {sig}\n修复 {fix}" if sig else ""


    # ========== 缓存序列化 ==========

    @staticmethod
    def _serialize_results(results: list) -> str:
        """将 RetrievalResult 列表序列化为 JSON（不含 vector 字段）。"""
        items = []
        for r in results:
            items.append({
                "content": getattr(r, "content", ""),
                "source_collection": getattr(r, "source_collection", ""),
                "source_channel": getattr(r, "source_channel", ""),
                "score": getattr(r, "score", 0.0),
                "metadata": getattr(r, "metadata", {}),
            })
        return json.dumps(items, ensure_ascii=False)

    @staticmethod
    def _deserialize_results(json_str: str, source_channel: str) -> list | None:
        """从 JSON 反序列化为 RetrievalResult 列表。"""
        try:
            items = json.loads(json_str)
        except json.JSONDecodeError:
            return None
        results = []
        for item in items:
            results.append(_retrieval_result(
                content=item.get("content", ""),
                source_collection=item.get("source_collection", ""),
                source_channel=item.get("source_channel", source_channel),
                score=item.get("score", 0.0),
                metadata=item.get("metadata", {}),
            ))
        return results


# 全局单例
hybrid_engine = HybridEngine()
