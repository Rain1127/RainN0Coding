# 腾讯云香港低成本生产部署设计

## 1. 目标与范围

将 RainN0Coding 完整部署到腾讯云中国香港地域，为首月试运行提供公网可访问、可恢复、可验证的生产环境。

首月目标用户为项目所有者及少量试用用户。系统只允许一个代码生成任务并发执行，以匹配低成本单机资源。最终交付包括可信 HTTPS 访问地址、完整业务链路、自动启动、备份与回滚能力，以及可重复执行的部署文档。

## 2. 已确认约束

- 云平台：腾讯云。
- 地域：中国香港，无需中国大陆 ICP 备案。
- 产品：Lighthouse 轻量应用服务器；如果购买页没有符合要求的库存，停止下单并重新确认，不自动降配。
- 首期规格：4 vCPU、16 GB RAM、至少 100 GB SSD。
- 操作系统：Ubuntu 22.04 LTS。
- 购买周期：1 个月。
- 域名：无；使用公网 IP 作为首期入口。
- 成本策略：所有应用与数据服务同机部署。
- 并发策略：最多一个代码生成任务。
- 监控范围：首月不部署 Prometheus、Grafana、Tempo 或 OTel Collector。
- 付款边界：展示腾讯云下单页的实际规格和价格后，由用户确认并完成付款。

## 3. 部署架构

```text
Internet
  |
  | HTTPS :443 / HTTP :80 redirect
  v
Nginx
  |
  v
Spring Boot :8123 (/api)
  |-- Vue production assets
  |-- MySQL :3306
  |-- Redis :6379
  `-- FastAPI :8000
        `-- Milvus :19530
              |-- etcd
              `-- MinIO
