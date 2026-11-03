"""
RAG 结果缓存 —— Redis-backed, 版本隔离 + 热点查询动态 TTL

Key 结构: rag:v2:{seed_version}:{channel_version}:{phase}:{channel}:{query_sha256}

热点检测:
  - 滑动窗口计数: rag:query:count:{bucket}:{query_sha256}
  - bucket = floor(now / window_size)，当前 + 上一个 bucket 求和
  - 窗口内计数 >= 阈值 → 热查询 → TTL 自动晋级 (冷 30min → 热 2h)

版本 SHA 由种子数据内容计算，动态 code_store 写入另行递增通道版本。
Redis 不可用时旁路缓存，并在冷却后重连。
"""
import hashlib
import json
import re
import time
from pathlib import Path
from uuid import uuid4
from typing import Optional
from config import config, get_lang_config
from rag.singleflight import SingleFlight, record_singleflight


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
SCHEMA_VERSION = 2
RECONNECT_COOLDOWN_SECONDS = 5
NEGATIVE_TTL_SECONDS = 30
CODE_STORE_CHANNELS = ("grep_cs", "intent_directed", "global_vector")


def retrieval_input(ctx, keywords: list[str] | None = None) -> dict:
    """Capture all context that may influence a retrieval channel."""
    architecture = ctx.architecture or {}
    return {
        "keywords": sorted(set(keywords or [])),
        "code_gen_type": ctx.code_gen_type,
        "framework": architecture.get("tech_stack", {}).get("framework")
                     or get_lang_config(ctx.code_gen_type).get("framework", ""),
        "user_request": ctx.user_request,
        "file_info": ctx.file_info or {},
        "architecture": architecture,
        "embedding_model": config.EMBEDDING_MODEL,
        "algorithm_version": "2026-09-27-v2",
    }


