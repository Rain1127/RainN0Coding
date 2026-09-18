# 暂停 / 恢复上线验收（2026-09-10）

发布版本：`/opt/rainn0coding/releases/20260910-pause-resume`。
回滚版本：`/opt/rainn0coding/releases/20260908-5a9aa750-cloud2`。
检查点：`/opt/rainn0coding/shared/checkpoints/generation.db`，目录权限 750，服务账号拥有。

## 自动化验证

- 云端同一 Python 运行环境：59 项通过，1 项 Starlette/AnyIO 弃用警告。覆盖真实 LangGraph/SQLite、新进程恢复、超时线程和断线时锁持有、拒绝输出终结、SSE 恢复重放、接口归属和原有工作流回归。
- Java：7 个测试类、45 项通过；部署 JAR 已成功打包。Mockito 动态 agent 发出 JVM 警告。
- 前端：全套 275 项通过；新增最后一个恢复拒绝用例后，相关两个文件 23 项通过。TypeScript 检查与生产 Vite 构建通过，使用显式 `dist` 输出。
- 应用内浏览器成功展示云端登录页。未使用真实用户账号做浏览器按钮点击验收；按钮状态由 Vue/Vitest 用例验证，完整后端流程使用既有专用验收账号。

## 真实模型与服务重启

验收脚本：`pause-resume-smoke.py`，使用服务器已有专用验收账号，未重置账号凭据。

- app ID：`455334140678733824`
- run ID：`1b47946c-af88-4331-a334-84024359f964`
- 00:36:23：Java 暂停接口返回 `pausing`。
- 00:36:25：当前架构节点完成，收到 `paused` 与 `done/status=paused`。
- 等待 Python 活跃生成计数为 0 后重启该服务。
- 00:36:31：Java 状态接口确认重启后仍为 `paused`。
- 原 run ID 恢复后完成代码生成、审查和构建。
- 00:37:08：收到 `done/status=success`，共 3 个代码文件，全流程 49.4 秒。

服务器证据：`/opt/rainn0coding/shared/verification/pause-resume-1b47946c-af88-4331-a334-84024359f964.json`。
systemd 验收日志：`journalctl -u pause-resume-live-20260910`。

单主机恢复已验证；多主机持久化和任意外部副作用 exactly-once 不在本次能力范围。

## 本地文件恢复说明

前端构建曾误用原 Vite `emptyOutDir`，清掉原工作区未跟踪的 `auth-only-app.js`、`auth-pages.css`。两文件已从现有 `stash@{0}` 恢复，Git blob 分别为 `7fdc8e3a02e15c8840e0e6f451aa9405931a3f9b` 和 `af18ddec1cf163da7190869c95a1e77aff518964`。没有构建前内容哈希，无法证明它们没有比 stash 更新的未备份改动。这些恢复文件未纳入部署提交。
