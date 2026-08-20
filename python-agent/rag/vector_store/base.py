from typing import Protocol, runtime_checkable


FilterMap = dict[str, object]


@runtime_checkable
class VectorStore(Protocol):
    def connect(self) -> None:
        pass

    def init_collections(self) -> None:
        pass

    def ensure_collection(self, collection_name: str) -> None:
        pass

    def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        output_fields: list[str] | None = None,
    ) -> list[dict]:
        pass

    def search_multi(
        self,
        queries: list[tuple],
    ) -> list[list[dict]]:
        pass

    async def search_async(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        output_fields: list[str] | None = None,
    ) -> list[dict]:
        pass

    async def search_multi_async(
        self,
        queries: list[tuple],
    ) -> list[list[dict]]:
        pass

    def insert_one(
        self,
        collection_name: str,
        data: dict,
    ) -> None:
        pass

    def delete_by_filters(
        self,
        collection_name: str,
        filters: FilterMap,
    ) -> int:
        pass

    def query_by_filters(
        self,
        collection_name: str,
        filters: FilterMap,
        output_fields: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        pass

    def count(self, collection_name: str) -> int:
        pass

    def reset_all(self) -> None:
        pass

    def close(self) -> None:
        pass