def _canonical_input(query: str | dict) -> str:
    if isinstance(query, str):
        query = {"legacy_query": normalize_query(query)}
    if not isinstance(query, dict):
        raise TypeError("RAG query must be a string or mapping")
    normalized = dict(query)
    if "keywords" in normalized:
        normalized["keywords"] = sorted(set(normalized["keywords"]))
    return json.dumps(normalized, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


# ============ Query 规范化 ============

def normalize_query(query_text: str) -> str:
    """规范化旧式文本 query；结构化检索输入走规范 JSON。

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

    def __init__(self, *, singleflight_enabled: bool = True):
        self._redis = None
        self._ok: Optional[bool] = None
        self._last_failure = 0.0
        self._dirty_file = Path(config.CODE_STORE_DIR) / ".rag-cache-version"
        self._pending_file = Path(config.CODE_STORE_DIR) / ".rag-cache-pending"
        self.singleflight_enabled = singleflight_enabled
        self._singleflight = SingleFlight()

    # ---- 公开 API ----

    def get(self, phase: str, channel: str, query_text: str | dict) -> Optional[str]:
        """读取缓存。命中返回 JSON 字符串，未命中/不可用返回 None。"""
        identity = self._prepare_identity(phase, channel, query_text)
        if identity is None:
            return None
        r, key = identity
        return self._read_key(r, key, phase, channel)

    def _prepare_identity(self, phase, channel, query_text):
        """Pin the generation once; a failed version read must bypass sharing."""
        r = self._get_redis()
        if not r:
            self._record_status(phase, channel, "bypass")
            return None
        try:
            if channel in CODE_STORE_CHANNELS and self._pending_file.exists():
                self.bump_code_store_versions()
                if self._pending_file.exists():
                    self._record_status(phase, channel, "bypass")
                    return None
            key = self._make_key(phase, channel, query_text)
            return r, key
        except (TypeError, ValueError, UnicodeDecodeError):
            self._record_status(phase, channel, "miss")
        except Exception:
            self._mark_redis_failure()
            self._record_status(phase, channel, "bypass")
        return None

    def _read_key(self, r, key, phase, channel, *, record=True):
        status = 'miss'
        try:
            if record:
                self._record_heat(key, r)
            raw = r.get(key)
            if raw:
                envelope = json.loads(raw.decode("utf-8"))
                if (isinstance(envelope, dict)
                        and envelope.get("schema_version") == SCHEMA_VERSION
                        and isinstance(envelope.get("payload"), str)):
                    items = json.loads(envelope["payload"])
                    if isinstance(items, list) and all(
                        isinstance(item, dict)
                        and isinstance(item.get("content"), str)
                        and isinstance(item.get("source_collection"), str)
                        and isinstance(item.get("source_channel"), str)
                        and isinstance(item.get("score"), (int, float))
                        and isinstance(item.get("metadata"), dict)
                        for item in items
                    ):
                        if items and self._get_ttl(key, r) == config.RAG_CACHE_TTL_HOT:
                            r.expire(key, config.RAG_CACHE_TTL_HOT)
                        if record:
                            self._record_status(phase, channel, "hit")
                        return envelope["payload"]
        except (TypeError, ValueError, UnicodeDecodeError):
            pass
        except Exception:
            self._mark_redis_failure()
            status = 'bypass'
        if record:
            self._record_status(phase, channel, status)
        return None

    def get_or_load(self, phase, channel, query_text, loader) -> Optional[str]:
        """Load a serialized result once per pinned key while it is in flight."""
        identity = self._prepare_identity(phase, channel, query_text)

        def load():
            self._record_flight(phase, channel, 'executed')
            try:
                value = loader()
            except BaseException:
                self._record_flight(phase, channel, 'failure')
                raise
            if value is not None and identity is not None and self._ok:
                r, key = identity
                self._write_key(r, key, channel, value, negative=value == '[]')
            return value

        if identity is None:
            return load()
        r, key = identity
        cached = self._read_key(r, key, phase, channel)
        if cached is not None:
            return cached
        if not self._ok or not self.singleflight_enabled:
            return load()

        def recheck_and_load():
            if self._ok:
                cached = self._read_key(r, key, phase, channel, record=False)
                if cached is not None:
                    self._record_flight(phase, channel, 'race_hit')
                    return cached
            return load()

        return self._singleflight.run(
            key, recheck_and_load,
            lambda status: self._record_flight(phase, channel, status))

    @staticmethod
    def _record_flight(phase, channel, status):
        try:
            record_singleflight(phase, channel, status)
        except Exception:
            pass

    def set(self, phase: str, channel: str, query_text: str | dict,
            value: str, *, negative: bool = False):
        """写入缓存 —— 使用自适应 TTL（热查询更长）。"""
        r = self._get_redis()
        if not r:
            return
        try:
            if channel in CODE_STORE_CHANNELS and self._pending_file.exists():
                return
            key = self._make_key(phase, channel, query_text)
            self._write_key(r, key, channel, value, negative=negative)
        except (TypeError, ValueError):
            return
        except Exception:
            self._mark_redis_failure()

    def _write_key(self, r, key, channel, value, *, negative=False):
        try:
            if channel in CODE_STORE_CHANNELS and self._pending_file.exists():
                return
            ttl = NEGATIVE_TTL_SECONDS if negative else self._get_ttl(key, r)
            envelope = json.dumps({"schema_version": SCHEMA_VERSION, "payload": value},
                                  ensure_ascii=False, separators=(",", ":"))
            r.setex(key, ttl, envelope)
        except (TypeError, ValueError):
            return
        except Exception:
            self._mark_redis_failure()

    # ---- 内部 ----

    def _make_key(self, phase: str, channel: str, query_text: str | dict) -> str:
        digest = hashlib.sha256(_canonical_input(query_text).encode("utf-8")).hexdigest()
        r = self._redis if self._ok else None
        raw_version = r.get(f"rag:v2:channel_version:{channel}") if r else None
        channel_version = int(raw_version) if raw_version else 0
        local_version = self._dirty_file.read_text(encoding="utf-8") if (
            channel in CODE_STORE_CHANNELS and self._dirty_file.exists()) else "0"
        return f"rag:v2:{VERSION_SHA}:{channel_version}-{local_version}:{phase}:{channel}:{digest}"

    def _get_ttl(self, key: str, r) -> int:
        """判定 query 热度并返回对应的 TTL。

        固定窗口滑动计数：
          1. 对规范化 query 做 SHA-256
          2. 计算当前窗口 bucket = floor(now / window_size)
          3. 读取 get() 已递增的当前 bucket
          4. 同时读取上一 bucket 的计数（窗口边界处的平滑过渡）
          5. 总计 >= 阈值 → 热查询 TTL，否则冷查询 TTL
        """
        query_md5 = hashlib.sha256(key.encode("utf-8")).hexdigest()

        window = config.RAG_HOT_QUERY_WINDOW       # 默认 600s = 10min
        now = int(time.time())
        current_bucket = now // window
        prev_bucket = current_bucket - 1

        current_key = f"rag:query:count:{current_bucket}:{query_md5}"
        prev_key = f"rag:query:count:{prev_bucket}:{query_md5}"

        current_count = int(r.get(current_key) or 0)

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

    def _record_heat(self, key: str, r) -> None:
        window = config.RAG_HOT_QUERY_WINDOW
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        heat_key = f"rag:query:count:{int(time.time()) // window}:{digest}"
        r.incr(heat_key)
        r.expire(heat_key, window * 2)

    @staticmethod
    def _record_status(phase: str, channel: str, status: str) -> None:
        try:
            from monitoring import record_rag_cache_hit
            record_rag_cache_hit(status, phase=phase, channel=channel)
        except Exception:
            pass

    def _mark_redis_failure(self) -> None:
        self._ok = False
        self._last_failure = time.monotonic()

    def bump_code_store_versions(self) -> bool:
        """Invalidate every channel that can include newly indexed code."""
        r = self._get_redis()
        if not r:
            self._pending_file.parent.mkdir(parents=True, exist_ok=True)
            self._pending_file.touch()
            return False
        try:
            for channel in CODE_STORE_CHANNELS:
                r.incr(f"rag:v2:channel_version:{channel}")
            self._pending_file.unlink(missing_ok=True)
            return True
        except Exception:
            self._pending_file.parent.mkdir(parents=True, exist_ok=True)
            self._pending_file.touch()
            self._mark_redis_failure()
            return False

    def code_store_changed(self) -> None:
        """Persist a local generation before trying Redis invalidation."""
        self._dirty_file.parent.mkdir(parents=True, exist_ok=True)
        self._dirty_file.write_text(uuid4().hex, encoding="utf-8")
        self.bump_code_store_versions()

    def _get_redis(self):
        if self._ok is False:
            if time.monotonic() - self._last_failure < RECONNECT_COOLDOWN_SECONDS:
                return None
            self._ok = None
        if self._ok is True:
            return self._redis
        # 首次连接 —— 懒导入 redis 避免模块缺失阻塞加载
        try:
            import redis
            self._redis = redis.Redis(
                host=config.REDIS_HOST,
                port=config.REDIS_PORT,
                password=config.REDIS_PASSWORD or None,
                db=2,
                socket_connect_timeout=2,
            )
            self._redis.ping()
            self._ok = True
            print(f"[RagCache] Redis 连接成功 (db=2, version={VERSION_SHA})")
        except Exception:
            self._mark_redis_failure()
            print("[RagCache] Redis 不可用，缓存降级跳过")
        return self._redis if self._ok else None


# ============ 全局单例 ============

rag_cache = RagCache()
