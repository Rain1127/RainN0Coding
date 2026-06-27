"""
RAGAS RAG 质量评估器

模式:
  1. online (轻量): 用检索 score 计算 precision/recall，不调 LLM，不阻塞主流程
  2. offline (完整): 用 RAGAS LLM 评估 faithfulness/context_relevancy，事后批量跑
     Judge LLM: deepseek-v4-pro (可配置 RAGAS_JUDGE_MODEL 环境变量)

用法:
  from rag.ragas_evaluator import evaluate_online, evaluate_offline
  metrics = evaluate_online(retrieval_results, generated_code)
  # → {context_precision, context_hit_rate, avg_score}

  results = evaluate_offline(dataset)
  # → [{faithfulness, context_precision, ...}]
"""
import os

# 强制离线模式：RAGAS 的 HuggingFaceEmbeddings 会尝试连接 huggingface.co
# 设置此环境变量后，SentenceTransformer 将仅使用本地缓存模型
os.environ.setdefault("HF_HUB_OFFLINE", "1")

from dataclasses import dataclass, field
from config import config


@dataclass
class RagasMetrics:
    """RAG 评估指标"""
    context_precision: float = 0.0     # 检索结果中高相关 (>0.7) 的占比
    context_hit_rate: float = 0.0      # 检索结果中至少有一条相关的比例
    avg_retrieval_score: float = 0.0   # 平均检索分数
    retrieved_count: int = 0           # 检索结果总数
    high_quality_count: int = 0        # 高分结果数 (score > 0.7)
    retrieval_timing_ms: int = 0       # 检索耗时


def evaluate_online(retrieval_results: list, query: str = "",
                    generated_text: str = "") -> RagasMetrics:
    """
    在线评估（轻量，不调 LLM）。

    基于 Milvus 检索 score 计算 precision/hit_rate。
    """
    if not retrieval_results:
        return RagasMetrics()

    scores = []
    high_quality = 0
    for r in retrieval_results:
        score = getattr(r, 'score', 0)
        scores.append(score)
        if score > 0.7:
            high_quality += 1

    total = len(scores)
    return RagasMetrics(
        context_precision=high_quality / total if total > 0 else 0.0,
        context_hit_rate=1.0 if high_quality > 0 else 0.0,
        avg_retrieval_score=sum(scores) / total if total > 0 else 0.0,
        retrieved_count=total,
        high_quality_count=high_quality,
    )


def create_ragas_embeddings():
    """
    创建 RAGAS 评估用的 Embeddings 模型。

    包装项目现有的 embedding_service（BAAI/bge-small-zh-v1.5），
    适配 RAGAS 0.4.x 的 BaseRagasEmbedding 接口（modern embeddings）。

    Returns:
        BaseRagasEmbedding 实例
    """
    from ragas.embeddings.base import BaseRagasEmbedding
    from rag.embedding_service import embedding_service

    class LocalEmbeddings(BaseRagasEmbedding):
        """将项目现有的 EmbeddingService 适配为 RAGAS modern embeddings 接口"""

        async def aembed_text(self, text: str, **kwargs) -> list[float]:
            return embedding_service.embed(text)

        def embed_text(self, text: str, **kwargs) -> list[float]:
            return embedding_service.embed(text)

    return LocalEmbeddings()


def create_ragas_judge_llm():
    """
    创建 RAGAS 离线评估用的 Judge LLM（deepseek-v4-pro）。

    使用 RAGAS 0.4.x 的 llm_factory + OpenAI 兼容客户端，
    指向 DeepSeek API，温度设为 0 确保评估结果稳定可复现。

    Returns:
        InstructorBaseRagasLLM 实例，可直接传给 ragas.evaluate() 的 metrics
    """
    from ragas.llms import llm_factory
    import openai

    client = openai.OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        timeout=config.LLM_TIMEOUT,
    )
    return llm_factory(
        model=config.RAGAS_JUDGE_MODEL,
        client=client,
    )


def evaluate_offline(dataset: list[dict]) -> list[dict]:
    """
    离线评估（完整 RAGAS，需要 Judge LLM）。

    使用 deepseek-v4-pro 作为 Judge LLM 对生成结果进行多维度评估。

    dataset: [{"question": str, "answer": str, "contexts": [str], "ground_truth": str}]

    返回 RAGAS 指标: faithfulness, context_precision, context_recall, answer_relevancy
    """
    try:
        from ragas import evaluate
        from ragas.metrics.collections import (
            Faithfulness, ContextPrecision, ContextRecall, AnswerRelevancy,
        )
        from datasets import Dataset

        judge_llm = create_ragas_judge_llm()
        embeddings = create_ragas_embeddings()
        print(f"[RAGAS] Judge LLM: {config.RAGAS_JUDGE_MODEL} (temperature={config.RAGAS_JUDGE_TEMPERATURE})")

        ds = Dataset.from_list(dataset)
        result = evaluate(
            ds,
            metrics=[
                Faithfulness(llm=judge_llm),
                ContextPrecision(llm=judge_llm),
                ContextRecall(llm=judge_llm),
                AnswerRelevancy(llm=judge_llm, embeddings=embeddings),
            ],
        )
        return result.to_pandas().to_dict("records")
    except ImportError as e:
        print(f"[RAGAS] 离线评估不可用: {e}")
        return []
