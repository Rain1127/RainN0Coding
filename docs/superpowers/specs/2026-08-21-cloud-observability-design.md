# RainN0Coding 云端监控平台设计

## 1. 目标与边界

本设计面向个人学习与演示环境。Java Spring Boot 与 Python FastAPI 继续运行在 Windows 本地；MySQL、Redis、Qdrant 继续运行在现有腾讯云轻量服务器；Prometheus、Tempo、OpenTelemetry Collector、Grafana 全部新增到同一台腾讯云服务器。

监控范围只包含：

- Java 与 Python 的 Prometheus 指标；
- 浏览器请求经 Java、Python、LangGraph Agent 到 LLM 的 OpenTelemetry Trace；
- 监控组件自身的存活状态。

本阶段不包含 Loki 日志、Alertmanager、邮件告警、Node Exporter、cAdvisor、MySQL/Redis/Qdrant Exporter，也不把 Java 或 Python 部署到云端。

## 2. 约束与设计原则

- 服务器规格为 2 vCPU、4 GB 内存、5 Mbps，另有 2 GB Swap。
- 继续使用现有服务器和预算，不采购额外云服务。
- 所有数据库与监控端口只监听云端 `127.0.0.1`，腾讯云防火墙不新增公网入站规则。
- 本地和云端通过 SSH 正向、反向端口转发通信。
- 监控失败不得阻断代码生成主链路。
- 所有镜像必须使用固定版本，不使用 `latest`。
- Grafana、Prometheus、Tempo 使用 Docker Volume 持久化。

## 3. 方案选择

采用 SSH 双向隧道方案。

未采用的方案：

- Tailscale/WireGuard：长期连接更稳定，但增加虚拟网络安装和维护成本。
- 公网 HTTPS + 鉴权：不依赖 SSH，但需要域名、证书和反向代理，并扩大公网攻击面。

SSH 方案复用现有连接、不增加成本，符合只在演示时启动的使用模式。它的明确限制是：演示期间 SSH 隧道窗口必须保持运行，隧道断开期间 Prometheus 会显示目标离线，Trace 也无法上传。

## 4. 组件与固定版本

| 组件 | 镜像 | 用途 |
|---|---|---|
| Grafana | `grafana/grafana:13.1.0` | 指标与 Trace 的统一查询界面 |
| Prometheus | `prom/prometheus:v3.12.0` | 抓取并保存 Java/Python 指标 |
| Tempo | `grafana/tempo:2.10.7` | 单机保存和查询 Trace |
| OTel Collector | `otel/opentelemetry-collector-contrib:0.157.0` | 接收 OTLP 并转发到 Tempo |

Tempo 使用单进程模式和本地文件存储，仅用于个人演示，不按生产高可用系统设计。

## 5. 数据流与端口

### 5.1 指标链路

Windows 启动 SSH 反向转发：

- 云端 `127.0.0.1:18123` 转发到本地 Java `127.0.0.1:8123`；
- 云端 `127.0.0.1:18000` 转发到本地 Python `127.0.0.1:8000`。

Prometheus 使用 Linux host network，只监听 `127.0.0.1:9090`，并抓取：

- `http://127.0.0.1:18123/api/actuator/prometheus`；
- `http://127.0.0.1:18000/metrics`。

### 5.2 Trace 链路

Windows 启动 SSH 正向转发：

- 本地 `127.0.0.1:14318` 转发到云端 OTel Collector `127.0.0.1:4318`。

Java 与 Python 的 OTLP HTTP Endpoint 均设置为 `http://127.0.0.1:14318`。Collector 在 Docker 内把 Trace 发送给 `tempo:4317`，Grafana通过 `http://tempo:3200` 查询。

### 5.3 查询入口

Windows 启动 SSH 正向转发：

- 本地 `127.0.0.1:13000` 转发到云端 Grafana `127.0.0.1:3000`；
- 本地 `127.0.0.1:19090` 转发到云端 Prometheus `127.0.0.1:9090`，只用于诊断。

用户只需访问 `http://127.0.0.1:13000`。Tempo不设置独立本地入口，统一通过 Grafana Explore 查询。

现有数据服务隧道继续保留：

- `13306 -> 云端 3306`；
- `16379 -> 云端 6379`；
- `16333 -> 云端 6333`。

## 6. 云端网络布局

Prometheus使用 `network_mode: host`，以访问SSH反向转发创建的云端loopback端口。它的Web接口显式监听 `127.0.0.1:9090`。

Grafana、Tempo、OTel Collector位于独立的Compose bridge network：

