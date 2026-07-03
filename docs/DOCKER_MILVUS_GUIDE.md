# Docker Desktop + Milvus Standalone 操作指南

> 本项目用 Docker 运行 Milvus 向量数据库。Docker 只需启动/停止，日常不用管。

---

## 一、Docker Desktop

### 1.1 启动

```bash
# 方式1: 开始菜单搜索 "Docker Desktop" 点开
# 方式2: 命令行启动
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
```

左下角图标变绿 = 就绪。首次启动需要 20~60 秒。

### 1.2 验证

```bash
docker ps
# 输出有 CONTAINER ID / IMAGE / STATUS 表头 = 正常
# 输出 "Error response from daemon" = 还没启动完，等一等
```

### 1.3 停止

Docker Desktop 图标右键 → Quit Docker Desktop。或者：

```bash
taskkill /F /IM "Docker Desktop.exe"
```

### 1.4 WSL2 未安装时报错

如果 `docker ps` 报 `Docker Desktop is unable to start`：

```bash
# 安装 WSL2（需要管理员权限的终端）
wsl --install

# 装完后重启电脑，Docker Desktop 就能用了
```

---

## 二、Milvus Standalone

所有命令在 `milvus/` 目录下执行：

```bash
cd D:/code/RainN0Coding/milvus
```

### 2.1 启动

```bash
docker compose up -d
```

首次启动会下载 3 个镜像（约 2GB，只需一次）。成功后输出：

```
Container milvus-etcd      Started
Container milvus-minio     Started
Container milvus-standalone Started
```

### 2.2 查看状态

```bash
docker compose ps
```

三个容器都是 `Up` / `healthy` = 正常：

```
NAME                STATUS
milvus-etcd         Up (healthy)
milvus-minio        Up (healthy)
milvus-standalone   Up (healthy)
```

### 2.3 验证连接

```bash
curl http://localhost:9091/healthz
# 返回 "OK" = Milvus 就绪
```

Python 验证：

```bash
cd D:/code/RainN0Coding/python-agent
.venv/Scripts/python.exe -c "from pymilvus import MilvusClient; c = MilvusClient(uri='http://localhost:19530'); print(c.list_collections())"
```

### 2.4 停止

```bash
# 停止容器，保留数据（下次 start 数据还在）
docker compose down

# 停止容器 + 删除所有数据（重置到初始状态）
docker compose down -v
```

### 2.5 查看日志

```bash
# 所有容器日志
docker compose logs

# 只看 Milvus
docker compose logs milvus-standalone

# 实时跟踪（Ctrl+C 退出）
docker compose logs -f milvus-standalone
```

---

## 三、日常使用流程

```
1. 开机 → Docker Desktop 自动启动（如果设置了开机自启）
         没有的话手动开一下，等图标变绿

2. 启动 Milvus:
   cd D:/code/RainN0Coding/milvus
   docker compose up -d

3. 开发/测试 → 用 Python 连 localhost:19530

4. 关机前（可选，不关也行）:
   docker compose down
```

---

## 四、端口说明

| 端口 | 服务 | 用途 |
|---|---|---|
| 19530 | Milvus gRPC | Python pymilvus 连接 |
| 9091 | Milvus Metrics | 健康检查 / 监控 |
| 9000 | MinIO | 内部存储（不对开发者暴露） |
| 2379 | etcd | 内部元数据（不对开发者暴露） |

---

## 五、常见问题

### Q: `docker ps` 报 "Docker Desktop is unable to start"

**原因：** WSL2 未安装或 Docker Desktop 刚重启还在初始化。

**解决：**
```bash
# 1. 等 30 秒再试
sleep 30 && docker ps

# 2. 如果还是不行，检查 WSL2
wsl --status

# 3. 如果 WSL2 没装
wsl --install
# 重启电脑
```

### Q: `docker compose up -d` 报端口占用

```
Error: port 19530 is already in use
```

**原因：** 之前运行的 Milvus 容器没停，或别的程序占用了 19530。

**解决：**
```bash
# 停止旧容器
docker compose down

# 如果还报错，查谁占用了端口
netstat -ano | findstr 19530
# 记下 PID，去任务管理器结束它
```

### Q: Milvus 连接超时

```
pymilvus.exceptions.MilvusException: connection timeout
```

**原因：** Docker 在运行但 Milvus 容器没启动。

**解决：**
```bash
docker compose up -d
# 等 10 秒让容器就绪
sleep 10
```

### Q: 搜索报 "collection not loaded"

**原因：** Milvus Standalone 需要先 load Collection 到内存。

**解决：** 代码里已经处理了（`_load_collection`），如果手动操作：
```python
from pymilvus import MilvusClient
client = MilvusClient(uri="http://localhost:19530")
client.load_collection("code_store")  # 加载到内存
```

### Q: 想彻底重置（删除所有数据）

```bash
cd D:/code/RainN0Coding/milvus
docker compose down -v   # 删除容器 + 数据卷
docker compose up -d      # 重新创建
```

然后 Python 里重新 `init_collections()`。

### Q: 电脑内存不够

Milvus Standalone 默认占用约 4GB 内存。如果 Docker Desktop 只分配了 2GB：
- Docker Desktop → Settings → Resources → Memory → 调到 6GB+
- 或者换成 Milvus Lite 模式（不需要 Docker，`.env` 里设 `MILVUS_MODE=lite`）

---

## 六、两种模式切换

`.env` 文件中的 `MILVUS_MODE` 控制：

| 值 | 模式 | 需要 Docker | 适合 |
|---|---|---|---|
| `standalone` | Milvus Standalone | 是 | 生产 / 需要真正并行搜索 |
| `lite` | Milvus Lite | 否 | 开发 / Docker 不可用 |

切换到 Lite 模式：
```bash
# .env 中设置
MILVUS_MODE=lite

# 初始化（自动创建本地文件数据库）
cd D:/code/RainN0Coding/python-agent
.venv/Scripts/python.exe -c "from rag.milvus_client import milvus_store; milvus_store.connect(); milvus_store.init_collections()"
```
