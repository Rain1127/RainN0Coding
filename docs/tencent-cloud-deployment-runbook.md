# 腾讯云部署清单与操作流程

适用项目：`yu-ai-code-mother`

目标架构：腾讯云 CVM 上运行 Spring Boot 网关、Python FastAPI Agent、Redis、MySQL、Milvus Standalone，并通过 Nginx 对外暴露 HTTPS。前端由 Vite 构建后打入 Spring Boot `src/main/resources/static`，生产访问路径建议统一走 `/api`。

---

## 1. 推荐部署拓扑

### 1.1 单机版，适合初期上线

```
Internet
  |
  v
Tencent Cloud Security Group
  |
  v
Nginx :80/:443
  |
  +--> Spring Boot :8123, context-path /api
          |
          +--> MySQL :3306, local/private only
          +--> Redis :6379, local/private only
          +--> Python FastAPI :8000, local only
                  |
                  +--> Milvus :19530, local only
                  +--> SQLite/FTS + local generated code files
```

推荐先用这个方案，部署简单，链路短，问题定位成本低。

### 1.2 生产增强版

当有真实用户或生成任务变多时，建议拆成：

- CVM 1：Nginx + Spring Boot + Python Agent
- 腾讯云数据库 MySQL：替代本机 MySQL
- 腾讯云 Redis：替代本机 Redis
- 独立 CVM 或专用实例：Milvus + MinIO + etcd
- COS：截图、生成包、长期归档文件

---

## 2. 资源规格建议

### 2.1 CVM

最低可跑：

- 4 核 CPU
- 16 GB 内存
- 100 GB SSD 云硬盘
- Ubuntu 22.04 LTS 或 24.04 LTS

更稳妥：

- 8 核 CPU
- 32 GB 内存
- 200 GB SSD 云硬盘

原因：

- Python Agent 依赖 `torch`、`sentence-transformers`、`onnxruntime`、`milvus-lite/pymilvus`，内存占用明显高于普通 Web 服务。
- Milvus Standalone 同机运行通常需要预留 4 GB 以上内存。
- 生成 Vue 项目时会执行 `npm install && npm build`，CPU、磁盘、网络都会有瞬时压力。

### 2.2 云侧安全组

只放行公网必要端口：

| 端口 | 来源 | 用途 |
|---|---|---|
| 22 | 你的固定 IP | SSH |
| 80 | 0.0.0.0/0 | HTTP，签发证书或跳转 HTTPS |
| 443 | 0.0.0.0/0 | HTTPS |

不要对公网开放：

| 端口 | 服务 |
|---|---|
| 8123 | Spring Boot |
| 8000 | Python FastAPI |
| 3306 | MySQL |
| 6379 | Redis |
| 19530 | Milvus |
| 9091 | Milvus health/metrics |
| 9000/9001 | MinIO |
| 2379 | etcd |
| 9090 | Prometheus |
| 3000 | Grafana |

这些端口只允许 `127.0.0.1` 或内网访问。

---

## 3. 上线前必须处理的问题

### 3.1 轮换已经暴露的密钥

当前仓库的 `src/main/resources/application-local.yml` 和 `python-agent/.env` 存在 API Key、COS Secret 等敏感配置。部署前必须：

1. 在 DeepSeek、智谱 AI、腾讯云 COS、Pexels 等平台轮换已出现过的密钥。
2. 生产服务器只通过环境变量或 `EnvironmentFile` 注入密钥。
3. 不要把生产密钥提交到 Git。

### 3.2 默认管理员账号

`DataInitializer` 会创建默认管理员：

- 账号：`admin`
- 代码注释与日志提示里出现默认口令

生产首启后必须立刻改密码，或者上线前改成从环境变量读取默认管理员密码。

### 3.3 部署访问地址常量

`AppConstant.CODE_DEPLOY_HOST` 当前硬编码为：

```java
String CODE_DEPLOY_HOST = "http://localhost";
```

