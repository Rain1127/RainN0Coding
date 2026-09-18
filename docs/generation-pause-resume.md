# 生成任务暂停与恢复

用户点击暂停后显示“正在暂停”，当前 LangGraph 业务节点完成后，在下一个控制节点保存 checkpoint 并进入“已暂停”。继续使用原 run ID 和 `Command(resume=True)`，不会重新发送需求或重跑已经完成的业务节点。当前节点是 `fork_coder_and_images` 时，图片处理和代码生成一起完成后暂停。

## 部署

安装 `python-agent/pyproject.toml` 中的 `langgraph-checkpoint-sqlite` 依赖。云端使用现有单 worker FastAPI systemd 服务，设置：

```ini
Environment=CHECKPOINT_DB_PATH=/opt/rainn0coding/shared/checkpoints/generation.db
```

该目录由运行服务的账号拥有，必须位于版本发布目录之外。数据库包含完整代码与对话输入；使用私有文件权限，备份使用 SQLite backup API，不能在写入期间单独拷贝主数据库而遗漏 WAL。运行目录也包含每个应用的 OS 锁文件，不能在运行期间清理。

此实现适用于同一 Linux 主机上的本地持久化磁盘；不支持多个云主机通过各自 SQLite 文件接力，也不应把 SQLite/文件锁放在不保证锁语义的网络文件系统上。

## 接口

- 原生成请求：`GET /api/app/chat/gen/code`，UUID `Idempotency-Key` 成为 run ID。
- 暂停：`POST /api/app/chat/gen/pause`，JSON `{appId, runId}`。
- 继续：`GET /api/app/chat/gen/resume?appId=...&runId=...`，返回 SSE。
- 状态：`GET /api/app/chat/gen/status?appId=...&runId=...`。

所有控制操作校验登录用户和应用归属。前端仅在 localStorage 保存应用/run ID，以便刷新后重新查询状态。新任务不能覆盖同一应用的未完成任务；先恢复已有任务。已完成或失败任务不可再次续跑。

Python 内部接口分别是 `/api/generation/pause`、`/api/generation/status` 和 `/api/generate-code`（`resume: true`），全部沿用内部 token 校验。

## 可靠性边界

- `pausing` 表示请求已接收，只有 `done/status=paused` 表示检查点暂停完成。最后一个业务节点已完成时可直接正常结束。
- SSE 断线会请求暂停，后台仍持有应用锁和 Python 并发许可，直到当前节点完成并保存状态。锁由操作系统在进程退出时释放。
- 主动暂停后可重启服务并继续。进程在业务节点中途崩溃时，恢复会重新执行未完成节点；文件写入、外部 API 或模型计费不具备自动 exactly-once 保证。
- 恢复时会重发保存的代码文件，让 Java 新建的 SSE 处理链能保存完整结果。
- Redis 对话摘要属于附属效果，按 run ID 尽力写入一次；若进程在记录写入标记后崩溃，可能缺失摘要，不影响代码 checkpoint。
- 检查点跨代码升级要求兼容原有状态字段和节点名称。回滚应保留数据库和生成代码目录。

## 验证

```powershell
.\python-agent\.venv\Scripts\python.exe -m pytest python-agent/tests/test_generation_pause.py python-agent/tests/test_generation_pause_api.py -q
```

测试使用真实 LangGraph、SQLite 和新 Python 进程，验证节点计数、归属隔离、重复点击、断线后锁生命周期、SSE 恢复文件重放。上线后还需使用真实前端/API完成暂停、重启、继续的验收。
