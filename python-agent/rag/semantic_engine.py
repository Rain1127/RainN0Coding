"""
精简语义检索引擎 —— 仅负责 design_pattern + component_library 的向量检索

Embedding 次数从 5-10 次降到 1 次，Milvus 只搜 2 个 Collection。
"""

from rag.embedding_service import embedding_service
from rag.milvus_client import milvus_store
from rag.retrieval_engine import RetrievalResult  # 复用数据模型


class SemanticRetriever:
    """语义检索：design_pattern + component_library，用 embedding 做概念映射"""

    SEMANTIC_COLLECTIONS = [
        {"collection": "design_pattern", "top_k": 5},
        {"collection": "component_library", "top_k": 3},
    ]

    def retrieve(self, user_request: str, file_info: dict | None = None,
                 architecture: dict | None = None) -> list[RetrievalResult]:
        """
        向量检索 design_pattern + component_library。

        Args:
            user_request: 用户原始需求
            file_info: 当前文件信息 {'path': str, 'description': str, ...}
            architecture: 架构方案 dict

        Returns:
            list[RetrievalResult]
        """
        query_text = self._build_query_text(user_request, file_info, architecture)
        try:
            query_vector = embedding_service.embed(query_text)
        except Exception:
            return []

        queries = [(c["collection"], query_vector, c["top_k"]) for c in self.SEMANTIC_COLLECTIONS]
        raw_results = milvus_store.search_multi(queries)

        results: list[RetrievalResult] = []
        for (col, _, _), hits in zip(queries, raw_results):
            for hit in hits:
                entity = hit.get("entity", {})
                content = self._extract_content(col, entity)
                if not content:
                    continue
                results.append(RetrievalResult(
                    content=content,
                    source_collection=col,
                    source_channel="semantic",
                    score=hit.get("distance", 0.0),
                    metadata={k: v for k, v in entity.items()},
                ))
        return results

    def _build_query_text(self, user_request: str, file_info: dict | None,
                          architecture: dict | None) -> str:
        """构造向量检索的查询文本"""
        parts = [user_request]
        if architecture:
            features = architecture.get("component_tree", [])
            if features:
                parts.append(str(features)[:500])
        if file_info:
            parts.append(file_info.get("description", ""))
        return " ".join(p for p in parts if p)

    @staticmethod
    def _extract_content(collection: str, entity: dict) -> str:
        """从 Milvus entity 提取文本内容"""
        if collection == "design_pattern":
            name = entity.get("pattern_name", "")
            desc = entity.get("description", "")
            example = entity.get("example_code", "")
            parts = [p for p in [f"模式 {name}:", desc, example] if p]
            return "\n".join(parts) if parts else ""
        elif collection == "component_library":
            name = entity.get("component_name", "")
            snippet = entity.get("code_snippet", "")
            return f"组件 {name}\n{snippet}" if snippet else ""
        return ""


# 全局单例
semantic_retriever = SemanticRetriever()