生产会导致部署后返回 `http://localhost/{deployKey}`。上线前建议改成配置项，例如：

```yaml
app:
  deploy-host: https://your-domain.com/api/static
```

然后在代码里通过 `@Value("${app.deploy-host}")` 注入。

### 3.4 部署目录与静态资源目录疑似不一致

`deployApp()` 会把文件复制到：

```text
${user.dir}/tmp/code_deploy/{deployKey}
```

但 `StaticResourceController` 当前读取的是：

```text
${user.dir}/tmp/code_output/{deployKey}
```

这会导致部署成功后无法访问已部署应用。上线前建议统一为 `CODE_DEPLOY_ROOT_DIR`，并让访问 URL 走：

```text
https://your-domain.com/api/static/{deployKey}/
```

### 3.5 数据表初始化脚本不完整

`sql/create_table.sql` 包含：

- `user`
- `app`
- `chat_history`
- `intent_config`

但代码里还有 `app_version` 实体和 Mapper。生产初始化时建议补充：

```sql
create table if not exists app_version
(
    id             bigint auto_increment primary key,
    app_id         bigint       not null comment '关联应用ID',
    version_number int          not null comment '版本号',
    code_content   longtext     null comment '代码内容或文件路径',
    description    varchar(512) null comment '版本说明',
    create_time    datetime default CURRENT_TIMESTAMP not null comment '创建时间',
    index idx_app_id (app_id),
    unique key uk_app_version (app_id, version_number)
) comment '应用版本表' collate = utf8mb4_unicode_ci;
```

### 3.6 截图功能需要 Chrome

`WebScreenshotUtils` 使用 Selenium + ChromeDriver。服务器必须安装 Chrome/Chromium 及字体，否则截图和 COS 封面上传可能失败。

---

## 4. 目录规划

服务器上建议统一放到 `/opt`：

```bash
sudo mkdir -p /opt/yu-ai-code-mother
sudo mkdir -p /opt/yu-ai-code-mother/logs/java
sudo mkdir -p /opt/yu-ai-code-mother/logs/python
sudo mkdir -p /opt/yu-ai-code-mother/data/mysql
sudo mkdir -p /opt/yu-ai-code-mother/data/redis
sudo mkdir -p /opt/yu-ai-code-mother/data/milvus
sudo mkdir -p /opt/yu-ai-code-mother/tmp/code_output
sudo mkdir -p /opt/yu-ai-code-mother/tmp/code_deploy
sudo mkdir -p /opt/yu-ai-code-mother/python-agent/rag_data
sudo chown -R $USER:$USER /opt/yu-ai-code-mother
```

推荐创建专用用户：

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin yuai
sudo chown -R yuai:yuai /opt/yu-ai-code-mother
```

---

## 5. 安装系统依赖

以下命令以 Ubuntu 为例。

```bash
sudo apt update
sudo apt install -y \
  git curl wget unzip ca-certificates gnupg lsb-release \
  nginx mysql-server redis-server \
  python3.12 python3.12-venv python3-pip \
  nodejs npm \
  maven \
  chromium-browser fonts-noto-cjk fonts-wqy-zenhei \
  build-essential
```

如果系统源没有 `python3.12` 或 `chromium-browser`，用发行版对应包名替换，例如 `chromium`。

安装 Docker Engine：

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

重新登录 SSH 后验证：

```bash
docker version
docker compose version
```

---

## 6. 初始化 MySQL

### 6.1 创建数据库和用户

```bash
sudo mysql
```

执行：

```sql
create database if not exists yu_ai_code_mother
  default character set utf8mb4
  collate utf8mb4_unicode_ci;

create user if not exists 'yuai'@'127.0.0.1'
  identified by 'replace-with-strong-password';

