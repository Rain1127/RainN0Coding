# 单机云服务器 Docker 部署手册（无 Docker Compose）

本目录把整套项目部署为相互隔离的 Docker 容器。只有前端 Nginx 发布 HTTP
端口；MySQL、PostgreSQL、Redis、Qdrant、LiteLLM、Python、Java、Prometheus、
Tempo 和 OTel Collector 仅加入 `rain-network`。Grafana 只绑定服务器回环地址，
通过 SSH 隧道访问。

## 1. 前置条件

- 64 位 Linux 云服务器和可用的 Docker Engine；CPU、内存、磁盘容量需按实际
  并发量、模型缓存和数据保留周期评估，当前规格为**待确认**。
- 已取得 DeepSeek 与智谱 API Key。LiteLLM 本身不收取模型调用费，厂商仍按
  各自价格计费。
- 域名、DNS、HTTPS 终止方式和证书来源为**待确认**。
- 仓库放在仅部署账号可写的目录；`runtime.env` 和密钥目录不得提交。

以下命令都在仓库根目录执行。

## 2. 创建运行配置与密钥

```bash
cp deploy/cloud/runtime.env.example deploy/cloud/runtime.env
chmod 600 deploy/cloud/runtime.env
sudo install -d -o "$(id -u)" -g "$(id -g)" -m 700 /opt/rainn0coding/secrets
```

编辑 `runtime.env`：替换 `PUBLIC_ORIGIN`，填入厂商 Key、数据库密码、Redis
密码、Java→Python 内部令牌和 Grafana 密码。内部密码建议使用只含十六进制
字符的随机值，避免 shell 与 URL 转义问题：

```bash
openssl rand -hex 32
```

`LITELLM_API_KEY` 可以留空。首次完整启动会通过 master key 创建一个仅允许
`code-reasoning`、`code-structured`、`code-lightweight` 的虚拟密钥，并写到
`/opt/rainn0coding/secrets/litellm_agent_key`（权限 600）。Python 容器只拿到
该虚拟密钥，不拿厂商 Key或 master key。

## 3. 验证并拉取固定镜像

`versions.env` 中每个外部镜像都同时固定版本和多架构 digest。先验证拉取：

```bash
set -a
. deploy/cloud/versions.env
set +a
for image in \
  "$MYSQL_IMAGE" "$POSTGRES_IMAGE" "$REDIS_IMAGE" "$QDRANT_IMAGE" \
  "$LITELLM_IMAGE" "$PROMETHEUS_IMAGE" "$GRAFANA_IMAGE" \
  "$OTEL_IMAGE" "$TEMPO_IMAGE" "$CURL_IMAGE"; do
  docker pull "$image"
  docker image inspect "$image" >/dev/null
done
```

## 4. 构建不可变应用镜像

每次发布使用唯一版本，例如 Git commit SHA：

```bash
release="$(git rev-parse --short=12 HEAD)"
docker build -f deploy/docker/frontend.Dockerfile -t "rain/frontend:${release}" .
docker build -f deploy/docker/java.Dockerfile -t "rain/java-api:${release}" .
docker build -f deploy/docker/python-agent.Dockerfile -t "rain/python-agent:${release}" .
docker image inspect \
  "rain/frontend:${release}" \
  "rain/java-api:${release}" \
  "rain/python-agent:${release}" >/dev/null
```

将 `runtime.env` 的 `APP_RELEASE` 改为同一个 `release`。不要复用标签覆盖旧镜像；
旧标签是快速回滚的基础。

## 5. 首次启动

```bash
./deploy/cloud/create-network-and-volumes.sh
./deploy/cloud/start-data-services.sh
./deploy/cloud/start-app-services.sh
```

首次创建 Qdrant 卷后，只执行一次种子导入。命令通过共享 marker 防止普通重复
执行；恢复 Qdrant 备份后应先核对集合数量，不要盲目重灌：

```bash
docker exec python-agent sh -eu -c '
  marker=/data/code-output/.rag/vector-seed-v1
  if [ ! -f "$marker" ]; then
    python rag/seed_vector_store.py
    mkdir -p "$(dirname "$marker")"
    touch "$marker"
  fi
'
```

然后启动监控并运行整栈检查：

```bash
./deploy/cloud/start-observability.sh
./deploy/cloud/health-check.sh
```

## 6. HTTPS 与防火墙

