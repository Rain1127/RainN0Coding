# Milvus 向量数据库 — 安装与使用指南

> 当前使用：Milvus Lite 3.0（本地文件模式，无需 Docker）
> 备选方案：Milvus 2.4.0 Standalone（Docker Compose）
> Python SDK：pymilvus 3.0

---

## 零、当前方案：Milvus Lite（推荐用于开发）

### 安装

```bash
uv add milvus-lite
# 自动安装依赖：pymilvus, faiss-cpu, pyarrow
```

### 使用

```python
from pymilvus import MilvusClient

# 数据库文件路径
client = MilvusClient("./milvus_data/milvus_lite.db")

# 创建 Collection
client.create_collection(
    collection_name="docs",
    dimension=768,
    metric_type="COSINE",
)

# 插入
data = [{"id": 1, "vector": [0.1]*768, "text": "hello"}]
client.insert(collection_name="docs", data=data)

# 检索
results = client.search(
    collection_name="docs",
    data=[[0.1]*768],
    limit=5,
)
```

### 与 Standalone 的区别

| 功能 | Milvus Lite | Milvus Standalone |
|---|---|---|
| 安装 | `pip install` | Docker Compose |
| 数据存储 | 本地文件 (.db) | MinIO (S3) |
| 分布式 | 不支持 | 支持 |
| API | 完全兼容 pymilvus | 完全兼容 pymilvus |
| 适用场景 | 开发/测试/小规模 | 生产/大规模 |

### 已知问题

- Windows 下 `drop_collection` 偶尔报 `os.rename` 错误 → 手动删除 `.db` 文件夹重置
- 每个 Collection 的所有数据存入同一个 `.db` 文件

---

## 一、启动 Milvus

### 1.1 确认 Docker 运行

```bash
docker version
# 确认看到 Server 版本信息
```

如果报 `docker daemon is not running`，打开 **Docker Desktop** 等待左下角变绿。

### 1.2 启动服务

```bash
cd milvus
docker compose up -d
```

首次启动会拉取 3 个镜像（约 2GB），成功后输出：

```
[+] Running 4/4
 ✔ Network milvus_default     Created
 ✔ Container milvus-etcd      Healthy
 ✔ Container milvus-minio     Healthy
 ✔ Container milvus-standalone Started
```

### 1.3 验证

```bash
docker compose ps
# 三容器均为 Up / Healthy

curl http://localhost:9091/healthz
# 返回 "OK"
```

### 1.4 停止

```bash
docker compose down          # 停止 + 保留数据
docker compose down -v       # 停止 + 删除数据（重置）
```

---

## 二、核心概念

| 概念 | 类比 SQL | 说明 |
|---|---|---|
| **Collection** | Table | 存储同类数据的集合，定义字段 schema |
| **Entity** | Row | 一条数据记录 |
| **Field** | Column | 字段，分标量字段和向量字段 |
| **Vector Field** | — | 向量字段，存 embedding 向量 |
| **Index** | Index | 向量索引，加速相似度检索 |
| **Partition** | Partition | 分区，用于数据隔离和快速删除 |

---

## 三、Python 连接与操作

### 3.1 连接

```python
from pymilvus import connections

connections.connect(
    alias="default",
    host="localhost",
    port="19530",
)
```

### 3.2 创建 Collection

```python
from pymilvus import Collection, CollectionSchema, FieldSchema, DataType

# 定义字段
fields = [
    FieldSchema("id", DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema("text", DataType.VARCHAR, max_length=1000),
    FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=768),  # 维度取决于 embedding 模型
]

schema = CollectionSchema(fields, description="文本向量库")
collection = Collection(name="docs", schema=schema)

# 创建向量索引（必须——否则无法检索）
index_params = {
    "metric_type": "COSINE",      # 相似度算法: COSINE / IP / L2
    "index_type": "IVF_FLAT",     # 索引类型: IVF_FLAT / IVF_SQ8 / HNSW
    "params": {"nlist": 128},     # 聚类数（数据量大时调大）
}
collection.create_index(field_name="embedding", index_params=index_params)
```

