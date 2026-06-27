"""
反馈追踪器 —— P2 质量反馈闭环核心

生命周期：
  1. 检索时 record_to_session() → 记录"本次生成参考了哪些历史条目"
  2. 构建完成时 apply_feedback() → 成功加分 / 失败扣分
  3. 入库时 record_ingestion() → 记录初始质量分
  4. 检索排序时 get_quality_score() → 读取真实质量分
  5. 定期清理时 get_low_quality_entries() → 找出需要淘汰的条目

SQLite 表结构（自动创建）:
  rag_quality:       app_id, file_path, quality_score, success_count,
                     failure_count, total_retrievals, created_at, updated_at
  rag_retrieval_log: id, gen_app_id, rag_app_id, rag_file_path,
                     created_at, build_applied

自引用过滤：gen_app_id == rag_app_id → 不记录（避免循环自我强化）
"""
import os
import sqlite3
import time
import threading
from config import config


class FeedbackTracker:
    """质量反馈追踪器 —— SQLite 持久化 + 内存会话缓存"""

    def __init__(self):
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()
        self._db_path = os.path.join(
            os.path.abspath(config.CODE_STORE_DIR), "_quality.db")
        # 内存会话缓存：gen_app_id → set of (rag_app_id, rag_file_path)
        self._pending_sessions: dict[str, set[tuple[str, str]]] = {}

    # ========== 连接管理 ==========

    def connect(self):
        if self._conn is not None:
            return
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def close(self):
        with self._lock:
            if self._conn:
                self._conn.close()
                self._conn = None

    def init_tables(self):
        """初始化 SQLite 表结构（幂等）"""
        self.connect()
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS rag_quality (
                    app_id         TEXT NOT NULL,
                    file_path      TEXT NOT NULL,
                    quality_score  REAL NOT NULL DEFAULT 70.0,
                    success_count  INTEGER NOT NULL DEFAULT 0,
                    failure_count  INTEGER NOT NULL DEFAULT 0,
                    total_retrievals INTEGER NOT NULL DEFAULT 0,
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT NOT NULL,
                    PRIMARY KEY (app_id, file_path)
                );

                CREATE TABLE IF NOT EXISTS rag_retrieval_log (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    gen_app_id     TEXT NOT NULL,
                    rag_app_id     TEXT NOT NULL,
                    rag_file_path  TEXT NOT NULL,
                    created_at     TEXT NOT NULL,
                    build_applied  INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_retrieval_gen
                    ON rag_retrieval_log(gen_app_id);
                CREATE INDEX IF NOT EXISTS idx_retrieval_rag
                    ON rag_retrieval_log(rag_app_id, rag_file_path);
                CREATE INDEX IF NOT EXISTS idx_quality_score
                    ON rag_quality(quality_score, updated_at);
            """)
            self._conn.commit()

    # ========== 检索时：记录会话 ==========

    def record_to_session(self, gen_app_id: str, rag_app_id: str, rag_file_path: str):
        """检索时调用：记录「本次生成参考了哪些历史条目」。

        过滤规则：
          - 自引用过滤：gen_app_id == rag_app_id 时不记录
          - 空值过滤：任一参数为空字符串时不记录
        """
        if not gen_app_id or not rag_app_id or not rag_file_path:
            return
        if gen_app_id == rag_app_id:
            return  # 自引用：同一轮生成的其他文件，不记录

        if gen_app_id not in self._pending_sessions:
            self._pending_sessions[gen_app_id] = set()
        self._pending_sessions[gen_app_id].add((rag_app_id, rag_file_path))

    # ========== 构建完成时：应用反馈 ==========

    def apply_feedback(self, gen_app_id: str, build_success: bool):
        """构建完成时调用：将本次会话的检索记录刷入 SQLite，更新质量分。

        Args:
            gen_app_id: 本次生成的 app_id
            build_success: 构建是否成功
        """
        session = self._pending_sessions.pop(gen_app_id, set())
        if not session:
            return

        self.connect()
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        delta = config.QUALITY_BOOST_ON_SUCCESS if build_success else -config.QUALITY_PENALTY_ON_FAILURE

        with self._lock:
            for rag_app_id, rag_file_path in session:
                # 写入检索日志
                self._conn.execute(
                    """INSERT INTO rag_retrieval_log
                       (gen_app_id, rag_app_id, rag_file_path, created_at, build_applied)
                       VALUES (?, ?, ?, ?, 1)""",
                    (gen_app_id, rag_app_id, rag_file_path, ts),
                )
                # 更新质量表：UPSERT
                self._conn.execute(
                    """INSERT INTO rag_quality
                       (app_id, file_path, quality_score, success_count,
                        failure_count, total_retrievals, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                       ON CONFLICT(app_id, file_path) DO UPDATE SET
                         quality_score = MAX(0.0, MIN(100.0,
                           rag_quality.quality_score + ?)),
                         success_count = rag_quality.success_count + ?,
                         failure_count = rag_quality.failure_count + ?,
                         total_retrievals = rag_quality.total_retrievals + 1,
                         updated_at = ?""",
                    (
                        rag_app_id, rag_file_path,
                        max(0.0, min(100.0, config.QUALITY_INITIAL_SCORE + delta)),
                        1 if build_success else 0,
                        0 if build_success else 1,
                        ts, ts,
                        delta,
                        1 if build_success else 0,
                        0 if build_success else 1,
                        ts,
                    ),
                )
            self._conn.commit()

    # ========== 入库时：记录初始质量 ==========

    def record_ingestion(self, app_id: str, file_path: str, review_score: int = 0):
        """新代码入库时调用：记录初始质量分。

        Args:
            app_id: 应用 ID
            file_path: 文件路径
            review_score: Reviewer 评分 (0-100)，用于计算初始质量分
        """
        if not app_id or not file_path:
            return
        self.connect()
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        # 初始质量分：以 review_score 为基础（若提供且 > 0），否则使用默认值
        if review_score > 0:
            initial = float(review_score)
        else:
            initial = float(config.QUALITY_INITIAL_SCORE)

        with self._lock:
            self._conn.execute(
                """INSERT INTO rag_quality
                   (app_id, file_path, quality_score, success_count,
                    failure_count, total_retrievals, created_at, updated_at)
                   VALUES (?, ?, ?, 0, 0, 0, ?, ?)
                   ON CONFLICT(app_id, file_path) DO UPDATE SET
                     quality_score = MAX(rag_quality.quality_score, ?),
                     updated_at = ?""",
                (app_id, file_path, initial, ts, ts, initial, ts),
            )
            self._conn.commit()

    # ========== 检索排序时：查询质量分 ==========

    def get_quality_score(self, app_id: str, file_path: str) -> float | None:
        """查询某个条目的质量分。返回 None 表示该条目无质量记录。

        用于 PostProcessor._success_score() 替代固定的 0.7。
        """
        if not app_id or not file_path:
            return None
        self.connect()
        with self._lock:
            row = self._conn.execute(
                "SELECT quality_score FROM rag_quality WHERE app_id = ? AND file_path = ?",
                (app_id, file_path),
            ).fetchone()
        if row:
            return float(row[0])
        return None

    # ========== 定期清理：查找低质量条目 ==========

    def get_low_quality_entries(self, threshold: float = 30.0,
                                 min_age_days: int = 30) -> list[dict]:
        """查找需要清理的低质量条目。

        Args:
            threshold: 质量分阈值，低于此分数的条目将被返回
            min_age_days: 最小存活天数，条目必须存在超过此天数才会被清理

        Returns:
            [{"app_id": str, "file_path": str, "quality_score": float, "updated_at": str}, ...]
        """
        self.connect()
        with self._lock:
            rows = self._conn.execute(
                """SELECT app_id, file_path, quality_score, updated_at
                   FROM rag_quality
                   WHERE quality_score < ?
                     AND julianday(updated_at) < julianday('now', ? || ' days')
                   ORDER BY quality_score ASC""",
                (threshold, f"-{min_age_days}"),
            ).fetchall()
        return [
            {
                "app_id": row[0],
                "file_path": row[1],
                "quality_score": row[2],
                "updated_at": row[3],
            }
            for row in rows
        ]

    def delete_entry(self, app_id: str, file_path: str):
        """删除质量记录（在清理 Milvus + 文件系统之后调用）。"""
        if not app_id or not file_path:
            return
        self.connect()
        with self._lock:
            self._conn.execute(
                "DELETE FROM rag_quality WHERE app_id = ? AND file_path = ?",
                (app_id, file_path),
            )
            self._conn.commit()


# 全局单例
feedback_tracker = FeedbackTracker()
