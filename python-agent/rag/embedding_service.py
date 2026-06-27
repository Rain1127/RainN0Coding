"""
Embedding 服务 —— 文本转向量

使用 sentence-transformers (PyTorch) 加载 BAAI/bge-small-zh-v1.5（512 维）。
PyTorch 不可用时自动安装，不降级到 TF-IDF。

2026-05-24: 修复 c10.dll Error 1114 —— 原因：intel-openmp 2026.0.0 与 torch 不兼容。
           方案：移除 intel-openmp/mkl 包，torch 使用自带 OpenMP。
"""
from config import config


class EmbeddingService:
    def __init__(self):
        self._model = None
        self._dimension = 512  # bge-small-zh-v1.5 默认维度

    def _load_model(self):
        """加载 sentence-transformers 模型"""
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer
        print(f"[Embedding] 加载 PyTorch 模型: {config.EMBEDDING_MODEL}...")
        self._model = SentenceTransformer(config.EMBEDDING_MODEL)
        self._dimension = self._model.get_embedding_dimension()
        print(f"[Embedding] PyTorch 模型就绪, 维度: {self._dimension}")

    @property
    def dimension(self) -> int:
        if self._model is None:
            self._load_model()
        return self._dimension

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        self._load_model()
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [e.tolist() for e in embeddings]


# 全局单例
embedding_service = EmbeddingService()