grant all privileges on yu_ai_code_mother.* to 'yuai'@'127.0.0.1';
flush privileges;
```

### 6.2 导入表结构

```bash
mysql -h127.0.0.1 -uyuai -p yu_ai_code_mother < /opt/yu-ai-code-mother/sql/create_table.sql
```

然后补充 `app_version`：

```bash
mysql -h127.0.0.1 -uyuai -p yu_ai_code_mother
```

执行第 3.5 节的 `app_version` SQL。

### 6.3 MySQL 安全加固

```bash
sudo mysql_secure_installation
sudo systemctl enable --now mysql
```

确保 MySQL 只监听本地或内网：

```bash
sudo ss -lntp | grep 3306
```

---

## 7. 初始化 Redis

编辑：

```bash
sudo vim /etc/redis/redis.conf
```

建议：

```conf
bind 127.0.0.1 ::1
protected-mode yes
requirepass replace-with-strong-redis-password
appendonly yes
maxmemory 2gb
maxmemory-policy allkeys-lru
```

重启：

```bash
sudo systemctl enable --now redis-server
sudo systemctl restart redis-server
redis-cli -a replace-with-strong-redis-password ping
```

返回 `PONG` 即可。

---

## 8. 初始化 Milvus

### 8.1 上传或拉取项目

```bash
cd /opt
git clone <your-repo-url> yu-ai-code-mother
cd /opt/yu-ai-code-mother
```

如果用本地构建产物上传，也要把 `milvus/docker-compose.yml` 和 `python-agent` 上传到服务器。

### 8.2 限制 Milvus 只监听本地

生产建议把 `milvus/docker-compose.yml` 的端口绑定改成：

```yaml
ports:
  - "127.0.0.1:19530:19530"
  - "127.0.0.1:9091:9091"
```

MinIO 和 etcd 不需要映射公网端口。

### 8.3 启动 Milvus

```bash
cd /opt/yu-ai-code-mother/milvus
docker compose up -d
docker compose ps
curl http://127.0.0.1:9091/healthz
```

健康时返回 `OK`。

---

## 9. 配置 Python Agent

### 9.1 创建虚拟环境

```bash
cd /opt/yu-ai-code-mother/python-agent
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip uv
.venv/bin/uv sync
```

如果 `uv sync` 在服务器上较慢，可先在构建机生成 wheel 缓存，或临时使用清华源。

### 9.2 创建生产环境变量文件

创建 `/opt/yu-ai-code-mother/python-agent/.env.prod`：

```bash
cat > /opt/yu-ai-code-mother/python-agent/.env.prod <<'EOF'
DEEPSEEK_API_KEY=replace-with-real-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
CHAT_MODEL=deepseek-chat
REASONING_MODEL=deepseek-v4-pro

ZHIPU_API_KEY=replace-with-real-key
ZHIPU_BASE_URL=https://open.bigmodel.cn/api/paas/v4
ZHIPU_FLASH_MODEL=glm-4.7-flash

SERVER_PORT=8000
LLM_TIMEOUT=120
LLM_FALLBACK_TIMEOUT=60

MILVUS_MODE=standalone
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530

REDIS_HOST=127.0.0.1
REDIS_PORT=6379

LOCAL_EMBEDDING_ENABLED=true
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
RAG_TOP_K=8
RAG_DEDUP_THRESHOLD=0.95
RAG_PARALLEL_WORKERS=5

SQLITE_DB_PATH=/opt/yu-ai-code-mother/python-agent/rag_data/exact_search.db
CODE_STORE_DIR=/opt/yu-ai-code-mother/python-agent/verified_code
USE_HYBRID_ENGINE=true

LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=yu-ai-code-mother
EOF

chmod 600 /opt/yu-ai-code-mother/python-agent/.env.prod
```

注意：当前 `Config` 使用 `python-dotenv` 默认加载 `.env`。生产可把 `.env.prod` 复制为 `.env`，或在 systemd 里通过 `EnvironmentFile` 注入。

```bash
cp /opt/yu-ai-code-mother/python-agent/.env.prod /opt/yu-ai-code-mother/python-agent/.env
```

### 9.3 初始化 Milvus Collection 和种子数据

```bash
cd /opt/yu-ai-code-mother/python-agent
PYTHONPATH=/opt/yu-ai-code-mother/python-agent \
  .venv/bin/python rag/seed_milvus.py
