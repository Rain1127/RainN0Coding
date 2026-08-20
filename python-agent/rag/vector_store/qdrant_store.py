import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4

from qdrant_client import QdrantClient, models

from config import config


logger = logging.getLogger(__name__)


class QdrantStore:
    COLLECTIONS = {
        "code_store": 512,
        "component_library": 512,
        "design_pattern": 512,
        "error_pattern": 512,
        "framework_api": 512,
    }

    OUTPUT_FIELDS_MAP = {
        "code_store": [
            "app_id",
            "file_path",
            "content",
            "code_gen_type",
            "tags",
        ],
        "component_library": [
            "component_name",
            "props_schema",
            "code_snippet",
            "framework",
            "use_count",
        ],
        "design_pattern": [
            "pattern_name",
            "description",
            "example_code",
            "best_for",
        ],
        "error_pattern": [
            "error_signature",
            "fix_code",
            "occurrence_count",
        ],
        "framework_api": [
            "api_name",
            "signature",
            "import_statement",
            "example",
            "framework",
        ],
    }

    def __init__(self, client: QdrantClient | None = None):
        self._client = client or QdrantClient(
            url=config.QDRANT_URL,
            api_key=config.QDRANT_API_KEY or None,
            timeout=config.QDRANT_TIMEOUT_SECONDS,
        )
        self._connected = False
        self._executor = ThreadPoolExecutor(
            max_workers=config.RAG_PARALLEL_WORKERS,
            thread_name_prefix="qdrant",
        )

    def connect(self) -> None:
        if self._connected:
            return

        self._client.get_collections()
        self._connected = True

    def init_collections(self) -> None:
        self.connect()
        for collection_name in self.COLLECTIONS:
            self.ensure_collection(collection_name)

    def ensure_collection(self, collection_name: str) -> None:
        self.connect()
        if self._client.collection_exists(collection_name=collection_name):
            return

        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=self.COLLECTIONS.get(collection_name, 512),
                distance=models.Distance.COSINE,
            ),
        )

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        output_fields: list[str] | None = None,
    ) -> list[dict]:
        self.connect()
        if not self._client.collection_exists(
            collection_name=collection_name
        ):
            return []

        payload_selector = (
            output_fields
            or self.OUTPUT_FIELDS_MAP.get(collection_name)
            or True
        )
        response = self._client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=limit,
            with_payload=payload_selector,
        )

        return [
            {
                "id": point.id,
                "distance": float(point.score),
                "entity": dict(point.payload or {}),
            }
            for point in response.points
        ]

    def search_multi(
        self,
        queries: list[tuple],
    ) -> list[list[dict]]:
        if not queries:
            return []

        futures = {}
        for index, query in enumerate(queries):
            collection_name = query[0]
            query_vector = query[1]
            limit = query[2] if len(query) > 2 else 5
            output_fields = query[3] if len(query) > 3 else None
            future = self._executor.submit(
                self.search,
                collection_name,
                query_vector,
                limit,
                output_fields,
            )
            futures[future] = index

        results: list[list[dict]] = [[] for _ in queries]
        for future in as_completed(futures):
            index = futures[future]
            try:
                results[index] = future.result()
            except Exception as exc:
                logger.warning("Qdrant search failed: %s", exc)
                results[index] = []
        return results

    async def search_async(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        output_fields: list[str] | None = None,
    ) -> list[dict]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self.search,
            collection_name,
            query_vector,
            limit,
            output_fields,
        )

    async def search_multi_async(
        self,
        queries: list[tuple],
    ) -> list[list[dict]]:
        if not queries:
            return []

        tasks = [
            self.search_async(
                query[0],
                query[1],
                query[2] if len(query) > 2 else 5,
                query[3] if len(query) > 3 else None,
            )
            for query in queries
        ]
        raw_results = await asyncio.gather(
            *tasks,
            return_exceptions=True,
        )
        return [
            result if isinstance(result, list) else []
            for result in raw_results
        ]

    def insert_one(
        self,
        collection_name: str,
        data: dict,
    ) -> None:
        self.ensure_collection(collection_name)

        record = dict(data)
        vector = record.pop("vector", None)
        if vector is None:
            raise ValueError("data must contain vector")

        self._client.upsert(
            collection_name=collection_name,
            points=[
                models.PointStruct(
                    id=str(uuid4()),
                    vector=vector,
                    payload=record,
                )
            ],
            wait=True,
        )

    @staticmethod
    def _build_filter(
        filters: dict[str, object],
    ) -> models.Filter:
        if not filters:
            raise ValueError("filters must not be empty")

        return models.Filter(
            must=[
                models.FieldCondition(
                    key=field,
                    match=models.MatchValue(value=value),
                )
                for field, value in filters.items()
            ]
        )

    def delete_by_filters(
        self,
        collection_name: str,
        filters: dict[str, object],
    ) -> int:
        self.connect()
        if not self._client.collection_exists(
            collection_name=collection_name
        ):
            return 0

        query_filter = self._build_filter(filters)
        matched = self._client.count(
            collection_name=collection_name,
            count_filter=query_filter,
            exact=True,
        ).count
        self._client.delete(
            collection_name=collection_name,
            points_selector=models.FilterSelector(filter=query_filter),
            wait=True,
        )
        return int(matched)

    def query_by_filters(
        self,
        collection_name: str,
        filters: dict[str, object],
        output_fields: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        self.connect()
        if not self._client.collection_exists(
            collection_name=collection_name
        ):
            return []

        points, _ = self._client.scroll(
            collection_name=collection_name,
            scroll_filter=self._build_filter(filters),
            limit=limit,
            with_payload=output_fields or True,
            with_vectors=False,
        )
        return [
            {"id": point.id, **dict(point.payload or {})}
            for point in points
        ]

    def count(self, collection_name: str) -> int:
        self.connect()
        if not self._client.collection_exists(
            collection_name=collection_name
        ):
            return 0

        result = self._client.count(
            collection_name=collection_name,
            exact=True,
        )
        return int(result.count)

    def reset_all(self) -> None:
        self.connect()
        for collection_name in self.COLLECTIONS:
            if self._client.collection_exists(
                collection_name=collection_name
            ):
                self._client.delete_collection(
                    collection_name=collection_name
                )

    def close(self) -> None:
        self._executor.shutdown(wait=False)
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
        self._connected = False