```

Nginx 是唯一业务公网入口。Spring Boot 同时提供前端静态资源、REST/SSE API 和已部署应用的静态访问。Java 仅通过回环地址调用 FastAPI；MySQL、Redis、FastAPI、Milvus、MinIO 和 etcd 不对公网开放。

Java 与 Python 服务由 systemd 管理并设置失败重启。Milvus、MinIO 和 etcd 使用仓库现有 Docker Compose 运行。数据与发布产物统一放在 `/opt/RainN0Coding` 下的固定持久化目录。

## 4. HTTPS 与网络安全

公网仅开放以下端口：

| 端口 | 用途 | 访问限制 |
| --- | --- | --- |
| 22 | SSH | 优先限制为用户当前公网 IP；仅允许密钥认证 |
| 80 | ACME 校验与 HTTPS 跳转 | 公网 |
| 443 | 业务 HTTPS | 公网 |

Let’s Encrypt 已支持公有 IPv4/IPv6 证书。首期使用 Certbot 5.4+ 为公网 IP 申请 `shortlived` 证书。证书有效期约 160 小时，因此必须配置自动续期、失败检测和续期后的 Nginx 平滑重载。只有证书申请和自动续期验证通过，才允许开放登录功能。

参考资料：

- [Let’s Encrypt IP 证书正式可用](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability.html)
- [Certbot 申请短期与 IP 证书](https://letsencrypt.org/2026/03/11/shorter-certs-certbot.html)

## 5. 应用安全加固

公开上线前必须完成以下代码和配置检查：

1. 移除固定管理员密码和包含默认密码的日志；首启管理员密码通过受保护环境变量注入。
2. 新生产数据库启用 BCrypt 密码散列，不继续使用 MD5。由于生产库为全新数据库，不需要迁移历史用户密码。
3. 轮换曾出现在本地配置中的 DeepSeek、智谱、COS、Pexels 等密钥；生产密钥只保存在权限为 `600` 的 EnvironmentFile 中。
4. 复查管理接口和版本接口鉴权，普通用户不得读取或修改其他用户的应用、版本和代码内容。
5. 复查静态资源路径规范化与目录边界，阻止路径穿越。
6. Spring Boot 对外采用同源策略；FastAPI 只监听回环地址并拒绝公网直连。
7. SSH 禁止密码登录；数据库、缓存和向量服务只监听本机或内部 Docker 网络。

任一项未通过都属于上线阻塞问题。

## 6. 资源控制

4 核 16 GB 主机采用保守资源配置：

- Java 最大堆约 2 GB。
- Redis 最大内存约 512 MB，并配置适合会话和限流数据的淘汰策略。
- 创建 4 GB swap 作为瞬时内存保护，不将其视为可用常规内存。
- Python Agent 只启动一个 Uvicorn worker。
- 代码生成任务并发限制为 1；生成期间限制 Node/npm 子进程数量和执行时长。
- Milvus、MinIO、etcd、MySQL 分别配置可用内存和日志上限。
- 首月不启动仓库中的监控 Compose，避免占用额外 1–3 GB 内存。

如果稳定运行时持续发生 swap 抖动或 OOM，不通过继续压缩内存掩盖问题；停止新生成任务并提出升配建议。

## 7. 数据、目录与备份

建议目录：

```text
/opt/RainN0Coding/releases/       versioned application releases
/opt/RainN0Coding/current/        active release link
/opt/RainN0Coding/config/         protected environment files
/opt/RainN0Coding/data/mysql/     MySQL persistence
/opt/RainN0Coding/data/redis/     Redis persistence
/opt/RainN0Coding/data/milvus/    Milvus, MinIO and etcd persistence
/opt/RainN0Coding/data/backups/   database backup staging
/opt/RainN0Coding/tmp/code_output generated projects
/opt/RainN0Coding/tmp/code_deploy deployed applications
/opt/RainN0Coding/logs/           rotated service logs
```

备份策略：

- 每日执行 MySQL 逻辑备份并保留最近 7 份。
- 首次上线、数据库变更和每次发布前创建 Lighthouse 快照。
- 配置、发布包和数据库备份不包含明文密钥副本。
- 上线验收必须执行一次临时数据库恢复测试，而不是只确认备份文件存在。

## 8. 发布与回滚

发布使用不可变版本目录。新版本经过本地构建和服务器健康检查后，再原子切换 `current` 符号链接并重启 Java/Python 服务。上一版本至少保留一份。

发布失败时：

1. 停止新生成请求。
2. 将 `current` 切回上一版本。
3. 恢复上一版本配置和服务定义。
4. 如果包含不兼容数据库变更，使用发布前快照或已验证备份恢复。
5. 重跑健康检查和核心冒烟测试。

## 9. 实施顺序

1. 本地预检与安全修复：前端测试和构建、Java测试、Python测试与工作流导入、安全阻塞项复查。
2. 打开腾讯云购买页，选择中国香港 Lighthouse、4C16G、Ubuntu 22.04、SSD ≥100 GB、1 个月；由用户核对价格并付款。
3. 初始化 SSH、系统更新、防火墙、swap、Docker、Java 21 运行时、Python 3.12、Node.js、MySQL、Redis、Nginx 和 Certbot；Java 发布包在本地使用 JDK 23 构建，以兼容当前 Lombok 注解处理配置。
4. 创建目录、系统用户、EnvironmentFile、systemd 服务和备份任务。
5. 上传严格筛选的发布产物，不上传本地 `.env`、`application-local.yml`、缓存、IDE 文件或未授权工作区内容。
6. 初始化数据库、Milvus Collection、SQLite/FTS 数据和必要种子数据。
7. 启动内部服务，完成本机健康检查。
8. 申请公网 IP 证书，配置 Nginx HTTPS、HTTP 跳转和 SSE 代理参数。
9. 执行完整业务验收、重启恢复测试和备份恢复测试。

## 10. 错误处理与停止条件

- 购买页没有符合要求的 4C16G/100GB 香港套餐：停止并重新选型。
- 本地测试或构建失败：先定位并修复，不上传未验证产物。
- 生产密钥未轮换或仍存在固定管理员密码：不开放公网。
- IP 证书申请或自动续期测试失败：不开放登录功能。
- MySQL、Redis、FastAPI 或 Milvus 健康检查失败：不启动 Java 公网流量。
- 生成链路失败：保留日志与上个版本，修复或回滚，不宣称上线完成。
- 内存持续超过安全水位或出现 OOM：停止新生成任务并重新评估规格。

## 11. 上线验收标准

只有以下全部通过，部署才算完成：

- `https://<public-ip>/api/` 使用受信任证书正常打开，并将 HTTP 跳转到 HTTPS。
- Certbot 自动续期演练成功，Nginx 能无中断重载。
- 前端静态资源完整加载，无控制台致命错误。
- 普通用户能够注册、登录和退出；越权访问被拒绝。
- 管理员凭据未硬编码、未出现在日志中。
- 创建应用后能收到完整 SSE 阶段事件。
- Agent 能生成代码，Builder 能完成依赖安装和构建。
- 生成应用能够通过 `/api/static/{deployKey}/` 访问。
- MySQL、Redis、Milvus 和生成目录在重启后数据仍存在。
- 每日备份任务可执行，且数据库恢复测试成功。
- 服务器重启后 Nginx、Java、Python、MySQL、Redis 和 Milvus 自动恢复。
- 外部端口检查仅显示 22、80、443；内部服务端口不可从公网访问。
- 磁盘使用、证书续期、服务状态和日志轮转检查可执行。

## 12. 首月不包含的内容

- Prometheus、Grafana、Tempo、OpenTelemetry Collector。
- 多机高可用、负载均衡或自动扩缩容。
- 云数据库 MySQL、云 Redis 或独立 Milvus 主机。
- 自有域名和长期域名证书。
- CI/CD 自动发布流水线。

这些能力可在首月稳定性数据明确后单独设计和启用。
