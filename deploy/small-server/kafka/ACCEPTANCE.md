# Kafka 代码生成队列验收（2026-09-16）

范围：现有腾讯云服务器上的 AI 代码生成任务。单消费者执行，默认最多 100 个未完成任务，页面断线只关闭事件订阅，生成继续执行。保留原暂停、检查点与继续生成能力。

## 发布与恢复点

- 功能合并提交：`5cb115afbbfbee4b252a2e42f316decb8b2377cd`。
- 静态 HTML 预览修复提交：`736b977de96a121b28ea201e726753040ddd3064`。
- 最终发布目录：`/opt/rainn0coding/releases/20260916-kafka-queue-static`。
- 原发布保留：`/opt/rainn0coding/releases/20260910-pause-resume`；首次队列发布也保留在 `20260916-kafka-queue`。
- 两次发布分别备份于 `/home/ubuntu/rainn0coding-backups/<release>-before-queue`，含 MySQL、原 Java 环境配置和停止服务后归档的 shared 数据；未删除原数据、检查点或 Kafka 数据卷。
- Java SHA256：`592b91fda276be491957aec4719b076be5d7097ce487b94d702faecb9740ef25`。
- 最终 Python 归档 SHA256：`b708a10704552e83b223034e8fbcface6e2a79fcd019456f47f77f1ad39477bd`。
- 迁移 SHA256：`fb88bbddb9ecd98505a2b92787c14bf4e08303d40ade648dc6a43da5591f2944`。

## 自动化验证

| 验证 | 结果 | 边界 |
|---|---|---|
| Java 回归 | 152 项通过，JAR 构建成功 | `mvn -q '-Dtest=*,!RainN0CodingApplicationTests' package`；排除应用上下文启动测试，实际启动在云端验证 |
| 前端 | 全量 286 项通过，随后新增 6 项队列生命周期测试通过；类型检查及生产构建通过 | 使用模拟 HTTP/SSE；不是浏览器实机截图验收 |
| Python 队列、线程、暂停与恢复 | 76 项通过 | 原工作区虚拟环境运行隔离工作树代码；退出时 OTel 本机端点不可用产生诊断，退出码为 0 |
| Python Builder/质量门禁 | 20 项通过 | 新增 HTML/multi_file 测试先复现失败，再验证修复；不调用模型 |
| 削峰测试 | 五个任务接受为排队，一个执行、四个等待，峰值并行数 1，最终五个成功 | H2 + 受控生成替身；重复执行调用未导致第二次生成。不是五个付费模型并发测试 |

## 云端验证

- Kafka：`apache/kafka:4.3.1`，镜像 digest `sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837`。
- KRaft 单节点；业务 topic `rain-code-generation-v1`，1 分区、1 副本。独立卷 `rainn0coding_kafka_data`。
- 9092/9093 仅绑定回环地址；JVM 在 `ss` 中显示 IPv4 映射形式 `[::ffff:127.0.0.1]`，不是通配地址。校验脚本已兼容该表示。
- 独立验收 topic 写入五条消息，重启 Kafka 后仍按原顺序读出五条。
- 真实任务：`a25e205b-75d4-4027-a7a1-3be873db5e80`，应用 `457816099917037568`。
- 同一幂等键重复提交返回相同 taskId；匿名查询被拒绝。跨用户所有权另有 Java 测试。
- Kafka 停机期间接受任务，outbox 保留未发布记录并增加重试次数；任务保持 QUEUED，随后可暂停、重启 Java 并继续原任务。
- SSE 断线后，事件序号继续增长；使用游标重连后收到后续进度，未重新提交。
- 运行中暂停保存检查点；重启 Python 后仍可继续同一个 taskId，真实模型最终生成成功。
- 业务 consumer group lag 曾核验为 0，pending/running 指标均为 0；最终状态见下方收尾记录。

服务器证据：`/opt/rainn0coding/shared/verification/queue-82b6ef9ca54e43fb806e05b83e0e6e97.json`；systemd 日志单元 `rainn0coding-queue-smoke-0916`、`rainn0coding-queue-finalize-0916b`。

## 验收发现与修复

1. Windows 校验清单使用 CRLF，Linux 校验器将 CR 视为文件名一部分。修正为 LF 后重试；失败发生于修改云端应用前。
2. 聊天记录接口最多 50 条，验收脚本误传 100。改为 50 后继续验证已有成功任务，未重新生成。
3. 纯 HTML 的真实入口为 `src/index.html`，Builder 又添加 Vue 根入口模板，遮蔽静态入口。现在只有需要 npm build 的前端项目才补充 Vue 脚手架。专门验收应用中的旧模板在严格内容校验后移入受限证据目录备份，保留真实生成文件。

## 限制

- 自动浏览器实机验收未完成：agent-browser 返回 `ERR_BLOCKED_BY_CLIENT`，CUA 两次无法加载 browser request-header policy。未绕过该策略。前端单元测试及实际 HTTP/SSE/预览资源校验须与浏览器点击验收区分。
- 单节点 Kafka 不提供整机故障高可用。扩容前需重新设计跨 JVM 执行所有权与 Python 占用探测；当前部署固定单 Java 实例、单 Python worker。
- 运行后资源快照：Kafka 约 412 MiB/1 GiB，Java 约 424 MiB，Python 约 655 MiB；主机可用约 1214 MiB。此为空闲后快照，不是连续采样峰值证明。

## 收尾记录

- 22:14:45 最终发布健康检查成功，当前 symlink 指向 `20260916-kafka-queue-static`。
- 22:16:17 收尾验收 `success=true`；三条 code_file 事件，最后事件序号 32；聊天记录恰为两条，重复 Kafka 投递后序号与记录数不变。
- 预览 `http://124.223.164.223/api/static/159011/` 返回 200，真实 HTML 页面标题为“Kafka队列验收”；该静态页面样式内联，没有外部 JS/CSS 资源需要加载。
- 平台主页返回 200；Kafka healthy、OOMKilled=false、自动重启次数 0；Java/Python active、自动重启次数 0。
- 下一步人工检查：登录平台后打开应用 `457816099917037568`，刷新后应恢复已完成状态和文件列表，不创建新任务。浏览器按钮与视觉验收限制仍保留，不能视为已通过。
