# 小规格服务器部署

适用本次已确认范围：原有 2 核 4 GB 腾讯云服务器，最多三名用户，完整应用加监控，公网 IP 访问，保留现有 MySQL/Redis/Qdrant 数据。使用原主分支的独立 worktree 构建。

## 运行结构

- Nginx 对公网提供 `http://服务器IP/api/`；Java 和 Python 分别只监听 `127.0.0.1:8123`、`:8000`。
- Java/Python 由 `rainn0coding-java.service`、`rainn0coding-python.service` 管理。
- 应用版本：`/opt/rainn0coding/releases/版本号`，`current` 指向当前版本。
- 用户生成代码、已部署页面、FTS 索引和质量数据库位于 `/opt/rainn0coding/shared`。
- Python 与 Java 共享 `shared/tmp/code_output`，避免构建结果与预览文件分离。
- Python 使用一个 worker、CPU 版 PyTorch 和本地 BGE 模型。两个入口的生成并发上限为 3；实际多任务容量以验收记录为准。
- 复用原来的三台数据容器，不执行 `down -v`，不重建数据库。
- 单独 Compose 项目运行 Prometheus/Grafana/Tempo/Collector；所有监控端口仅监听回环地址。指标保留 3 天，trace 保留 24 小时，监控容器日志轮转为每容器 2 × 10 MB。

## 首次部署顺序

1. 执行 `backup-existing.sh`，确认 `SHA256SUMS` 校验全部通过。备份包括 MySQL、Redis、Qdrant 各集合快照和原有 Compose/环境文件。
2. 执行 `provision.sh` 安装 Java/Node/Python/Nginx；Python 使用服务账号专有目录。截图功能另安装 Google 官方 Chrome deb，记录实际版本。
3. Windows 独立 worktree 中先 `npm ci && npm run build`，再使用 JDK 23 执行 Maven 打包和相关测试。不要在有未跟踪静态资源的原工作目录运行生产前端构建。
4. 单独使用本地原 venv 执行 `collect-local-secrets.py --source 原仓库 --output 私有临时JSON`，通过 SSH 上传私有目录。服务器执行 `sudo python3 configure-runtime.py --public-host 服务器IP --secrets 私有临时JSON`。这一步保留数据服务密码和已经存在的 Grafana 密码；迁移成功后删除传输用的 JSON。
5. 将本目录复制为 `/opt/rainn0coding/deployment`。显式将其中的目录权限设为 755，文件为 644；凭据只保留在 `/etc/rainn0coding`，不能放进此目录。
6. 执行 `install-python-runtime.sh`，默认使用已经验证的 `requirements.lock`。只有主动更新依赖时才使用 `REGENERATE_LOCK=1`。
7. 将本地缓存中 `BAAI/bge-small-zh-v1.5` 的完整单个 snapshot 解引用打包，解压到 `/opt/rainn0coding/tools/models/bge-small-zh-v1.5`。模型必须有 `model.safetensors`、tokenizer 和 pooling 配置。运行环境固定 `HF_HUB_OFFLINE=1`，不依赖运行时下载模型。
8. 将 JAR 和不含 `.env`/`.venv`/缓存的 `python-agent.tar.gz` 上传到 `/home/ubuntu/rainn0coding-release-upload`。核对本地和云端 JAR SHA256，执行 `activate-release.sh 新版本号`。
9. `sudo systemctl start rainn0coding-python`。执行 `sudo docker compose -f /opt/rainn0coding/deployment/monitoring/compose.yml up -d`。
10. 逐项完成以下验收，不能仅凭容器启动或页面能打开宣称部署成功。

## 验收

```bash
curl -fsS http://127.0.0.1:8123/api/actuator/health
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:3001/api/health
curl -fsS http://127.0.0.1:9090/-/ready
curl -fsS http://127.0.0.1:3200/ready
sudo systemctl show rainn0coding-java rainn0coding-python -p Id -p MemoryCurrent -p NRestarts
docker stats --no-stream
```

`check-rag.py` 需要以服务账号、Python 环境文件和应用 PYTHONPATH 运行，验证 512 维向量和 Qdrant 搜索。默认只读取；仅首次创建 SQLite 索引时加 `--seed-sqlite` 写入 FTS 种子。不会重新灌入已有 Qdrant 集合。

`live-smoke.py` 以 root 运行，创建专用验收账号并真实调用模型生成 Vue 应用，然后发布并读取页面。账号凭据仅在 `/etc/rainn0coding/smoke-account.json`，结果在 `shared/verification`。脚本会产生正常模型调用用量。继续通过浏览器检查实际交互、查询 Prometheus 两个 target 和 Tempo trace。已有用户账号和密码保持不变。

继续已有应用验收可加 `--app-id 应用ID --message 修改要求`。仅重新构建发布时使用 `--app-id 应用ID --publish-only`，不会再次调用模型。脚本检查 HTML 和其引用的 JS/CSS，实际交互仍需浏览器验收。生成可能较慢，脚本读超时为 900 秒；建议通过 `systemd-run` 启动验收，以免本机重启或 SSH 中断终止它。

生成的 Vite 应用使用 `npm run build -- --base=./` 构建，确保资源能在 `/api/static/发布键/` 下加载。Python 的 Node 后端项目仍保留原构建命令。

ChromeDriver 必须与 Chrome 版本匹配。当前 `152.0.7977.82`，驱动来自 Google 官方 Chrome for Testing。云端无法直接下载时，在本机下载对应 `linux64/chromedriver-linux64.zip` 后通过 SCP 上传，使用 `python3 -m zipfile -e` 解压；将驱动以 755 权限安装到 `/opt/rainn0coding/.cache/selenium/chromedriver/linux64/152.0.7977.82/chromedriver`，归属 `rainn0coding`。执行 `chromedriver --version` 后再测试截图。升级 Chrome 时同时更新驱动缓存。

本次实测记录见 [ACCEPTANCE.md](ACCEPTANCE.md)。

Kafka 代码生成队列的独立部署、资源预算、发布维护锁与回滚步骤见 [kafka/README.md](kafka/README.md)。Kafka 上线状态以新增验收记录为准，不能用旧部署记录代替。

## 日常访问与维护

Windows PowerShell 中建立监控隧道（保持终端开启）：

```powershell
ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -L 127.0.0.1:13001:127.0.0.1:3001 ubuntu@服务器IP
```

然后打开 `http://127.0.0.1:13001`。Grafana 用户为 `admin`；初始密码由服务器随机生成，保存在 `/etc/rainn0coding/grafana.env`，通过私有 SSH 会话查看。不要把该文件发到公开位置。

```bash
sudo journalctl -u rainn0coding-java -u rainn0coding-python -n 100 --no-pager
sudo systemctl restart rainn0coding-python rainn0coding-java
sudo docker compose -f /opt/rainn0coding/deployment/monitoring/compose.yml ps
```

备份存放在 `/home/ubuntu/rainn0coding-backups`；它是同机备份，不能替代异地备份。发布后的新数据还需要新的定期备份。首次安装没有旧应用版本可回退；以后版本可用 `rollback.sh` 回到 `previous`，不会覆盖数据卷。依赖升级需额外保留和恢复旧环境，本脚本仅回退应用代码。

当前是无域名的 HTTP 演示入口。HTTPS 尚未配置。多语言生成中，当前已安装 Java、Python、Node；Go/Rust 编译器并非本次默认安装内容，生成对应语言后的编译验收需单独记录。