```

验证：

```bash
PYTHONPATH=/opt/yu-ai-code-mother/python-agent \
  .venv/bin/python -c "from rag.milvus_client import milvus_store; milvus_store.connect(); print('milvus ok')"
```

### 9.4 创建 Python systemd 服务

创建 `/etc/systemd/system/yuai-python-agent.service`：

```ini
[Unit]
Description=Yu AI Code Mother Python Agent
After=network-online.target docker.service redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=yuai
Group=yuai
WorkingDirectory=/opt/yu-ai-code-mother/python-agent
EnvironmentFile=/opt/yu-ai-code-mother/python-agent/.env.prod
Environment=PYTHONPATH=/opt/yu-ai-code-mother/python-agent
ExecStart=/opt/yu-ai-code-mother/python-agent/.venv/bin/python -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5
StandardOutput=append:/opt/yu-ai-code-mother/logs/python/stdout.log
StandardError=append:/opt/yu-ai-code-mother/logs/python/stderr.log

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yuai-python-agent
sudo systemctl status yuai-python-agent
curl http://127.0.0.1:8000/api/health
```

---

## 10. 构建前端

当前前端配置：

- `VITE_API_BASE` 控制 axios 和 SSE 请求前缀。
- 生产构建 `base` 是 `/api/`。
- 构建输出目录是 `../src/main/resources/static`。

创建 `yu-ai-code-mother-frontend/.env.production`：

```bash
cat > /opt/yu-ai-code-mother/yu-ai-code-mother-frontend/.env.production <<'EOF'
VITE_API_BASE=/api
EOF
```

构建：

```bash
cd /opt/yu-ai-code-mother/yu-ai-code-mother-frontend
npm ci
npm run build
```

构建成功后应看到：

```text
/opt/yu-ai-code-mother/src/main/resources/static
```

---

## 11. 构建 Java 后端

### 11.1 生产配置文件

创建 `/opt/yu-ai-code-mother/config/application-prod.yml`：

```yaml
spring:
  profiles:
    active: prod
  application:
    name: yu-ai-code-mother-backend
  session:
    timeout: 2592000
    store-type: redis
  datasource:
    driver-class-name: com.mysql.cj.jdbc.Driver
    url: jdbc:mysql://127.0.0.1:3306/yu_ai_code_mother?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&useSSL=false&allowPublicKeyRetrieval=true
    username: yuai
    password: replace-with-strong-password
  data:
    redis:
      host: 127.0.0.1
      port: 6379
      database: 0
      password: replace-with-strong-redis-password
      ttl: 3600

server:
  port: 8123
  servlet:
    context-path: /api
    session:
      cookie:
        max-age: 2592000

python:
  ai:
    base-url: http://127.0.0.1:8000

sa-token:
  token-name: satoken
  timeout: 2592000
  active-timeout: -1
  is-concurrent: true
  is-share: true
  token-style: uuid
  is-log: false
  is-read-cookie: true
  is-read-header: true

management:
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
  endpoint:
    health:
      show-details: never

cos:
  client:
    host: https://your-bucket.cos.ap-shanghai.myqcloud.com
    secretId: ${COS_SECRET_ID}
    secretKey: ${COS_SECRET_KEY}
    region: ap-shanghai
    bucket: your-bucket

pexels:
  api-key: ${PEXELS_API_KEY}
