"""Provider-independent RAG seed-data entrypoint."""

from rag.embedding_service import embedding_service
from rag.seed_chunking import expand_seed_record
from rag.seed_data import (
    COMPONENT_LIBRARY_SEEDS,
    DESIGN_PATTERN_SEEDS,
    ERROR_PATTERN_SEEDS,
    FRAMEWORK_API_SEEDS,
)
from rag.sqlite_store import sqlite_store
from rag.vector_store import vector_store


def seed_collection(
    collection_name: str,
    data: list[dict],
    text_field: str,
) -> tuple[int, int]:
    vector_store.connect()
    vector_store.ensure_collection(collection_name)

    inserted_count = 0
    failed_count = 0
    for item in data:
        if collection_name == "component_library":
            records = expand_seed_record(
                item,
                name_field="component_name",
                content_field=text_field,
                max_chars=1200,
            )
        else:
            records = [dict(item)]

        for record in records:
            text = record.get(text_field, "")
            if not text:
                continue

            name = (
                record.get("api_name")
                or record.get("component_name")
                or record.get("pattern_name")
                or record.get("error_signature")
                or "?"
            )
            try:
                vector = embedding_service.embed(text)
            except Exception as exc:
                print(f"  [SKIP] embed 失败: {name}: {exc}")
                failed_count += 1
                continue

            try:
                vector_store.insert_one(
                    collection_name,
                    {
                        "vector": vector,
                        **{
                            key: value
                            for key, value in record.items()
                            if key != "vector"
                        },
                    },
                )
                inserted_count += 1
            except Exception as exc:
                print(f"  [FAIL] {name}: {exc}")
                failed_count += 1

    print(
        f"  {collection_name}: {inserted_count} 条向量 / "
        f"{len(data)} 个原始条目 / {failed_count} 条失败"
    )
    return inserted_count, failed_count


def main() -> None:
    print("=" * 50)
    print("RAG 种子数据入库")
    print("=" * 50)
    vector_store.init_collections()

    seed_jobs = [
        ("framework_api", FRAMEWORK_API_SEEDS, "example"),
        ("component_library", COMPONENT_LIBRARY_SEEDS, "code_snippet"),
        ("design_pattern", DESIGN_PATTERN_SEEDS, "description"),
        ("error_pattern", ERROR_PATTERN_SEEDS, "fix_code"),
    ]
    total_failures = 0
    for index, (collection_name, records, text_field) in enumerate(
        seed_jobs,
        start=1,
    ):
        print(f"\n[{index}/{len(seed_jobs)}] {collection_name}")
        _, failed_count = seed_collection(
            collection_name,
            records,
            text_field,
        )
        total_failures += failed_count

    print("\n[SQLite] 同步写入 FTS5 索引")
    sqlite_store.seed_all(
        FRAMEWORK_API_SEEDS,
        COMPONENT_LIBRARY_SEEDS,
        ERROR_PATTERN_SEEDS,
    )

    print("\n向量集合统计:")
    for collection_name, _, _ in seed_jobs:
        try:
            print(
                f"  {collection_name}: "
                f"{vector_store.count(collection_name)} 条"
            )
        except Exception as exc:
            print(f"  {collection_name}: 统计失败: {exc}")
            total_failures += 1

    if total_failures:
        print(f"\n入库存在 {total_failures} 条失败记录")
        raise SystemExit(1)

    print("\n全部入库完成！")


if __name__ == "__main__":
    main()
