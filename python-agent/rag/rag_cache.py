"""
RAG 结果缓存 —— Redis-backed, 版本隔离 + 热点查询动态 TTL

Key 结构: rag_cache:{version_sha}:{phase}:{channel}:{query_md5}

热点检测:
  - 滑动窗口计数: rag:query:count:{bucket}:{query_md5}
  - bucket = floor(now / window_size)，当前 + 上一个 bucket 求和
  - 窗口内计数 >= 阈值 → 热查询 → TTL 自动晋级 (冷 30min → 热 2h)

版本 SHA 由种子数据内容计算，种子更新后自动变化 → 旧缓存自然失效。
Redis 不可用时自动降级为空操作，不影响检索功能。
"""
import hashlib
import json
import re
import time
from typing import Optional
from config import config


# ============ 版本 SHA ============

def _compute_version_sha() -> str:
    """对所有种子数据的规范 JSON 计算 SHA-256，取前 12 位作为版本指纹。"""
    from rag.seed_data import (
        FRAMEWORK_API_SEEDS,
        COMPONENT_LIBRARY_SEEDS,
        DESIGN_PATTERN_SEEDS,
        ERROR_PATTERN_SEEDS,
    )
    all_seeds = (
        list(FRAMEWORK_API_SEEDS)
        + list(COMPONENT_LIBRARY_SEEDS)
        + list(DESIGN_PATTERN_SEEDS)
        + list(ERROR_PATTERN_SEEDS)
    )
    canonical = json.dumps(all_seeds, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]


VERSION_SHA = _compute_version_sha()


# ============ Query 规范化 ============

def normalize_query(query_text: str) -> str:
    """规范化 query 文本，使相似 query 共享同一个 query_md5。

    规则：
      1. 去首尾空白
      2. 合并连续空白字符（\\s+ → 单个空格）
      3. 小写化
      4. 去除无意义语气词碎片（单一语气词无影响，保留完整中文文本）

    注意：不进行中文分词或同义词归一化 —— 那是 Milvus 通道的职责。
    这里仅做字面层面的轻量规范化。
    """
    text = query_text.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.lower()
    return text


# ============ RagCache ============

class RagCache:
    """RAG 检索结果缓存 + 热点查询自适应 TTL。

    Redis DB 2，与 conversation_memory (DB 1) 隔离。
    redis 模块未安装时自动降级，get 返回 None，set 空操作。

    冷查询 TTL:  config.RAG_CACHE_TTL_COLD   (默认 30 分钟)
    热查询 TTL:  config.RAG_CACHE_TTL_HOT    (默认 2 小时)

    热点判定:   固定窗口计数（sliding by overlap），
               当前 + 上一个 bucket 计数 >= RAG_HOT_QUERY_THRESHOLD → 晋级。
    """

    def __init__(self):
        self._redis = None
        self._ok: Optional[bool] = None

    # ---- 公开 API ----

    def get(self, phase: str, channel: str, query_text: str) -> Optional[str]:
        """读取缓存。命中返回 JSON 字符串，未命中/不可用返回 None。"""
        r = self._get_redis()
        if not r:
            return None
        try:
            key = self._make_key(phase, channel, query_text)
            raw = r.get(key)
            if raw:
                return raw.decode("utf-8", errors="replace")
        except Exception:
            pass
        return None

    def set(self, phase: str, channel: str, query_text: str, value: str):
        """写入缓存 —— 使用自适应 TTL（热查询更长）。"""
        r = self._get_redis()
        if not r:
            return
        try:
            key = self._make_key(phase, channel, query_text)
            ttl = self._get_ttl(query_text, r)
            r.setex(key, ttl, value)
        except Exception:
            pass

    # ---- 内部 ----

    def _make_key(self, phase: str, channel: str, query_text: str) -> str:
        norm = normalize_query(query_text)
        query_md5 = hashlib.md5(norm.encode("utf-8")).hexdigest()
        return f"rag_cache:{VERSION_SHA}:{phase}:{channel}:{query_md5}"

    def _get_ttl(self, query_text: str, r) -> int:
        """判定 query 热度并返回对应的 TTL。

        固定窗口滑动计数：
          1. 对规范化 query 做 MD5
          2. 计算当前窗口 bucket = floor(now / window_size)
          3. INCR 当前 bucket → redis 自动创建/递增计数 key
          4. 同时读取上一 bucket 的计数（窗口边界处的平滑过渡）
          5. 总计 >= 阈值 → 热查询 TTL，否则冷查询 TTL
        """
        norm = normalize_query(query_text)
        query_md5 = hashlib.md5(norm.encode("utf-8")).hexdigest()

        window = config.RAG_HOT_QUERY_WINDOW       # 默认 600s = 10min
        now = int(time.time())
        current_bucket = now // window
        prev_bucket = current_bucket - 1

        current_key = f"rag:query:count:{current_bucket}:{query_md5}"
        prev_key = f"rag:query:count:{prev_bucket}:{query_md5}"

        # INCR 当前 bucket
        try:
            current_count = r.incr(current_key)
            r.expire(current_key, window * 2)  # 2x 窗口 TTL，确保不泄漏
        except Exception:
            return config.RAG_CACHE_TTL_COLD

        # 读取上一 bucket（窗口边界重叠）
        try:
            prev_raw = r.get(prev_key)
            prev_count = int(prev_raw) if prev_raw else 0
        except Exception:
            prev_count = 0

        total = current_count + prev_count

        if total >= config.RAG_HOT_QUERY_THRESHOLD:
            return config.RAG_CACHE_TTL_HOT
        return config.RAG_CACHE_TTL_COLD

    def _get_redis(self):
        if self._ok is False:
            return None
        if self._ok is True:
            return self._redis
        # 首次连接 —— 懒导入 redis 避免模块缺失阻塞加载
        try:
            import redis
            self._redis = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                db=2,
                socket_connect_timeout=2,
            )
            self._redis.ping()
            self._ok = True
            print(f"[RagCache] Redis 连接成功 (db=2, version={VERSION_SHA})")
        except Exception:
            self._ok = False
            print("[RagCache] Redis 不可用，缓存降级跳过")
        return self._redis if self._ok else None


# ============ 全局单例 ============

rag_cache = RagCache()