- Grafana通过服务名 `tempo:3200`访问Tempo；
- Collector通过服务名 `tempo:4317`发送OTLP；
- Grafana通过云端host gateway访问Prometheus `9090`；
- Grafana只发布 `127.0.0.1:3000:3000`；
- Collector只发布 `127.0.0.1:4317:4317`和`127.0.0.1:4318:4318`；
- Tempo无需向宿主机发布端口。

## 7. 资源与保留策略

| 组件 | 内存上限 | 保留策略 |
|---|---:|---|
| Grafana | 512 MB | 配置长期保留 |
| Prometheus | 384 MB | 3天，同时限制约512 MB磁盘 |
| Tempo | 384 MB | 24小时 |
| OTel Collector | 192 MB | 不持久化 |

内存上限合计约1.47 GB，但Docker限制不是预留量。所有组件采用低并发、低基数、单用户演示配置。服务器已存在的2 GB Swap只作为短时缓冲，不作为常态内存。

Grafana、Prometheus、Tempo分别使用命名Volume。删除或重建容器时不得使用`docker compose down -v`。

## 8. 凭据与安全

- Grafana管理员密码使用`openssl rand`生成，写入云端部署目录的`.env`。
- `.env`权限为`600`，不提交Git，不在验收日志中输出密码。
- Grafana匿名访问关闭，首次登录后保留随机管理员密码。
- Collector不做公网鉴权，因为只接受云端loopback经过SSH转发的请求。
- 不增加腾讯云安全组规则；继续只保留SSH 22和必要ICMP。
- 所有监控查询都通过SSH隧道，不使用公网IP直接访问数据库或监控端口。

## 9. 配置与部署产物

实现阶段在仓库新增独立目录`deploy/cloud-monitoring/`，包括：

- `compose.monitoring.yml`；
- `prometheus/prometheus.yml`；
- `tempo/tempo.yaml`；
- `otel/collector.yaml`；
- `grafana/provisioning/datasources/datasources.yaml`；
- `grafana/provisioning/dashboards/dashboards.yaml`；
- `grafana/dashboards/rainn0coding-overview.json`；
- `start-monitoring-tunnel.ps1`；
- `README.md`。

云端安装位置为`/home/ubuntu/rainn0coding-cloud/monitoring/`，与现有数据层Compose文件隔离。监控Compose的启停不会重建MySQL、Redis或Qdrant。

## 10. 故障处理

- SSH隧道断开：Prometheus目标变为`DOWN`，Java/Python OTLP上报失败；应用请求仍应正常完成。
- Tempo不可用：Collector重试或丢弃超出队列的Trace，不影响应用。
- Prometheus不可用：只丢失停机期间的指标，不影响Trace和业务数据。
- Grafana不可用：Prometheus和Tempo继续保存数据。
- 主机内存不足：先停止监控Compose，确认MySQL、Redis、Qdrant恢复健康，再降低Tempo或Prometheus内存与采样量。
- 镜像拉取失败：继续使用腾讯云Docker镜像加速配置，且不得退回浮动`latest`标签。

## 11. 验收标准

部署只有在以下条件全部满足时才完成：

1. MySQL、Redis、Qdrant、Prometheus、Tempo、OTel Collector、Grafana均正常运行，无`OOMKilled`和重启循环。
2. 云端`3000`、`9090`、`3200`、`4317`、`4318`均未向公网监听；腾讯云安全组没有新增规则。
3. Prometheus的Java、Python两个Target均为`UP`，并能查询JVM、HTTP与Python请求指标。
4. 浏览器执行一次真实代码生成后，Grafana Tempo可以检索同一请求下的Java入口、Python客户端/服务、`workflow.stream`、Agent和LLM Span。
5. Trace ID能够与Java日志、Python日志中的同次请求对应。
6. 重启监控容器后，Grafana账号和数据源、Prometheus历史指标、Tempo近期Trace仍存在。
7. 主机可用内存保持512 MB以上，无容器被OOM杀死，Swap没有持续快速增长，原有三个数据服务保持健康。
8. Grafana管理员密码不是默认值，并且未出现在Git或普通日志中。

## 12. 实施顺序与回滚

实施顺序：生成本地部署产物并验证Compose配置；上传到云端；生成密钥；拉取固定镜像；启动监控Compose；建立新隧道；配置并重启Java/Python；验证指标；触发真实请求并验证Trace；验证持久化与资源。

回滚只停止并移除监控容器与监控network，保留监控Volume；随后恢复Java/Python原OTLP设置或禁用OTel导出。回滚不得停止或删除MySQL、Redis、Qdrant及其Volume。
