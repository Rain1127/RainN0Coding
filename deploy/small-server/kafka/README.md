# 单节点 Kafka 代码生成队列

仅用于现有 Linux 演示服务器；Java 由宿主机 systemd 运行。官方 `apache/kafka:4.3.1` 使用 KRaft broker/controller 合并模式。没有 ZooKeeper、额外服务器或本机 Docker Desktop。

两个 Kafka listener 均显式绑定 `127.0.0.1`，使用 host 网络使 Java 与 advertised listener 保持一致。不要为 9092/9093 开放公网防火墙。数据卷固定为 `rainn0coding_kafka_data`，cluster ID 与该卷一起保持不变；重启、重建容器和回滚时都不能删除卷。

## 资源与限制

- JVM 初始堆 256 MiB，最大堆 512 MiB；容器上限 1 GiB（含原生内存和页缓存），禁止该容器使用 swap。健康检查 CLI 的堆独立限制为 64 MiB。
- 一个业务 topic、一个分区、一个副本，初期 Java 并发为 1。同机单节点不提供 broker 故障高可用或整机断电零丢失保证；任务及投递记录仍以 MySQL 为准。
- 业务日志保留 7 天、每分区 256 MiB，16 MiB 分段、每小时滚动；删除以日志段为单位，大小不是磁盘硬配额。Kafka 内部 topic 和元数据还会使用额外空间。容器日志为 2 × 10 MiB。
- 2026-09-16 只读核验：服务器总内存 3655 MiB，可用 1635 MiB，swap 已用 486 MiB，磁盘余 40 GiB。Java/Python 均健康且重启次数为 0。这是部署前空闲快照，不能代替 Kafka 上线后真实生成峰值验收。

## 发布顺序

1. 核对当前发布和源码。2026-09-16 现网为 `20260910-pause-resume`，manifest commit `4ed388f2ddc5a0579fb4991859835d14ee6fbef1`。新发布须合并已有暂停/恢复功能，不能直接覆盖为 9 月 8 日旧版本。保留 `/opt/rainn0coding/shared/checkpoints` 和 `/etc/rainn0coding`。
2. 备份 MySQL、`java.env`、当前发布 manifest、检查点目录和代码文件。先停止新生成请求并等待现有执行结束；备份中包含凭据的文件仅存放在服务器受限目录。保留旧发布路径和校验和。队列版本后续发布时设置 `generation_queue_lock` 中 `id=1` 的 `paused=1`，原子停止新提交和新认领；等待 `generation_task` 的 `RUNNING`、`PAUSING` 数量为 0 后切换版本。保留 `QUEUED` 待消费记录和 `PAUSED` 检查点/占位，健康检查通过后再解除维护锁。首次接入队列前仍通过现有生成状态排空旧执行。
3. 将本目录上传到 `/opt/rainn0coding/deployment/kafka`，保持脚本 LF 换行。运行 `sudo bash /opt/rainn0coding/deployment/kafka/start.sh`。脚本检查资源/端口、拉取固定镜像、启动容器、创建 topic 并核验；它不修改现有数据库或应用环境。
4. 应用增量 SQL 迁移，检查表和约束；部署通过前后端/Python测试的队列版本。将 `java-queue.env.example` 中三个键合并到现有 `/etc/rainn0coding/java.env`，保留所有其他值与权限，不运行旧的全量 `configure-runtime.py` 覆盖后续部署配置。配置前缀为 `app.generation-queue`。
5. 确认 Java 优雅停止时限覆盖当前任务收尾；原 systemd `TimeoutStopSec=45` 不能用于强行重启正在运行的长任务。实际发布必须先暂停接收、排空再切换，不能依赖 kill 后自动重跑。
6. 重启应用并检查原健康检查、旧页面、暂停/恢复、队列指标与以下验收。记录镜像实际 digest、发布 SHA256 和测试结果。

```bash
sudo bash /opt/rainn0coding/deployment/kafka/verify.sh
sudo docker exec -e KAFKA_HEAP_OPTS='-Xms32m -Xmx64m' rainn0coding-kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server 127.0.0.1:9092 --list
```

默认 topic 为 `rain-code-generation-v1`，Java consumer group 为 `rain-code-generation-workers-v1`；若修改 Java topic，运行脚本时同步设置 `GENERATION_QUEUE_TOPIC`。已存在的 topic 不会被静默更改；分区/副本不符合 1/1 时校验失败，需先排查。

## 完成标准

静态 Compose 解析与 `bash -n` 只验证部署文件。上线验收另需：5 个替身任务始终仅一个执行；刷新/断开后生成继续且可恢复事件；幂等/所有权检查；Kafka 暂停时 outbox 保留及恢复投递；重复消息不重复执行；服务重启后排队与中断终态正确；真实模型生成、文件、聊天与预览成功。验证原暂停/恢复和旧应用仍可用。

持久化用独立验收 topic 写入标记，重启 Kafka 后读取相同标记，记录结果；不要向业务 topic 注入无效任务。重启前停止业务消费并确保没有运行任务。同步记录 `verify.sh`、`docker stats`、`free -m` 和磁盘快照；监控 OOM、重启次数及真实构建峰值。

## 回滚

回滚到队列版本时，先设置维护锁阻止新提交/认领，等待 RUNNING/PAUSING 数量为 0，保留 QUEUED 与 PAUSED，切回兼容发布版本，验证后解除维护锁。回滚到没有队列能力的旧版本前，则需先单独停止新提交并让排队任务消费完成，对 PAUSED 任务逐个明确恢复或终结方案；不能仅暂停 broker 后把未完任务留给不认识它们的旧版本。无法完成的任务须保留事件并明确终态，禁止遗留假运行状态。记录处理证据后，关闭 Java queue 配置并切回已备份的发布版本。保留新增表、MySQL数据、Kafka topic、offset、数据卷和 Python 检查点，不执行 `down -v`。

应用回滚并完成原功能健康检查后，运行 `sudo env QUEUE_DRAIN_VERIFIED=yes bash /opt/rainn0coding/deployment/kafka/stop-after-drain.sh`。该脚本仅停止 Kafka，不代表它自动核实了数据库排空；操作人必须先完成上述核验。后续重新启用从相同卷启动。

官方依据：[Apache Kafka 下载](https://kafka.apache.org/community/downloads/)、[4.3.1 官方单节点示例](https://github.com/apache/kafka/blob/4.3.1/docker/examples/docker-compose-files/single-node/plaintext/docker-compose.yml)、[4.3 broker 配置](https://kafka.apache.org/43/configuration/broker-configs/)。
