"""
种子数据入库脚本

将 seed_data.py 中的 Vue 3 / Router / Pinia / Tailwind API 文档、
组件模板、设计模式、常见错误模式写入 Milvus + SQLite FTS5。

用法:
    .venv/Scripts/python.exe rag/seed_milvus.py
"""
from rag.embedding_service import embedding_service
from rag.milvus_client import milvus_store
from rag.sqlite_store import sqlite_store
from rag.seed_chunking import expand_seed_record
from rag.seed_data import (
    FRAMEWORK_API_SEEDS,
    COMPONENT_LIBRARY_SEEDS,
    DESIGN_PATTERN_SEEDS,
    ERROR_PATTERN_SEEDS,
)


def seed_collection(collection_name: str, data: list[dict], text_field: str):
    """
    将数据列表批量入库到指定 Collection。

    Args:
        collection_name: Milvus Collection 名称
        data: 种子数据列表
        text_field: 用于生成 embedding 的字段名（如 'example' 或 'description'）
    """
    milvus_store.connect()
    milvus_store.ensure_collection(collection_name)

    inserted_count = 0
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

            try:
                vec = embedding_service.embed(text)
            except Exception as e:
                print(f"  [SKIP] embed 失败: {record.get('api_name', record.get('component_name', record.get('pattern_name', '?')))}: {e}")
                continue

            try:
                milvus_store.insert_one(collection_name, {
                    "vector": vec,
                    **{k: v for k, v in record.items() if k not in ("vector",)},
                })
                inserted_count += 1
            except Exception as e:
                name = record.get('api_name') or record.get('component_name') or record.get('pattern_name') or record.get('error_signature') or '?'
                print(f"  [FAIL] {name}: {e}")

    print(f"  {collection_name}: {inserted_count} 条向量 / {len(data)} 个原始条目")


def main():
    print("=" * 50)
    print("RAG 种子数据入库")
    print("=" * 50)

    print("\n[1/4] framework_api — Vue 3 / Router / Pinia / Tailwind API 参考")
    seed_collection("framework_api", FRAMEWORK_API_SEEDS, "example")

    print("\n[2/4] component_library — 可复用组件骨架")
    seed_collection("component_library", COMPONENT_LIBRARY_SEEDS, "code_snippet")

    print("\n[3/4] design_pattern — 常见 UI 架构模式")
    seed_collection("design_pattern", DESIGN_PATTERN_SEEDS, "description")

    print("\n[4/4] error_pattern — 高频错误与修复")
    seed_collection("error_pattern", ERROR_PATTERN_SEEDS, "fix_code")

    print("\n" + "=" * 50)
    print("Milvus 入库完成！")
    print("=" * 50)

    # === SQLite FTS5 同步写入 ===
    print("\n[SQLite] 同步写入 FTS5 索引...")
    sqlite_store.seed_all(FRAMEWORK_API_SEEDS, COMPONENT_LIBRARY_SEEDS, ERROR_PATTERN_SEEDS)

    print("\n" + "=" * 50)
    print("全部入库完成！")
    print("=" * 50)

    # 打印统计
    from config import config
    if config.MILVUS_MODE == "lite":
        import os
        from pymilvus import MilvusClient
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "milvus_data", "milvus_lite.db")
        client = MilvusClient(db_path)
    else:
        from pymilvus import MilvusClient
        client = MilvusClient(uri=f"http://{config.MILVUS_HOST}:{config.MILVUS_PORT}")
    for col in ["framework_api", "component_library", "design_pattern", "error_pattern"]:
        try:
            client.load_collection(col)
            stats = client.get_collection_stats(col)
            print(f"  {col}: {stats.get('row_count', '?')} 条")
        except Exception:
            print(f"  {col}: 统计失败")


if __name__ == "__main__":
    main()
