import hashlib
from dataclasses import dataclass, field

from config import config


@dataclass
class RetrievalResult:
    """单条检索结果"""

    content: str
    source_collection: str
    source_channel: str
    score: float
    metadata: dict = field(default_factory=dict)
    vector: list[float] | None = None

    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode()).hexdigest()


@dataclass
class RetrievalContext:
    """检索上下文"""

    phase: str
    user_request: str
    file_info: dict | None = None
    architecture: dict | None = None
    retry_count: int = 0
    code_gen_type: str = "vue_project"
    app_id: str = ""


class PostProcessor:
    """去重 -> 重排序 -> 格式化"""

    def __init__(self):
        self.top_k = config.RAG_TOP_K
        self.semantic_threshold = config.RAG_SEMANTIC_DEDUP_THRESHOLD

    def dedup(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """三步去重：内容哈希 + 语义相似度 + 来源去重"""
        if len(results) <= 1:
            return results

        seen_hashes: set[str] = set()
        hash_deduped: list[RetrievalResult] = []
        sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
        for r in sorted_results:
            h = r.content_hash()
            if h not in seen_hashes:
                seen_hashes.add(h)
                hash_deduped.append(r)

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
                seen[f"__{id(r)}"] = r
        return sorted(seen.values(), key=lambda x: x.score, reverse=True)

    def _source_key(self, r: RetrievalResult) -> str:
        """生成来源唯一键"""
        meta = r.metadata
        col = r.source_collection
        if col == "component_library":
            return f"{col}:{meta.get('component_name', '')}"
        if col == "code_store":
            return f"{col}:{meta.get('file_path', '')}"
        if col == "design_pattern":
            return f"{col}:{meta.get('pattern_name', '')}"
        if col == "error_pattern":
            return f"{col}:{meta.get('error_signature', '')}"
        if col == "framework_api":
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

    def rerank(
        self, results: list[RetrievalResult], query_vector: list[float] | None = None
    ) -> list[RetrievalResult]:
        """四因子加权重排序"""
        for r in results:
            semantic_score = r.score
            source_score = 1.0 if r.source_channel == "intent_directed" else 0.6
            success_score = self._success_score(r)
            freshness_score = 0.5

            r.score = (
                0.40 * semantic_score
                + 0.25 * source_score
                + 0.20 * success_score
                + 0.15 * freshness_score
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[: self.top_k]

    def _success_score(self, r: RetrievalResult) -> float:
        """提取成功记录因子，code_store 使用反馈追踪的真实质量分"""
        meta = r.metadata
        col = r.source_collection
        if col == "code_store":
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
            return 0.7
        if col == "error_pattern":
            count = meta.get("occurrence_count", 1)
            return min(float(count) / 10.0, 1.0)
        if col == "component_library":
            use_count = meta.get("use_count", 1)
            return min(float(use_count) / 20.0, 1.0)
        return 0.5

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
            blocks[rtype].append(r.content[:800])

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
                "## 推荐设计模式\n\n" + "\n---\n".join(blocks["pattern"])
            )

        if not sections:
            return ""

        return (
            "## 可复用资源（来自 RAG 多路检索，优先使用，避免造轮子）\n\n"
            + "\n\n".join(sections)
        )
