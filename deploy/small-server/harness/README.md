# 云端 Harness 验收与执行

在候选环境验证后再启用现网策略。新运行冻结开关，旧检查点继续使用自己的策略。

## 普通用户容器引擎

1. 为服务账号配置 Ubuntu 的 rootless Docker 先决条件。系统需支持非特权用户命名空间、cgroup v2、`uidmap`、`slirp4netns`，以及专属、不重叠的 subordinate UID/GID 范围。将 `cpu cpuset io memory pids` 委派给此账号的 `user@UID.service`。
2. 将 `launch-rootless.sh`、`worker.py` 和 `python-agent/workflow/execution.py` 安装到管理员所有的 `/opt/rainn0coding/harness-executor`。设置 `worker.py` 和 launcher 为可执行。将 `browser_entry.py`、`runtime_validation.py` 和已锁定的 Playwright 依赖安装到其只读 `browser` 子目录。
3. 在 `/etc/rainn0coding/harness-executor.env` 指定服务账号拥有的 `HARNESS_DOCKER_DATA` 和 `HOME`。安装 `rainn0coding-harness-executor@.service`，实例号使用 `id -u rainn0coding`。launcher 在私有挂载命名空间里处理宿主 procfs 兼容问题，随后降到服务账号启动引擎。
4. 预置并校验 Node、Python 及 Chromium 镜像。在 `worker.json` 登记服务账号专用的 `docker_socket`、允许的 `workspace_roots`、`node_image`、`python_image` 与 `browser_image`。镜像按摘要固定。Java、Go、Rust 需要登记对应镜像，否则返回环境未验证。
5. 验证容器执行和进程清理后，给 Python 配置 `HARNESS_EXECUTOR_ENABLED=true` 与 `HARNESS_DOCKER_WORKER=/opt/rainn0coding/harness-executor/worker.py`。部署门禁可用 `test_harness_executor.py`，需指定专属 `HARNESS_EXECUTOR_TEST_ROOT`。

构建和检查在一次性副本运行。构建只回收 `dist`、`build` 和合法安装产物。依赖安装仅支持普通 npm 注册源版本、禁止生命周期脚本。其他检查和 Chromium 使用无网络容器。依赖 CDN 的页面显示环境未验证。隔离引擎只接受登记配置和候选路径。

## 云端候选验证

`sync-source.ps1` 使用严格 SSH 主机校验传输代码。候选 Java/Python 使用独立端口、数据目录、数据库、Redis 和 Kafka 主题。实模型调用必须经过已核对的费用限额代理。 `stage_smoke.py` 只访问候选的 18123 端口，记录队列、重连、指令回执、前端和候选发布证据。脚本每次执行会发起新的真实生成。