推荐在云负载均衡器或受管反向代理终止 HTTPS，再转发到前端容器的 80 端口；
证书私钥不能进入镜像或 Git。若直接在服务器 Nginx 终止 HTTPS，需先提供真实
域名、证书和经审查的 443 配置，再显式挂载只读证书并发布 443。本仓库不会
默默启用自签名生产证书，因此直连服务器 HTTPS 当前为**待确认**。

主机安全组/防火墙只允许 22、80、443。Grafana 使用 SSH 隧道：

```bash
ssh -L 3001:127.0.0.1:3001 user@server
```

浏览器随后访问 `http://127.0.0.1:3001`。从另一台机器扫描确认 3306、5432、
6379、6333、4000、8000、8123、9090、3200、4317、4318 和 3001 均不可达。

## 7. MySQL 与 PostgreSQL 备份/恢复演练

先加载运行变量并创建严格权限的备份目录：

```bash
set -a
. deploy/cloud/runtime.env
set +a
backup_dir=/opt/rainn0coding/backups
install -d -m 700 "$backup_dir"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
mysql_backup="${backup_dir}/mysql-${stamp}.sql"
postgres_backup="${backup_dir}/postgres-${stamp}.dump"
```

生成备份并确认非空：

```bash
docker exec mysql sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE"' \
  >"$mysql_backup"
docker exec postgres sh -c \
  'exec pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' \
  >"$postgres_backup"
test -s "$mysql_backup"
test -s "$postgres_backup"
```

必须恢复到临时库验证，不能覆盖生产库：

```bash
mysql_restore_verify=rainn0coding_restore_verify
docker exec mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE IF EXISTS rainn0coding_restore_verify; CREATE DATABASE rainn0coding_restore_verify"'
docker exec -i mysql sh -c \
  'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" rainn0coding_restore_verify' \
  <"$mysql_backup"
docker exec mysql sh -c \
  'mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" rainn0coding_restore_verify -e "SHOW TABLES" | grep -q .'
docker exec mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "DROP DATABASE rainn0coding_restore_verify"'

postgres_restore_verify=litellm_restore_verify
docker exec postgres sh -c \
  'dropdb -U "$POSTGRES_USER" --if-exists litellm_restore_verify && createdb -U "$POSTGRES_USER" litellm_restore_verify'
docker exec -i postgres sh -c \
  'exec pg_restore -U "$POSTGRES_USER" --exit-on-error -d litellm_restore_verify' \
  <"$postgres_backup"
docker exec postgres sh -c \
  'psql -U "$POSTGRES_USER" -d litellm_restore_verify -tAc "SELECT count(*) FROM information_schema.tables" | grep -Eq "[1-9]"'
docker exec postgres sh -c \
  'dropdb -U "$POSTGRES_USER" litellm_restore_verify'
```

验证完成后，才可在明确目录内执行保留策略，例如保留 14 天：

```bash
find /opt/rainn0coding/backups -maxdepth 1 -type f \
  \( -name 'mysql-*.sql' -o -name 'postgres-*.dump' \) \
  -mtime +14 -delete
```

## 8. 发布与回滚

新发布先构建三个相同 release 的镜像，更新 `runtime.env`，然后运行：

```bash
./deploy/cloud/start-app-services.sh
./deploy/cloud/health-check.sh
```

回滚只替换 Python、Java 和前端，不删除数据容器或卷，也不替换 LiteLLM：

```bash
./deploy/cloud/rollback.sh <previous-release>
```

回滚健康检查通过后，把 `runtime.env` 的 `APP_RELEASE` 同步为回滚版本，避免
下一次普通启动又切回错误版本。

## 9. 验收记录

以下项目必须全部有云服务器上的时间戳和非敏感输出，才能把部署标记完成：

| 验收项 | 当前状态 |
| --- | --- |
| 外部镜像 digest 拉取、三个应用镜像构建 | 待验收（本地 Docker daemon 未启动） |
| 所有容器健康、Prometheus 三个 target 为 UP | 待验收 |
| 公网仅 22/80/443 可达 | 待验收 |
| 真实 Java→Python SSE 代码生成成功 | 待验收 |
| LiteLLM fallback、低预算拒绝、消费记录重启持久化 | 待验收 |
| Qdrant 种子与检索 | 待验收 |
| MySQL/PostgreSQL 临时库恢复演练 | 待验收 |
| 已知坏版本回滚后恢复健康 | 待验收 |
| HTTPS 证书与终止方式 | 待确认 |

禁止在验收记录中粘贴密码、Key、用户 prompt 或生成代码。
