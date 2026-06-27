"""
Milvus 客户端 —— 双模式：Lite (本地文件) / Standalone (Docker)

并行检索：ThreadPoolExecutor 实现 Collection 级真正并行搜索。

用法：
    store = MilvusStore()
    store.init_collections()
    results = store.search("component_library", query_vector, limit=5)
    # 异步并行：
    results = await store.search_multi_async([
        ("component_library", vec1, 5),
        ("code_store", vec2, 5),
    ])
"""
import os
import shutil
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pymilvus import MilvusClient
from config import config


class MilvusStore:
    """Milvus 向量数据库封装 —— Lite/Standalone 双模式"""

    COLLECTIONS = {
        "code_store": 512,
        "component_library": 512,
        "design_pattern": 512,
        "error_pattern": 512,
        "framework_api": 512,
    }

    OUTPUT_FIELDS_MAP = {
        "code_store": ["app_id", "file_path", "content", "code_gen_type", "tags"],
        "component_library": ["component_name", "props_schema", "code_snippet", "framework", "use_count"],
        "design_pattern": ["pattern_name", "description", "example_code", "best_for"],
        "error_pattern": ["error_signature", "fix_code", "occurrence_count"],
        "framework_api": ["api_name", "signature", "import_statement", "example", "framework"],
    }

    def __init__(self):
        self._client: MilvusClient | None = None
        self._connected = False
        self._mode = config.MILVUS_MODE  # "lite" | "standalone"
        self._executor = ThreadPoolExecutor(
            max_workers=config.RAG_PARALLEL_WORKERS,
            thread_name_prefix="milvus",
        )

        if self._mode == "lite":
            db_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "milvus_data",
            )
            os.makedirs(db_dir, exist_ok=True)
            self.db_path = os.path.join(db_dir, "milvus_lite.db")
        else:
            self._host = config.MILVUS_HOST
            self._port = config.MILVUS_PORT

    # ========== 连接管理 ==========

    def connect(self):
        if self._connected:
            return
        if self._mode == "lite":
            self._client = MilvusClient(self.db_path)
            print(f"[Milvus] 已连接 (lite): {self.db_path}")
        else:
            self._client = MilvusClient(uri=f"http://{self._host}:{self._port}")
            print(f"[Milvus] 已连接 (standalone): {self._host}:{self._port}")
        self._connected = True

    # ========== Collection 管理 ==========

    def init_collections(self):
        """初始化所有 Collections（不存在则创建）"""
        self.connect()
        existing = self._client.list_collections()
        for name, dim in self.COLLECTIONS.items():
            if name not in existing:
                self._client.create_collection(
                    collection_name=name,
                    dimension=dim,
                    metric_type="COSINE",
                    auto_id=True,
                )
                print(f"[Milvus] 创建 Collection: {name} (dim={dim})")
            else:
                print(f"[Milvus] Collection 已存在: {name}")

    def ensure_collection(self, collection_name: str):
        """确保单个 Collection 存在"""
        self.connect()
        if collection_name not in self._client.list_collections():
            self._client.create_collection(
                collection_name=collection_name,
                dimension=self.COLLECTIONS.get(collection_name, 512),
                metric_type="COSINE",
                auto_id=True,
            )

    # ========== 同步搜索 ==========

    def search(self, collection_name: str, query_vector: list,
               limit: int = 5, output_fields: list | None = None) -> list:
        """单 Collection 向量相似度检索"""
        self.connect()
        if collection_name not in self._client.list_collections():
            return []
        self._load_collection(collection_name)
        if output_fields is None:
            output_fields = self.OUTPUT_FIELDS_MAP.get(collection_name, ["*"])
        results = self._client.search(
            collection_name=collection_name,
            data=[query_vector],
            limit=limit,
            output_fields=output_fields,
        )
        if not results or not results[0]:
            return []
        return results[0]

    def search_multi(self, queries: list[tuple]) -> list[list]:
        """
        多 Collection 并行搜索（同步接口，内部用 ThreadPoolExecutor）。

        Args:
            queries: [(collection_name, query_vector, limit, output_fields), ...]

        Returns:
            [[hit_dict, ...], ...]  每个 query 的结果列表
        """
        if not queries:
            return []
        if len(queries) == 1:
            q = queries[0]
            return [self.search(q[0], q[1], q[2] if len(q) > 2 else 5,
                               q[3] if len(q) > 3 else None)]

        futures = {}
        for i, q in enumerate(queries):
            col = q[0] # collection_name
            vec = q[1] # query_vector
            limit = q[2] if len(q) > 2 else 5 # limit
            fields = q[3] if len(q) > 3 else None # output_fields
            futures[self._executor.submit(self.search, col, vec, limit, fields)] = i

        results = [None] * len(queries)
        for f in as_completed(futures):
            idx = futures[f]
            results[idx] = f.result()
        return results

    # ========== 异步搜索（供 asyncio 集成） ==========

    async def search_async(self, collection_name: str, query_vector: list,
                           limit: int = 5, output_fields: list | None = None) -> list:
        """异步包装单 Collection 搜索"""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self.search,
            collection_name, query_vector, limit, output_fields,
        )

    async def search_multi_async(self, queries: list[tuple]) -> list[list]:
        """
        多 Collection 异步并行搜索 —— 真正的并发。

        Args:
            queries: [(collection_name, query_vector, limit), ...]

        Returns:
            [[hit_dict, ...], ...]
        """
        import asyncio
        if not queries:
            return []
        if len(queries) == 1:
            q = queries[0]
            r = await self.search_async(q[0], q[1], q[2] if len(q) > 2 else 5)
            return [r]
        tasks = [
            self.search_async(q[0], q[1], q[2] if len(q) > 2 else 5)
            for q in queries
        ]
        return await asyncio.gather(*tasks)

    # ========== 便利搜索方法 ==========

    def search_components(self, query_vector: list, limit: int = 5) -> list:
        return self.search("component_library", query_vector, limit)

    def search_similar_code(self, query_vector: list, limit: int = 5) -> list:
        return self.search("code_store", query_vector, limit)

    def search_design_patterns(self, query_vector: list, limit: int = 3) -> list:
        return self.search("design_pattern", query_vector, limit)

    def search_error_fix(self, query_vector: list, limit: int = 3) -> list:
        return self.search("error_pattern", query_vector, limit)

    def search_framework_api(self, query_vector: list, limit: int = 5) -> list:
        return self.search("framework_api", query_vector, limit)

    # ========== 数据入库 ==========

    def insert_code(self, code_files: list, app_id: str,
                    code_gen_type: str, tags: str = ""):
        """将生成的代码入库（构建成功后调用）"""
        self.connect()
        self.ensure_collection("code_store")
        print(f"[Milvus] 预留: insert_code({len(code_files)} files) — 需 embedding 支持")

    def insert_one(self, collection_name: str, data: dict):
        """单条数据入库"""
        self.connect()
        self.ensure_collection(collection_name)
        self._client.insert(collection_name=collection_name, data=data)

    # ========== 数据删除 / 查询 ==========

    def delete_by_expr(self, collection_name: str, expr: str) -> int:
        """按过滤表达式删除。返回删除数量。

        expr 使用 Milvus 表达式语法，例如:
            'app_id == "x" && file_path == "y"'
        """
        self.connect()
        if collection_name not in self._client.list_collections():
            return 0
        result = self._client.delete(collection_name=collection_name, filter=expr)
        if isinstance(result, dict):
            return result.get("delete_count", 0)
        return 0

    def query(self, collection_name: str, expr: str,
              output_fields: list | None = None, limit: int = 100) -> list[dict]:
        """按过滤表达式查询实体。

        Args:
            collection_name: Collection 名称
            expr: Milvus 过滤表达式
            output_fields: 要返回的字段列表，默认使用 OUTPUT_FIELDS_MAP 中的字段
            limit: 最大返回条数

        Returns:
            实体字典列表
        """
        self.connect()
        if collection_name not in self._client.list_collections():
            return []
        if output_fields is None:
            output_fields = self.OUTPUT_FIELDS_MAP.get(collection_name, ["*"])
        results = self._client.query(
            collection_name=collection_name,
            filter=expr,
            output_fields=output_fields,
            limit=limit,
        )
        return results or []

    # ========== 内部方法 ==========

    def _load_collection(self, collection_name: str):
        # MilvusClient handles load automatically in most cases.
        # Keep for explicit load when needed (standalone mode).
        try:
            if self._mode == "standalone" and self._client:
                self._client.load_collection(collection_name)
        except Exception:
            pass

    def _cleanup(self):
        """删除数据库文件（仅用于测试重置）"""
        if self._mode == "lite":
            db_dir = os.path.dirname(self.db_path)
            if os.path.exists(db_dir):
                shutil.rmtree(db_dir, ignore_errors=True)
        elif self._client:
            for name in self.COLLECTIONS:
                try:
                    self._client.drop_collection(name)
                except Exception:
                    pass

    def close(self):
        if self._executor:
            self._executor.shutdown(wait=False)

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


# 全局单例
milvus_store = MilvusStore()
