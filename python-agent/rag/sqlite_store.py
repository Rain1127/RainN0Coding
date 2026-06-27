"""
SQLite FTS5 精确检索 —— framework_api / error_pattern / component_library

替代 Milvus 向量检索，用全文索引做精确匹配：
  - framework_api: 按 API 名称搜索（如 "ref", "BaseMapper"）
  - error_pattern: 按异常类名搜索（如 "NullPointerException"）
  - component_library: 按组件名搜索（如 "BaseController", "PageResult"）

用法：
    store = SqliteStore()
    store.init_tables()
    results = store.search_framework_api(["BaseMapper", "QueryWrapper"], limit=5)
    results = store.search_error("NullPointerException at line 42", limit=3)
"""

import os
import re
import sqlite3
from config import config


class SqliteStore:
    """SQLite FTS5 全文检索引擎 —— framework_api / error_pattern / component_library"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or config.SQLITE_DB_PATH
        self._conn: sqlite3.Connection | None = None

    # ========== 连接管理 ==========

    def connect(self):
        if self._conn is not None:
            return
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ========== 建表 ==========

    def init_tables(self):
        """创建 FTS5 虚拟表（如已存在则跳过）"""
        self.connect()

        # framework_api: 搜索 api_name + example
        # 使用 content= 指向 meta 表，FTS5 自动从 meta 读取文本
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS framework_api USING fts5(
                api_name,
                signature,
                import_statement,
                example,
                framework,
                content='framework_api_meta',
                content_rowid='rowid',
                tokenize='unicode61'
            )
        """)

        # error_pattern: 搜索 error_signature
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS error_pattern USING fts5(
                error_signature,
                fix_code,
                occurrence_count,
                content='error_pattern_meta',
                content_rowid='rowid',
                tokenize='unicode61'
            )
        """)

        # component_library: 搜索 component_name + code_snippet
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS component_library USING fts5(
                component_name,
                code_snippet,
                framework,
                use_count,
                content='component_library_meta',
                content_rowid='rowid',
                tokenize='porter unicode61'
            )
        """)

        # 元数据表：存储完整字段（FTS5 只能搜文本，这里存原始数据）
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS framework_api_meta (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                api_name TEXT,
                signature TEXT,
                import_statement TEXT,
                example TEXT,
                framework TEXT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS error_pattern_meta (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                error_signature TEXT,
                fix_code TEXT,
                occurrence_count INTEGER DEFAULT 1
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS component_library_meta (
                rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                component_name TEXT,
                code_snippet TEXT,
                framework TEXT,
                use_count INTEGER DEFAULT 1
            )
        """)

        self._conn.commit()
        print(f"[SqliteStore] 表初始化完成: {self.db_path}")

    # ========== 搜索 ==========

    def search_framework_api(self, keywords: list[str], limit: int = 5) -> list[dict]:
        """
        按 API 名称精确搜索。
        keywords: 从用户需求中提取的关键词，如 ["BaseMapper", "QueryWrapper", "分页"]
        """
        self.connect()
        if not keywords:
            return []

        # 构建 FTS5 查询：phrase match，兼容中英文
        fts_terms = " OR ".join(
            f'"{kw}"' for kw in keywords[:5] if kw
        )
        if not fts_terms:
            return []
        try:
            rows = self._conn.execute(
                "SELECT rowid, rank FROM framework_api WHERE framework_api MATCH ? "
                "ORDER BY rank LIMIT ?",
                (fts_terms, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            # FTS5 语法错误时回退到简单 LIKE
            return self._search_framework_api_fallback(keywords, limit)

        return [self._load_meta("framework_api_meta", r["rowid"]) for r in rows]

    def _search_framework_api_fallback(self, keywords: list[str], limit: int) -> list[dict]:
        """FTS5 失败时用 LIKE 回退"""
        rows = []
        for kw in keywords:
            like_kw = f"%{kw}%"
            cur = self._conn.execute(
                "SELECT rowid FROM framework_api_meta WHERE api_name LIKE ? LIMIT ?",
                (like_kw, limit),
            )
            rows.extend(cur.fetchall())
        return [self._load_meta("framework_api_meta", r["rowid"]) for r in rows[:limit]]

    def search_error(self, error_text: str, limit: int = 5) -> list[dict]:
        """
        从报错文本中提取异常类名，精确匹配 error_pattern。
        error_text: 编译/运行时报错文本
        """
        self.connect()
        tokens = self._extract_error_keywords(error_text)

        all_results: list[dict] = []

        # 策略 1: 用提取的 token 做精确搜索
        for token in tokens[:3]:
            try:
                rows = self._conn.execute(
                    "SELECT rowid, rank FROM error_pattern WHERE error_pattern MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (f'"{token}"', limit),
                ).fetchall()
                for r in rows:
                    meta = self._load_meta("error_pattern_meta", r["rowid"])
                    if meta:
                        meta["_rank"] = r["rank"]
                        all_results.append(meta)
            except sqlite3.OperationalError:
                # token 里有特殊字符，换 LIKE
                cur = self._conn.execute(
                    "SELECT rowid FROM error_pattern_meta WHERE error_signature LIKE ? LIMIT ?",
                    (f"%{token}%", limit),
                )
                for r in cur.fetchall():
                    meta = self._load_meta("error_pattern_meta", r["rowid"])
                    if meta:
                        all_results.append(meta)

        # 去重（按 rowid）
        seen = set()
        unique = []
        for r in sorted(all_results, key=lambda x: x.get("_rank", 999)):
            key = r.get("error_signature", id(r))
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique[:limit]

    def search_component(self, keywords: list[str], limit: int = 5) -> list[dict]:
        """
        按组件名称搜索。
        keywords: 如 ["BaseController", "分页", "JwtUtil"]
        """
        self.connect()
        if not keywords:
            return []

        fts_terms = " OR ".join(
            f'"{kw}"' for kw in keywords[:5] if kw
        )
        if not fts_terms:
            return []
        try:
            rows = self._conn.execute(
                "SELECT rowid, rank FROM component_library WHERE component_library MATCH ? "
                "ORDER BY rank LIMIT ?",
                (fts_terms, limit),
            ).fetchall()
        except sqlite3.OperationalError:
            return self._search_component_fallback(keywords, limit)

        return [self._load_meta("component_library_meta", r["rowid"]) for r in rows]

    def _search_component_fallback(self, keywords: list[str], limit: int) -> list[dict]:
        """FTS5 失败时用 LIKE 回退"""
        rows = []
        for kw in keywords:
            cur = self._conn.execute(
                "SELECT rowid FROM component_library_meta WHERE component_name LIKE ? LIMIT ?",
                (f"%{kw}%", limit),
            )
            rows.extend(cur.fetchall())
        return [self._load_meta("component_library_meta", r["rowid"]) for r in rows[:limit]]

    # ========== 数据种子 ==========

    def insert_framework_api(self, item: dict):
        """插入单条 framework_api（写入 meta，FTS5 延迟索引）"""
        self.connect()
        cur = self._conn.execute(
            "INSERT INTO framework_api_meta (api_name, signature, import_statement, example, framework) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                item.get("api_name", ""),
                item.get("signature", ""),
                item.get("import_statement", ""),
                item.get("example", ""),
                item.get("framework", ""),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def insert_error_pattern(self, item: dict):
        """插入单条 error_pattern"""
        self.connect()
        cur = self._conn.execute(
            "INSERT INTO error_pattern_meta (error_signature, fix_code, occurrence_count) "
            "VALUES (?, ?, ?)",
            (
                item.get("error_signature", ""),
                item.get("fix_code", ""),
                item.get("occurrence_count", 1),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def insert_component(self, item: dict):
        """插入单条 component_library"""
        self.connect()
        cur = self._conn.execute(
            "INSERT INTO component_library_meta (component_name, code_snippet, framework, use_count) "
            "VALUES (?, ?, ?, ?)",
            (
                item.get("component_name", ""),
                item.get("code_snippet", ""),
                item.get("framework", ""),
                item.get("use_count", 1),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def rebuild_indexes(self):
        """重建所有 FTS5 索引（批量写入后调用）"""
        self.connect()
        for table in ["framework_api", "error_pattern", "component_library"]:
            self._conn.execute(f"INSERT INTO {table}({table}) VALUES('rebuild')")
        self._conn.commit()
        print("[SqliteStore] FTS5 索引重建完成")

    def seed_all(self, framework_seeds: list[dict], component_seeds: list[dict],
                 error_seeds: list[dict]):
        """批量写入种子数据（写入 meta + 重建 FTS5 索引）"""
        self.connect()
        self.init_tables()

        print("[SqliteStore] 写入种子数据...")
        for item in framework_seeds:
            self.insert_framework_api(item)
        print(f"  framework_api: {len(framework_seeds)} 条")

        for item in component_seeds:
            self.insert_component(item)
        print(f"  component_library: {len(component_seeds)} 条")

        for item in error_seeds:
            self.insert_error_pattern(item)
        print(f"  error_pattern: {len(error_seeds)} 条")

        # 批量重建 FTS5 索引
        self.rebuild_indexes()
        print("[SqliteStore] 种子数据写入完成")

    # ========== 内部方法 ==========

    def _load_meta(self, table: str, rowid: int) -> dict:
        """从元数据表加载完整记录"""
        row = self._conn.execute(
            f"SELECT * FROM {table} WHERE rowid = ?", (rowid,)
        ).fetchone()
        return dict(row) if row else {}

    @staticmethod
    def _extract_error_keywords(text: str) -> list[str]:
        """从报错文本中提取异常类名"""
        patterns = [
            r'\b([A-Z][a-zA-Z]+(?:Exception|Error))\b',      # Java 异常
            r'\b(TypeError|SyntaxError|ImportError|ValueError|KeyError|'
            r'AttributeError|RuntimeError|NameError|IndexError)\b',  # Python 内建
            r'panic:\s*([^\n]+)',                              # Go panic
            r'error\[([A-Z]\d+)\]',                            # Rust compiler
            r'\b([A-Z][a-zA-Z]+Error)\b',                      # 通用 Error 后缀
        ]
        tokens = set()
        for pat in patterns:
            matches = re.findall(pat, text)
            tokens.update(matches)
        if not tokens:
            # fallback: 取前 3 个单词
            tokens = set(text.split()[:3])
        return list(tokens)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


# 全局单例
sqlite_store = SqliteStore()
