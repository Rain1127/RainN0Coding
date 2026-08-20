# Milvus / Qdrant 双向量存储改造设计

日期：2026-08-20

## 1. 目标

在 Python Agent 中引入统一的向量存储边界，使现有 RAG 流程可以通过环境变量选择 Milvus 或 Qdrant。迁移期间保留 Milvus 和 Milvus Lite，不迁移旧 Milvus 数据；Qdrant 数据通过现有种子数据重新生成 Embedding 后写入。

本阶段只完成本地代码改造和本地 Docker Qdrant 验证，不包含腾讯云部署。

## 2. 使用方式与约束

- 用户亲自执行每一步代码修改和命令，Codex 每次只指导一个步骤并检查结果。
- 本地 Qdrant 通过 Docker 容器运行。
- 默认后端继续使用 Milvus，避免改造过程中改变现有行为。
- 上层检索、去重、重排和提示词组装不感知具体数据库。
- 不修改与本次迁移无关的代码和用户未提交改动。
- 依赖只修改 `python-agent/pyproject.toml`，不修改工作区根目录已有改动的 `pyproject.toml`。

## 3. 方案选择

采用“统一接口 + 两个适配器 + 工厂”的结构：

```text
RetrievalEngine
      |
VectorStore 统一接口
      |
VectorStoreFactory
   +-- MilvusStore
   +-- QdrantStore
```

不在现有 `MilvusStore` 中堆叠数据库分支，也不让上层模块直接调用 Qdrant 客户端。

## 4. 组件设计

计划引入以下结构：

```text
python-agent/
|-- rag/vector_store/
|   |-- base.py
|   |-- factory.py
|   |-- milvus_store.py
|   `-- qdrant_store.py
|-- rag/seed_vector_store.py
|-- config.py
|-- .env.example
`-- tests/
    |-- test_vector_store_contract.py
    |-- test_vector_store_factory.py
    `-- test_qdrant_store.py
```

### 4.1 VectorStore 接口

统一接口覆盖当前实际需要的操作：

- `connect()`
- `init_collections()`
- `ensure_collection(collection_name)`
- `search(collection_name, query_vector, limit, output_fields)`
- `search_multi(queries)`
- `search_async(collection_name, query_vector, limit, output_fields)`
- `search_multi_async(queries)`
- `insert_one(collection_name, data)`
- 查询、删除和重置所需的通用操作

不把 Milvus 表达式语法定义成通用接口的一部分。查询和删除条件使用结构化字段过滤；Milvus 和 Qdrant 适配器分别将其转换为各自的过滤语法。

### 4.2 工厂

`VectorStoreFactory` 读取 `VECTOR_DB_PROVIDER`：

- `milvus`：创建 `MilvusStore`
- `qdrant`：创建 `QdrantStore`
- 其他值：立即抛出明确的配置错误

不执行数据库自动回退，避免读写落到不同数据库。

### 4.3 Qdrant 数据模型

保留五个集合：

- `framework_api`
- `component_library`
- `design_pattern`
- `error_pattern`
- `code_store`

每个集合使用：

- 512 维向量
- Cosine 距离
- 客户端生成的 UUID Point ID
- `vector` 字段写入 Qdrant 向量
- 其他业务字段写入 Payload

Qdrant 命中结果统一转换成现有 RAG 需要的格式：

```python
{
    "id": point.id,
    "distance": point.score,
    "entity": point.payload,
}
```

这保证 `retrieval_engine.py`、`semantic_engine.py` 及后处理逻辑继续使用 `distance` 和 `entity`。

## 5. 配置设计

默认配置：

```env
VECTOR_DB_PROVIDER=milvus
```

本地 Qdrant 配置：

```env
VECTOR_DB_PROVIDER=qdrant
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_TIMEOUT_SECONDS=10
```

现有 `MILVUS_MODE`、`MILVUS_HOST` 和 `MILVUS_PORT` 在 Milvus 后端下继续生效。

未来上云时只替换 `QDRANT_URL` 和认证信息；云端 Qdrant 端口不得直接暴露公网。

## 6. 种子数据流程

新增数据库无关的 `rag/seed_vector_store.py`：

```text
读取 seed_data
  -> 按现有规则分块
  -> 生成 Embedding
  -> vector_store.insert_one()
  -> 同步写入 SQLite FTS5
  -> 输出各集合统计
```

原 `seed_milvus.py` 暂时作为兼容入口，转调新脚本并提示旧入口将被弃用。Qdrant 不读取旧 Milvus 数据，也不提供 Milvus 到 Qdrant 的迁移脚本。

种子脚本必须能区分完整成功、部分失败和连接失败，不能在写入失败时输出成功结论。

## 7. 错误处理与降级

- Provider 配置错误：启动失败并指出允许值。
- Qdrant 连接失败：健康状态标记为不可用，不自动切到 Milvus。
- 普通 RAG 查询失败：记录结构化错误，向上层返回空检索结果，使可降级的 RAG 阶段不阻断核心代码生成。
- 种子写入失败：脚本返回非零状态并打印失败集合与记录标识。
- 单条写入失败：保留集合名、记录标识和异常信息。
- Qdrant 重启：从持久化 Docker Volume 恢复数据。

## 8. 测试设计

### 8.1 单元测试

1. 工厂根据 Provider 返回正确适配器。
2. 非法 Provider 明确失败。
3. 两个适配器满足相同接口契约。
4. Qdrant命中结果转换为 `id + distance + entity`。
5. 种子分块、Embedding输入和Payload字段与现有行为一致。
6. Qdrant异常不会触发隐式Milvus回退。

### 8.2 本地集成测试

使用真实Docker Qdrant验证：

1. 健康检查。
2. 创建五个集合。
3. 插入测试向量与Payload。
4. Cosine相似度搜索。
5. 字段过滤查询和删除。
6. 多集合并行搜索。
7. 执行种子脚本并核对记录数量。
8. 重启容器后再次查询，验证持久化。

### 8.3 回归测试

1. 运行现有RAG和种子分块测试。
2. Provider设为Qdrant，验证上层检索流程。
3. Provider切回Milvus Lite，验证原功能未被破坏。

## 9. 本地Docker边界

本地Qdrant使用单容器和持久化Volume。开发阶段只映射本机端口 `6333`；云端安全策略不属于本阶段。

容器配置必须固定明确的Qdrant版本，避免使用浮动的 `latest` 造成后续行为漂移。

## 10. 验收标准

- Qdrant健康检查成功。
- 五个集合全部创建且维度、距离类型正确。
- 现有种子数据完整写入Qdrant和SQLite FTS5。
- 已知查询能返回预期集合和Payload字段。
- RAG上层无需按数据库写分支。
- 相关单元测试、集成测试和现有回归测试通过。
- 切回Milvus Lite后原有检索仍然工作。
- Qdrant容器重启后数据不丢失。
- 本地改造阶段不包含腾讯云配置和公网开放。

## 11. 非目标

- 不迁移现有Milvus数据。
- 不删除Milvus或Milvus Lite依赖。
- 不修改Java后端和Vue前端。
- 不在本阶段部署腾讯云。
- 不引入自动数据库回退或双写。
- 不进行与向量存储边界无关的重构。
