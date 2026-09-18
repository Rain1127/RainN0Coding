# LiteLLM 小服务器增量上线设计

日期：2026-09-18

## 目标

把 `codex/litellm-gateway` 的模型网关实现合入当前 `main`，并在现有腾讯云单机拓扑上上线 LiteLLM。上线后 Python Agent 只访问 LiteLLM 的业务别名，不再持有或直连 DeepSeek、智谱供应商端点；现有 Kafka 队列、暂停恢复、MySQL、Redis、Qdrant、监控和发布目录保持工作。

## 现状与约束

- 当前线上发布为 `/opt/rainn0coding/releases/20260917-main-bfd24e5b`。
- Java 与 Python 由 systemd 单实例运行；MySQL、Redis、Qdrant、Kafka 和监控组件由 Docker 运行。
- 数据容器位于 `rainn0coding-cloud_default` 私有网络；Python 监听 `127.0.0.1:8000`。
- 服务器有约 1402 MiB 可用内存、38 GiB 可用磁盘，并已使用 swap。上线不能整体迁移应用容器，也不能重建现有数据卷。
- 供应商密钥、LiteLLM master key、salt key、数据库密码和 Virtual Key 不进入 Git、日志或验收输出。

## 选定架构

沿用现有混合部署，只新增两个容器：

1. `rainn0coding-postgres`：保存 LiteLLM 控制面、虚拟密钥、预算和消费记录，使用独立持久卷，不发布主机端口。
2. `rainn0coding-litellm`：使用仓库固定版本和配置，连接 PostgreSQL 与现有 Redis，只发布 `127.0.0.1:4000`。

两个容器加入 `rainn0coding-cloud_default`。systemd Python Agent 通过 `http://127.0.0.1:4000/v1` 调用 LiteLLM，使用仅允许 `code-reasoning`、`code-structured`、`code-lightweight` 的 Virtual Key。Java、前端和 Python 的内部鉴权边界不改变。

建议资源上限：PostgreSQL 256 MiB，LiteLLM 512 MiB；两者启用 restart policy。上线后以实际空闲内存、swap、OOM 计数和请求延迟决定是否调整，不从单次快照推导容量承诺。

## 密钥迁移

发布脚本在服务器受限目录生成 LiteLLM 专用环境文件，权限为 root/rainn0coding 可读且不回显值。初始供应商 Key 从现有 `/etc/rainn0coding/python.env` 复制到该文件，不在本地落盘。

LiteLLM 健康后用 master key 创建受限 Virtual Key，并把它写入新的 Python 环境文件。只有在网关模型列表和真实小请求成功后，才从 Python 环境删除供应商 Key。原环境文件先做权限受限备份，回滚时恢复。

## 发布流程

1. 确认当前 Git、服务、容器、Kafka lag、未完成任务和磁盘/内存状态。
2. 备份当前发布清单、Python 环境、MySQL、检查点目录和现有代码输出；保留当前 release 与数据卷。
3. 构建并校验合并后的 Python 发布包；不覆盖当前 release。
4. 拉取固定 PostgreSQL/LiteLLM 镜像，创建独立卷和受限环境文件。
5. 启动 PostgreSQL，再启动 LiteLLM；验证容器健康、端口仅绑定回环、模型别名和指标。
6. 创建受限 Virtual Key，写入候选 Python 环境。
7. 暂停新队列认领并等待当前任务排空；原子切换 `current` 软链接和 Python 环境，重启 Python。Java/Kafka/数据容器不重启。
8. 验证 Python、Java、Kafka、页面、暂停恢复状态查询和真实端到端生成。确认 LiteLLM 记录请求归属且 Python 没有供应商直连配置。
9. 解除队列维护锁，观察服务日志、内存、swap、OOM 和队列指标。

## 失败处理与回滚

- PostgreSQL或 LiteLLM 未健康：不切换 Python，停止新容器并保留卷供排查。
- Python 启动或健康检查失败：恢复原 Python 环境与 `current` 软链接，重启 Python；LiteLLM 容器可保留但不承载流量。
- 端到端生成失败：停止新任务，收集不含密钥/Prompt/生成代码的诊断，回滚 Python；不得让 Python 临时绕过网关直连供应商。
- 回滚不删除 PostgreSQL、LiteLLM 数据卷、Kafka 数据、检查点、MySQL 或代码输出。确认恢复健康后再决定是否停用新容器。

## 验收标准

- 合并结果通过 Python 网关、暂停恢复、并发占用、Guardrails 和禁止供应商直连测试；LiteLLM fallback 契约、前端全量测试/构建、Java 测试/打包通过。
- `main` 与 `origin/main` 指向同一个合并提交，发布目录和服务器证据记录该提交。
- LiteLLM/PostgreSQL 容器健康，4000 只监听 `127.0.0.1`，数据库无公开端口。
- Python 健康接口报告 LiteLLM 可达；三个业务别名可见，受限 Virtual Key 可调用且不能访问未授权模型。
- 一次真实平台生成完成，SSE、文件保存、Builder、聊天记录、Kafka 最终状态和 LiteLLM SpendLogs/指标可关联同一请求。
- Python 环境不再包含供应商 Key；重启 LiteLLM 与 Python 后健康和受限调用仍通过。
- 回滚命令、备份路径、镜像 digest、发布 SHA256、资源快照和已知限制写入验收记录。

## 非目标

- 不把 Java、Python、前端、Kafka或现有数据服务迁移为新的全容器栈。
- 不承诺多主机高可用、跨主机 exactly-once、HTTPS、域名或新的公网端口。
- 不在此次上线中删除旧 LiteLLM 全容器部署资产；其适用范围继续由文档区分。