```

设置权限：

```bash
chmod 600 /opt/yu-ai-code-mother/config/application-prod.yml
```

### 11.2 构建 Jar

推荐在 CI 或本地构建后上传 Jar。若在服务器构建，确保 JDK 版本满足项目要求。仓库说明里提到 Lombok 编译建议使用 JDK 23。

```bash
cd /opt/yu-ai-code-mother
mvn clean package -DskipTests -Dspring.profiles.active=prod
```

产物：

```text
target/yu-ai-code-mother-0.0.1-SNAPSHOT.jar
```

### 11.3 创建 Java 环境变量文件

创建 `/opt/yu-ai-code-mother/config/java.env`：

```bash
cat > /opt/yu-ai-code-mother/config/java.env <<'EOF'
COS_SECRET_ID=replace-with-real-secret-id
COS_SECRET_KEY=replace-with-real-secret-key
PEXELS_API_KEY=replace-with-real-key
EOF

chmod 600 /opt/yu-ai-code-mother/config/java.env
```

### 11.4 创建 Java systemd 服务

创建 `/etc/systemd/system/yuai-java.service`：

```ini
[Unit]
Description=Yu AI Code Mother Java Backend
After=network-online.target mysql.service redis-server.service yuai-python-agent.service
Wants=network-online.target

[Service]
Type=simple
User=yuai
Group=yuai
WorkingDirectory=/opt/yu-ai-code-mother
EnvironmentFile=/opt/yu-ai-code-mother/config/java.env
ExecStart=/usr/bin/java -Xms512m -Xmx2g -jar /opt/yu-ai-code-mother/target/yu-ai-code-mother-0.0.1-SNAPSHOT.jar --spring.config.additional-location=file:/opt/yu-ai-code-mother/config/application-prod.yml --spring.profiles.active=prod
Restart=always
RestartSec=5
StandardOutput=append:/opt/yu-ai-code-mother/logs/java/stdout.log
StandardError=append:/opt/yu-ai-code-mother/logs/java/stderr.log

[Install]
WantedBy=multi-user.target
```

启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yuai-java
sudo systemctl status yuai-java
curl http://127.0.0.1:8123/api/actuator/health
```

---

## 12. 配置 Nginx

假设域名是 `your-domain.com`，前端访问路径是：

```text
https://your-domain.com/api/
```

创建 `/etc/nginx/sites-available/yu-ai-code-mother.conf`：

```nginx
upstream yuai_java {
    server 127.0.0.1:8123;
    keepalive 64;
}

server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 50m;

    location = / {
        return 302 /api/;
    }

    location /api/ {
        proxy_pass http://yuai_java;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE / 长连接
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        chunked_transfer_encoding off;
    }
}
```

启用：

```bash
sudo ln -s /etc/nginx/sites-available/yu-ai-code-mother.conf /etc/nginx/sites-enabled/yu-ai-code-mother.conf
sudo nginx -t
sudo systemctl reload nginx
```

HTTPS 证书建议使用腾讯云 SSL 证书或 Let's Encrypt。配置 HTTPS 后，将 80 跳转到 443，并在 443 server 中保留上面的 `/api/` 反代配置。

---

## 13. 防火墙

Ubuntu UFW 示例：

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from <your-ip> to any port 22 proto tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status numbered
```

再次确认内部服务没有公网监听：

```bash
sudo ss -lntp
```

---

## 14. 启动顺序

首次部署推荐顺序：

1. MySQL
2. Redis
3. Docker
4. Milvus
5. Python Agent
6. 前端构建
7. Java Backend
8. Nginx

命令汇总：

```bash
sudo systemctl restart mysql
sudo systemctl restart redis-server
sudo systemctl restart docker

cd /opt/yu-ai-code-mother/milvus
docker compose up -d

sudo systemctl restart yuai-python-agent
sudo systemctl restart yuai-java
sudo systemctl reload nginx
```

---

## 15. 验收清单

### 15.1 基础服务

```bash
systemctl is-active mysql
systemctl is-active redis-server
systemctl is-active yuai-python-agent
systemctl is-active yuai-java
systemctl is-active nginx
docker compose -f /opt/yu-ai-code-mother/milvus/docker-compose.yml ps
```

### 15.2 健康检查

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8123/api/actuator/health
curl http://127.0.0.1:9091/healthz
curl -I https://your-domain.com/api/
```