### 3.3 插入数据

```python
import numpy as np

entities = [
    [1.0, 2.0, 3.0, ...],   # embedding 1 (768 维)
    [4.0, 5.0, 6.0, ...],   # embedding 2
]
data = {
    "text": ["文档内容A", "文档内容B"],
    "embedding": entities,
}
collection.insert(data)
collection.flush()  # 确保持久化
```

### 3.4 相似度检索

```python
collection.load()  # 加载到内存（必须）

query_vector = [[0.1, 0.2, 0.3, ...]]  # 查询向量

results = collection.search(
    data=query_vector,
    anns_field="embedding",
    param={"metric_type": "COSINE", "params": {"nprobe": 16}},
    limit=5,                       # 返回 Top 5
    output_fields=["text"],        # 返回哪些标量字段
)

for hits in results:
    for hit in hits:
        print(f"id={hit.id}, distance={hit.distance:.4f}, text={hit.entity.get('text')[:50]}")
```

### 3.5 删除 Collection

```python
from pymilvus import utility
utility.drop_collection("docs")
```

---

## 四、索引选择速查

| 索引类型 | 场景 | 精度 | 速度 | 内存 |
|---|---|---|---|---|
| **FLAT** | <10 万条，精度优先 | 100% | 慢 | 低 |
| **IVF_FLAT** | 10万~1000万，均衡 | ~95% | 中 | 中 |
| **IVF_SQ8** | 同上，内存受限 | ~90% | 中 | 低 |
| **IVF_PQ** | >1000 万，速度优先 | ~80% | 快 | 极低 |
| **HNSW** | 高精度 + 实时写入 | ~98% | 快 | 高 |

本项目的代码生成场景推荐 **IVF_FLAT**（数据量 <100 万，精度要求高）。

---

## 五、本项目中的 Collections

| Collection | 用途 | 向量维度 |
|---|---|---|
| `code_store` | 历史成功项目代码 | 768 |
| `component_library` | 可复用 Vue 组件 | 768 |
| `design_pattern` | 设计模式库 | 768 |
| `error_pattern` | 常见错误与修复 | 768 |
| `framework_api` | Vue 3 API 参考文档 | 768 |

每个 Collection 的 schema 见 `python-agent/rag/milvus_client.py`。

---

## 六、常见问题

### Q: 启动时端口冲突

```
Error: port 19530 is already in use
```

解决：修改 `docker-compose.yml` 中 `ports` 映射为 `19531:19530`

### Q: pymilvus 连接超时

```python
connections.connect(host="localhost", port="19530", timeout=10)
```

确保 Docker 正在运行 + 端口映射正确。

### Q: search 报 "collection not loaded"

```python
collection.load()  # 每次 search 之前必须先 load
```

### Q: 内存不足

Milvus Standalone 需要预留约 4GB 内存。如果 Docker Desktop 只分配了 2GB：
- Docker Desktop → Settings → Resources → Memory → 调至 6GB+

### Q: 数据量很小还要建索引吗？

要。不建索引 = 无法检索。FLAT 是最简索引（不做压缩，精度 100%）。

---

## 七、版本说明

| 组件 | 版本 | 稳定性 |
|---|---|---|
| Milvus | 2.4.0 | 生产可用 |
| pymilvus | 3.0.0 | 匹配 Milvus 2.4 |
| etcd | 3.5.5 | 稳定 |
| MinIO | RELEASE.2023-03 | 稳定 |

**为什么是 v2.4.0 而不是最新版？**
- v2.4.x 是当前最广泛使用的稳定大版本
- pymilvus 3.0 与 Milvus 2.4 API 完全兼容
- v2.5+ 有一些 API 变更，pymilvus 3.x 配合使用时需额外适配