### 15.3 前端和鉴权

- 打开 `https://your-domain.com/api/`
- 注册普通用户
- 登录
- 访问聊天页面
- 访问管理后台，确认普通用户被拒绝
- 用管理员账号登录后确认管理页面可访问

### 15.4 代码生成链路

完整验证一次：

1. 创建 App。
2. 输入简单需求，例如“生成一个 Todo 页面”。
3. 确认前端收到 SSE 流。
4. 确认 Java 日志没有 Python 连接错误。
5. 确认 Python 日志出现 Agent 工作流阶段。
6. 确认 `/opt/yu-ai-code-mother/tmp/code_output` 或当前代码实际输出目录下生成项目。
7. 点击部署。
8. 访问部署 URL。
9. 确认截图上传 COS 成功，`app.cover` 被更新。

### 15.5 数据检查

```sql
select count(*) from user;
select count(*) from app;
select count(*) from chat_history;
select count(*) from intent_config;
select count(*) from app_version;
```

---

## 16. 日志与排障

### 16.1 Java

```bash
sudo journalctl -u yuai-java -f
tail -f /opt/yu-ai-code-mother/logs/java/stdout.log
tail -f /opt/yu-ai-code-mother/logs/java/stderr.log
```

常见问题：

- MySQL 登录失败：检查 `application-prod.yml` 的账号密码。
- Redis 认证失败：检查 `spring.data.redis.password`。
- Python 不通：检查 `python.ai.base-url` 和 `yuai-python-agent` 状态。
- 前端 404：确认访问路径是 `/api/`，且静态文件已打进 Jar。

### 16.2 Python

```bash
sudo journalctl -u yuai-python-agent -f
tail -f /opt/yu-ai-code-mother/logs/python/stdout.log
tail -f /opt/yu-ai-code-mother/logs/python/stderr.log
```

常见问题：

- `Milvus connection timeout`：检查 Docker 容器和 `MILVUS_HOST/MILVUS_PORT`。
- `torch` 或 `onnxruntime` 安装失败：固定 Python 3.12，优先使用项目 `uv.lock`。
- 生成慢：检查 LLM API、网络出口、CPU 和内存。

### 16.3 Milvus

```bash
cd /opt/yu-ai-code-mother/milvus
docker compose ps
docker compose logs -f milvus-standalone
docker compose logs -f etcd
docker compose logs -f minio
```

### 16.4 Nginx

```bash
sudo nginx -t
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

SSE 中断时重点检查：

- `proxy_buffering off`
- `proxy_read_timeout 3600s`
- 浏览器请求是否带 cookie
- Java 接口是否持续输出 SSE

---

## 17. 备份与恢复

### 17.1 MySQL 备份

```bash
mkdir -p /opt/yu-ai-code-mother/backups/mysql
mysqldump -h127.0.0.1 -uyuai -p \
  --single-transaction \
  yu_ai_code_mother \
  > /opt/yu-ai-code-mother/backups/mysql/yu_ai_code_mother_$(date +%F_%H%M%S).sql
```

恢复：

```bash
mysql -h127.0.0.1 -uyuai -p yu_ai_code_mother < backup.sql
```

### 17.2 Redis 备份

Redis 用于会话、限流、记忆摘要。建议开启 AOF，定期备份：

```bash
sudo cp /var/lib/redis/appendonly.aof /opt/yu-ai-code-mother/backups/redis/appendonly_$(date +%F_%H%M%S).aof
```

### 17.3 Milvus 备份

单机 Docker volume 默认在 Docker 管理目录中。建议：

- 生产改用明确宿主机挂载路径。
- 备份 etcd、MinIO、Milvus 数据卷。
- 重要 RAG 种子数据保留在 Git 或对象存储中，可重建 Collection。

### 17.4 生成代码与部署产物

备份：

```bash
tar -czf /opt/yu-ai-code-mother/backups/code_output_$(date +%F_%H%M%S).tar.gz \
  -C /opt/yu-ai-code-mother tmp/code_output tmp/code_deploy
```

---

## 18. 发布与回滚流程

### 18.1 发布

```bash
cd /opt/yu-ai-code-mother
git fetch --all
git checkout <release-tag-or-branch>
git pull

cd yu-ai-code-mother-frontend
npm ci
npm run build

cd /opt/yu-ai-code-mother
mvn clean package -DskipTests

sudo systemctl restart yuai-python-agent
sudo systemctl restart yuai-java
sudo systemctl reload nginx
```

发布后执行第 15 节验收。

### 18.2 回滚

保留上一版 Jar：

```bash
cp target/yu-ai-code-mother-0.0.1-SNAPSHOT.jar \
  releases/yu-ai-code-mother-$(date +%F_%H%M%S).jar
```

回滚时：

```bash
ln -sfn /opt/yu-ai-code-mother/releases/previous.jar /opt/yu-ai-code-mother/app.jar
sudo systemctl restart yuai-java
```

如果涉及数据库结构变更，必须提前准备回滚 SQL。

---

## 19. 监控建议

已有 `prometheus.yml` 抓取：

```text
/api/actuator/prometheus
```

建议：

- Prometheus 只监听本机或内网。
- Grafana 不直接公网开放，至少加 Nginx Basic Auth 或 VPN。
- 告警指标：
  - Java 进程存活
  - Python 进程存活
  - MySQL 连接池
  - Redis 内存
  - Milvus healthz
  - SSE 接口耗时和错误率
  - 磁盘剩余空间

---

## 20. 最小可执行命令顺序

如果只想快速跑起来，可以按这个顺序：

```bash
# 1. 基础服务
sudo systemctl enable --now mysql redis-server docker nginx

# 2. 数据库
mysql -h127.0.0.1 -uyuai -p yu_ai_code_mother < /opt/yu-ai-code-mother/sql/create_table.sql

# 3. Milvus
cd /opt/yu-ai-code-mother/milvus
docker compose up -d

# 4. Python
cd /opt/yu-ai-code-mother/python-agent
python3.12 -m venv .venv
.venv/bin/python -m pip install -U pip uv
.venv/bin/uv sync
PYTHONPATH=/opt/yu-ai-code-mother/python-agent .venv/bin/python rag/seed_milvus.py
sudo systemctl enable --now yuai-python-agent

# 5. 前端
cd /opt/yu-ai-code-mother/yu-ai-code-mother-frontend
npm ci
npm run build

# 6. Java
cd /opt/yu-ai-code-mother
mvn clean package -DskipTests
sudo systemctl enable --now yuai-java

# 7. Nginx
sudo nginx -t
sudo systemctl reload nginx
```

最后打开：

```text
https://your-domain.com/api/
```

---

## 21. 腾讯云侧操作清单

- [ ] 购买 CVM，Ubuntu 22.04/24.04，建议 4C16G 起。
- [ ] 绑定弹性公网 IP。
- [ ] 配置安全组：公网只开放 22、80、443。
- [ ] 域名解析 A 记录到 CVM 公网 IP。
- [ ] 申请并下载 SSL 证书，或使用 ACME 自动签发。
- [ ] 创建 COS Bucket，用于截图封面。
- [ ] 如果使用托管 MySQL/Redis，确保和 CVM 在同 VPC，使用内网地址。
- [ ] 在云监控中配置 CPU、内存、磁盘、带宽告警。
- [ ] 完成密钥轮换，不使用仓库中的历史密钥。

---

## 22. 参考文档

- 腾讯云 CVM 安全组概述：https://cloud.tencent.com/document/product/213/112610
- Docker Engine on Ubuntu：https://docs.docker.com/engine/install/ubuntu/
- Milvus Standalone Docker Compose：https://milvus.io/docs/install_standalone-docker-compose.md
