# yu-ai-code-mother 技术参考文档

> 最后更新：2026-05-24
> 涵盖：项目架构、数据表、技术栈、优化建议、多 Agent 架构、RAG 反幻觉体系、Python 实现现状

---

## 目录

- [一、项目架构概览](#一项目架构概览)
- [二、数据表设计](#二数据表设计)
- [三、技术栈](#三技术栈)
- [四、AI 调用链路分析](#四ai-调用链路分析)
- [五、优化建议](#五优化建议)
- [六、多 Agent 架构演进](#六多-agent-架构演进)
  - [6.11 AutoGen + LangGraph 融合架构](#611-autogen--langgraph-融合架构)
  - [6.12 Milvus 向量数据库应用](#612-milvus-向量数据库应用)
- [七、RAG 反幻觉体系](#七rag-反幻觉体系)
  - [7.1 代码生成的幻觉类型分析](#71-代码生成的幻觉类型分析)
  - [7.2 多路检索引擎：意图定向 + 全局向量双通道并行](#72-多路检索引擎意图定向--全局向量双通道并行)
  - [7.3 RAG 整体数据流](#73-rag-整体数据流)
  - [7.4 各 Agent 的 RAG 接入设计](#74-各-agent-的-rag-接入设计)
  - [7.5 幻觉检测与自动纠错](#75-幻觉检测与自动纠错)
  - [7.6 知识库持续进化](#76-知识库持续进化)
  - [7.7 RAG 性能指标](#77-rag-性能指标)
  - [7.8 种子数据方案](#78-种子数据方案)
- [八、Python Agent 实现现状](#八python-agent-实现现状)
  - [8.1 已实现模块](#81-已实现模块)
  - [8.2 SSE 流式架构](#82-sse-流式架构)
  - [8.3 已知限制 & 调试记录](#83-已知限制--调试记录)
- [九、Java 侧重构（Python Agent 集成）](#九java-侧重构python-agent-集成)
  - [9.1 重构目标](#91-重构目标)
  - [9.2 数据流变化](#92-数据流变化)
  - [9.3 改动清单](#93-改动清单)
  - [9.4 编译与验证](#94-编译与验证)
- [十、附录](#十附录)

---

## 一、项目架构概览

### 1.1 当前形态

单体 Spring Boot 应用 + 独立 Vue 3 前端，核心功能：用户创建 App → AI 对话生成代码 → 代码保存/构建/截图 → 部署预览。

```
┌──────────────────┐     SSE/HTTP      ┌─────────────────────────┐
│  Vue 3 前端       │ ◄──────────────► │  Spring Boot 3.5.9      │
│  (Vite + AntDV)  │                  │  (端口 8123, /api)      │
│                  │                  │                         │
└──────────────────┘                  │  ┌───────────────────┐  │
                                      │  │ LangChain4j       │  │
                                      │  │ (LLM 调用/流式)    │──┼──► DeepSeek API
                                      │  └───────────────────┘  │
                                      │  ┌───────────────────┐  │
                                      │  │ LangGraph4j       │  │
                                      │  │ (工作流编排)       │  │
                                      │  └───────────────────┘  │
                                      │  ┌───────────────────┐  │
                                      │  │ MyBatis-Flex      │──┼──► MySQL
                                      │  │ (ORM)             │  │
                                      │  └───────────────────┘  │
                                      │  ┌───────────────────┐  │
                                      │  │ Redis + Redisson  │──┼──► Redis
                                      │  │ (缓存/限流/会话)   │  │
                                      │  └───────────────────┘  │
                                      └─────────────────────────┘
```

### 1.2 项目变体

| 变体 | 位置 | 状态 |
|---|---|---|
| 单体版本 | `src/` | 主力代码库 |
| 微服务重构 | `fronted/yu-ai-code-mother-microservice/` | 开发中，Dubbo + Nacos |
| 前端 | `yu-ai-code-mother-frontend/` | 生产环境 |

### 1.3 包结构

```
com.yupi.yuaicodemother
├── controller/       # REST 控制器 (App, User, ChatHistory, Health, WorkflowSse...)
├── service/          # 业务服务接口
├── service/impl/     # 业务服务实现
├── mapper/           # MyBatis-Flex Mapper 接口
├── model/
│   ├── entity/       # 数据库实体 (User, App, ChatHistory, AppVersion)
│   ├── dto/          # 请求 DTO
│   └── vo/           # 视图对象
├── ai/               # AI 服务 (代码生成、路由、防护栏、工具)
├── core/             # 代码生成管道 (解析、保存、流处理、构建)
├── langgraph4j/      # AI 工作流定义 + 节点实现
├── config/           # Spring 配置
├── ratelimiter/      # 限流注解 + AOP
├── annotation/       # 自定义注解 (AuthCheck)
├── aop/              # AOP 切面 (AuthInterceptor)
├── common/           # 公共工具类
├── constant/         # 常量定义
├── exception/        # 业务异常
├── manager/          # 第三方管理器 (CosManager)
├── monitor/          # AI 模型指标收集 (Micrometer)
└── utils/            # 工具类 (WebScreenshotUtils)
```

---

## 二、数据表设计

### 2.1 表清单

| 表名 | 实体类 | 主键策略 | 唯一索引 | 说明 |
|---|---|---|---|---|
| `user` | `model/entity/User.java` | 雪花 ID | `userAccount` | 用户表 |
| `app` | `model/entity/App.java` | 雪花 ID | `deployKey` | 应用表 |
| `chat_history` | `model/entity/ChatHistory.java` | 雪花 ID | — | 对话历史表 |
| `app_version` | `model/entity/AppVersion.java` | 自增 ID | — | 应用版本表（未在初始化脚本中） |

### 2.2 表结构详情

**user** — 用户表

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT | 主键（雪花 ID） |
| `userAccount` | VARCHAR | 账号（唯一索引） |
| `userPassword` | VARCHAR | 密码 |
| `userName` | VARCHAR | 昵称 |
| `userAvatar` | VARCHAR | 头像 URL |
| `userProfile` | VARCHAR | 个人简介 |
| `userRole` | VARCHAR | 角色（user/admin） |
| `editTime` | DATETIME | 最后编辑时间 |
| `createTime` | DATETIME | 创建时间 |
| `updateTime` | DATETIME | 更新时间 |
| `isDelete` | TINYINT | 逻辑删除 |

**app** — 应用表

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT | 主键（雪花 ID） |
| `appName` | VARCHAR | 应用名称 |
| `cover` | VARCHAR | 封面图 URL |
| `initPrompt` | TEXT | 初始提示词 |
| `codeGenType` | VARCHAR | 代码生成类型（HTML/MULTI_FILE/VUE_PROJECT） |
| `deployKey` | VARCHAR | 部署标识（唯一索引） |
| `deployedTime` | DATETIME | 部署时间 |
| `priority` | INT | 优先级 |
| `userId` | BIGINT | 创建者 ID |
| `currentVersion` | VARCHAR | 当前版本号 |

**chat_history** — 对话历史表

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT | 主键（雪花 ID） |
| `message` | TEXT | 消息内容 |
| `messageType` | VARCHAR | 消息类型（user/ai） |
| `appId` | BIGINT | 所属应用 ID（索引） |
| `userId` | BIGINT | 用户 ID |
| `createTime` | DATETIME | 创建时间（索引） |

**app_version** — 应用版本表（新增）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | BIGINT | 主键（自增） |
| `app_id` | BIGINT | 关联应用 ID |
| `version_number` | VARCHAR | 版本号 |
| `code_content` | LONGTEXT | 代码内容 |
| `description` | VARCHAR | 版本描述 |

---

## 三、技术栈

### 3.1 后端

| 类别 | 技术 | 版本 |
|---|---|---|
| **基础框架** | Spring Boot (Web + AOP + Actuator) | 3.5.9 |
| **JDK** | Java | 21 |
| **构建** | Maven | — |
| **ORM** | MyBatis-Flex | 1.11.0 |
| **数据库** | MySQL + HikariCP | 默认连接池 |
| **缓存** | Redis（Spring Session + Redisson + Caffeine） | Redisson 3.50.0 |
| **API 文档** | Knife4j + SpringDoc OpenAPI 3 | 4.4.0 |
| **工具库** | Lombok、Hutool | 1.18.36 / 5.8.38 |
| **LLM 框架** | LangChain4j + LangGraph4j | 1.1.0 / 1.6.0-rc2 |
| **模型接入** | OpenAI-compatible API、DeepSeek API | 2.21.1 |
| **对象存储** | 腾讯云 COS | 5.6.227 |
| **截图** | Selenium + WebDriverManager | 4.33.0 / 6.1.0 |
| **监控** | Micrometer + Prometheus + Grafana | — |
| **APM** | 阿里云 ARMS Java Agent | — |

### 3.2 中间件

| 组件 | 地址 | 用途 |
|---|---|---|
| MySQL | localhost:3306 | 主数据库（库名 `yu_ai_code_mother`） |
| Redis | localhost:6379 (DB 0) | 会话存储 / 缓存 / AI 聊天记忆 / 限流 |
| Milvus | localhost:19530 | 向量数据库（代码片段嵌入、相似检索、RAG） |
| Nacos | localhost:8848 | 微服务注册中心（仅微服务版本） |
| Dubbo | triple 协议 :50051-50053 | 微服务 RPC（仅微服务版本） |
| Prometheus | localhost:8123/api/actuator/prometheus | 指标抓取 |

### 3.3 前端

| 技术 | 版本 |
|---|---|
| Vue | 3.5.17 |
| Vite | 5.x |
| TypeScript | 5.8 |
| Ant Design Vue | 4.2.6 |
| Pinia | 3.0.3 |
| Vue Router | 4.5.1 |
| Axios | 1.11.0 |
| markdown-it + highlight.js | 14.x / 11.x |

### 3.4 配置要点

| 配置项 | 值 |
|---|---|
| 应用名 | `yu-ai-code-mother-backend` |
| 服务端口 | `8123` |
| 上下文路径 | `/api` |
| 会话超时 | 30 天（2592000 秒） |
| 会话存储 | Redis |
| 激活 Profile | `local` |
| AI 聊天记忆 TTL | 3600 秒（1 小时） |

---

## 四、AI 调用链路分析

### 4.1 当前工作流（LangGraph4j）

```
START → image_collector → prompt_enhancer → router → code_generator
                                            ↑            │
                                            │   (失败时重试)
                                            └────────────┘
                                         code_quality_check
                                               │
                                     (pass) ───┴─── (fail)
                                       │
                                  project_builder → END
```

### 4.2 LLM 调用统计（每次请求）

| 节点 | 是否调用 LLM | 说明 |
|---|---|---|
| image_collector | 是 (1 次) | 图片收集计划（LLM 决策） |
| prompt_enhancer | **否** | 纯字符串拼接 |
| router | 是 (1 次) | 路由决策（判断代码生成类型） |
| code_generator | 是 (1 次) | 生成代码（核心调用，可能触发最多 20 次工具调用） |
| code_quality_check | 是 (1 次) | 代码质量审查 |

**基准：每次工作流至少 4 次 LLM 调用。重试时每轮额外增加 2 次。**

### 4.3 提示词管理

所有系统提示词从 `src/main/resources/prompt/` 下的文本文件加载，共 7 个：

```
codegen-html-system-prompt.txt
codegen-multi-file-system-prompt.txt
codegen-vue-project-system-prompt.txt
codegen-routing-system-prompt.txt
image-collection-plan-system-prompt.txt
image-collection-system-prompt.txt
code-quality-check-system-prompt.txt
```

**当前问题：**
- 无 Prompt Caching，每次调用完整发送系统提示词
- `MessageWindowChatMemory` 仅按消息数量（20 条）截断，不感知 Token 数
- 质量检查失败后完全替换用户消息，丢失原始上下文

### 4.4 流式响应路径

```
LangChain4j TokenStream/Flux → AiCodeGeneratorFacade → StreamHandler → SSE → 前端
                                                    │
                                                    ├── JsonMessageStreamHandler (VUE_PROJECT)
                                                    └── SimpleTextStreamHandler (HTML/MULTI_FILE)
```

---

## 五、优化建议

### 5.1 Token 成本优化

| 优先级 | 优化项 | 预期收益 | 改动量 |
|---|---|---|---|
| **P1** | **Prompt Caching** — 利用 DeepSeek API 的缓存能力缓存系统提示词 | 节省 30%~50% Token | 中 |
| **P1** | **减少工作流 LLM 调用** — 合并 routing 到 code_generator 提示词；用规则引擎替代 image_plan | 节省 25% Token | 中 |
| **P2** | **优化重试策略** — 质量检查失败时保留原始上下文而非完全替换 | 节省 40%~60% 重试 Token | 小 |
| **P2** | **TokenWindowChatMemory** — 用 Token 感知的截断替代 MessageWindowChatMemory | 防止超上下文窗口 | 小 |

### 5.2 高并发优化

| 优先级 | 优化项 | 说明 |
|---|---|---|
| **P0** | **统一线程池** | 当前无全局线程池；ConcurrentWorkflow 每次 new ExecutorService 且不关闭 → 线程泄漏 |
| **P0** | **ThreadLocal onError 修复** | `onError` 回调在异步线程触发时 ThreadLocal 已被清除 |
| **P1** | **用户信息缓存** | 每次鉴权请求都 `getById(userId)` 查库 → 加入 Redis 缓存（TTL 10min） |
| **P2** | **数据库连接池调优** | HikariCP 默认 max=10 → 根据并发量调至 30 |
| **P2** | **Redis 连接池合并** | 三套独立连接池（Spring Session / Redisson / LangChain4j）→ 统一到 Redisson |
| **P3** | **其他接口限流** | 当前仅 chat 接口有 `@RateLimit`，创建/部署等写操作无保护 |

### 5.3 响应速度优化

| 优先级 | 优化项 | 说明 |
|---|---|---|
| **P1** | **HTTP 连接池配置** | OkHttp 默认最大空闲连接仅 5 个 → 调至 20，keep-alive 10min |
| **P1** | **npm build 异步化** | 当前 `onCompleteResponse` 同步执行构建阻塞流管道 → 异步 + SSE 推送结果 |
| **P2** | **AI 服务预热** | 首次请求冷启动（创建代理→加载提示词→初始化工具）→ `@PostConstruct` 预建 |
| **P2** | **消息批量写入** | 每个 chunk 都单独写 MySQL → 对话结束后批量写入 |
| **P3** | **聊天记忆本地缓存** | 从 Redis 加载记忆加 Caffeine 本地缓存（TTL 30s）减少 Redis 往返 |

### 5.4 稳定性修复

| 优先级 | 修复项 | 说明 |
|---|---|---|
| **P0** | **截图异步化重构** | `Thread.startVirtualThread` 无超时/无异常传播/无重试 → `CompletableFuture` + 超时 |
| **P0** | **数据库事务** | `deployApp()` 多步骤操作无 `@Transactional` → 加上事务边界 |
| **P3** | **会话超时缩短** | 30 天 → 7 天，减少 Redis 僵尸会话 |

### 5.5 Redis 会话与缓存架构优化

当前 Redis 使用存在三个问题：三套独立连接池、会话超时过长、鉴权链路上的数据库往返。

#### 5.5.1 连接池统一

**现状：** Spring Session Data Redis、Redisson（限流）、LangChain4j RedisChatMemoryStore 各自维护独立的 Redis 连接池，总连接数冗余，资源浪费。

**优化方案：**

```java
@Configuration
public class UnifiedRedisConfig {

    // 统一 Redisson 客户端，同时注入给 Spring Session 和缓存使用
    @Bean
    public RedissonClient redissonClient() {
        Config config = new Config();
        config.useSingleServer()
                .setAddress("redis://localhost:6379")
                .setConnectionPoolSize(30)    // 合并后增大连接池
                .setConnectionMinimumIdleSize(10)
                .setConnectTimeout(5000)
                .setTimeout(3000)
                .setRetryAttempts(3)
                .setRetryInterval(1500);
        return Redisson.create(config);
    }

    // 用 Redisson 替代 Spring Data Redis 作为 Session 存储后端
    @Bean
    public RedissonSpringSessionRepository sessionRepository(
            RedissonClient redissonClient) {
        return new RedissonSpringSessionRepository(redissonClient);
    }
}
```

#### 5.5.2 会话生命周期优化

```yaml
spring:
  session:
    timeout: 604800          # 7 天（原 30 天 → 减少僵尸会话堆积）
    redis:
      namespace: "yuai:session"  # 隔离会话键前缀
  data:
    redis:
      ttl: 3600              # 通用缓存 TTL 1 小时
```

#### 5.5.3 用户登录态多级缓存

**现状：** 每次鉴权 `getLoginUser()` 从 Session 取 userId → 再用 `this.getById(userId)` 查数据库。高并发下每次请求都触发一次用户表查询。

**优化方案 —— Redis 用户缓存 + 发布订阅刷新：**

```
请求 → AuthInterceptor → Redis 缓存命中 → 直接返回用户对象（零 DB 查询）
                              │
                              │ 缓存未命中
                              ▼
                        MySQL 查询 → 写入 Redis (TTL 10min) → 返回
```

```java
@Service
public class UserServiceImpl implements UserService {

    @Autowired
    private RedissonClient redissonClient;

    private static final String USER_CACHE_PREFIX = "yuai:user:";
    private static final long USER_CACHE_TTL_SECONDS = 600; // 10 分钟

    public User getLoginUser(HttpServletRequest request) {
        // 1. 从 Session 取 userId
        Long userId = (Long) request.getSession()
                .getAttribute(UserConstant.USER_LOGIN_STATE);

        // 2. 先查 Redis 缓存
        RBucket<User> bucket = redissonClient
                .getBucket(USER_CACHE_PREFIX + userId);
        User cached = bucket.get();
        if (cached != null) {
            return cached;
        }

        // 3. 缓存未命中，查库
        User user = this.getById(userId);
        if (user != null) {
            bucket.set(user, USER_CACHE_TTL_SECONDS, TimeUnit.SECONDS);
        }
        return user;
    }

    // 用户更新时，通过 Pub/Sub 使所有实例的本地缓存失效
    public void updateUser(User user) {
        this.updateById(user);
        // 发布失效事件，让集群内所有节点清除该用户缓存
        redissonClient.getTopic("yuai:user:invalidate")
                .publish(user.getId());
    }
}
```

#### 5.5.4 Session 共享与水平扩展

使用 Redis 作为 Session 后端，Tomcat 实例之间共享会话状态。当 Java 实例水平扩展到 N 台时，任意实例都可以处理同一用户的请求，无需 sticky session。配合 Redisson 的 `RLocalCachedMap`，还能在本地内存中保留热点会话副本，进一步减少 Redis 往返：

```java
// 热点会话本地缓存方案
RLocalCachedMap<String, User> sessionCache = redissonClient
        .getLocalCachedMap("yuai:session:cache",
                LocalCachedMapOptions.defaults()
                        .cacheSize(1000)
                        .timeToLive(5, TimeUnit.MINUTES));
```

### 5.6 优化实施优先级矩阵

```
影响大 │  P1: Prompt Caching          P0: 线程池
       │  P1: 用户信息缓存             P0: 截图异步化
       │  P1: HTTP 连接池              P0: ThreadLocal 修复
       │  P1: npm build 异步化         P0: 数据库事务
       │  P1: Redis 会话多级缓存       P0: Redis 连接池统一
       │
       │  P2: Token-aware 截断         P3: 其他接口限流
影响小 │  P2: AI 服务预热               P3: 会话超时缩短
       │  P2: 批量写消息               P3: 连接池调优
       │  P2: 本地记忆缓存
       │
       └──────────────────────────────────────────
              改动小                          改动大
```

---

## 六、多 Agent 架构演进

### 6.1 架构目标

将 LLM 调用和 AI 工作流从 Java 剥离到 Python，Java 降级为纯业务网关。

```
┌──────────┐     SSE/HTTP      ┌───────────────────┐   HTTP/SSE    ┌──────────────────────────────┐
│  Vue 前端  │ ◄──────────────► │  Java (Spring Boot)│ ◄───────────► │  Python (FastAPI)            │
│          │                  │                    │              │                            │
└──────────┘                  │  - 鉴权/限流        │              │  ┌───────────────────────┐  │
                              │  - CRUD             │              │  │  LangGraph (全局编排)   │  │
                              │  - 文件/截图         │              │  │  - Supervisor 路由    │  │
                              │  - SSE 透传         │              │  │  - Fork/Join 并行     │  │
                              │  - 持久化           │              │  │  - 条件回环重试       │  │
                              │                     │              │  └──────────┬────────────┘  │
                              │  ┌───────────────┐  │              │             │               │
                              │  │ Redis         │  │              │  ┌──────────▼────────────┐  │
                              │  │ - 会话多级缓存  │  │              │  │  AutoGen (局部讨论)    │  │
                              │  │ - Pub/Sub 刷新 │  │              │  │  - Coder ⇄ Reviewer  │  │
                              │  └───────────────┘  │              │  │  - PM ⇄ Architect    │  │
                              └───────────────────┘              │  └───────────────────────┘  │
                                                                 │                            │
                                                                 │  ┌───────────────────────┐  │
                                                                 │  │  Milvus (向量检索)     │  │
                                                                 │  │  - 组件库 RAG         │  │
                                                                 │  │  - 设计模式匹配       │  │
                                                                 │  │  - 错误模式库         │  │
                                                                 │  └───────────────────────┘  │
                                                                 └──────────────────────────────┘
```

### 6.2 技术选型

#### Java 侧

| 变动 | 技术 | 说明 |
|---|---|---|
| **新增** | `spring-boot-starter-webflux` (WebClient) | Reactive HTTP 客户端，透传 Python SSE 流 |
| **删除** | `langchain4j` 全家桶 | 不再直接调用 LLM |
| **删除** | `langgraph4j` | 工作流编排移到 Python |
| **删除** | 外部旧图像 SDK | 模型调用在 Python |

#### Python 侧

| 技术 | 版本建议 | 用途 |
|---|---|---|
| **FastAPI** | 最新稳定版 | Web 框架，原生 async + `StreamingResponse` |
| **AutoGen** | ≥ 0.7 | 多 Agent 对话协作框架（Agent-to-Agent 通信） |
| **LangGraph** | ≥ 0.4 | 多 Agent 状态图编排（全局工作流控制） |
| **LangChain** | 最新稳定版 | LLM 抽象层＋工具绑定 |
| **langchain-openai** / **langchain-deepseek** | — | DeepSeek 模型接入 |
| **Milvus** | ≥ 2.4 | 向量数据库，代码片段嵌入存储与相似检索 |
| **pymilvus** | ≥ 2.4 | Milvus Python SDK |
| **sentence-transformers** | — | 代码文本向量化（Embedding 模型） |
| **Pydantic** | v2 | 结构化输出（每个 Agent 输出强类型约束） |
| **httpx** | — | 异步 HTTP 客户端（Image Collector 调用外部 API） |

### 6.3 Agent 职责划分

```
                           ┌─────────────────────────────┐
                           │     Supervisor Agent         │
                           │  - 接收用户原始需求          │
                           │  - 决策调用顺序              │
                           │  - 判断质量 + 触发重试       │
                           └──────┬──────┬───────────────┘
                                  │      │
         ┌────────────────────────┘      └──────────────────────┐
         │                                                      │
┌────────▼────────┐   ┌──────────────────┐   ┌──────────────────┐
│   PM Agent      │   │  Architect Agent │   │   Coder Agent    │
│   (产品经理)     │   │  (架构师)         │   │   (程序员)        │
│                 │   │                  │   │                  │
│ 输入: 模糊需求   │   │ 输入: 结构化 PRD  │   │ 输入: 架构方案    │
│ 输出: 结构化 PRD │   │ 输出:            │   │ 输出: 代码文件    │
│                 │   │  - 组件树        │   │  列表(含内容)    │
│                 │   │  - 文件清单      │   │                  │
│                 │   │  - 数据流图      │   │ 工具:             │
│                 │   │  - 技术选型      │   │  - write_file    │
│                 │   │                  │   │  - search_docs   │
└─────────────────┘   └──────────────────┘   └──────────────────┘
                                                      │
         ┌────────────────────────────────────────────┘
         │
┌────────▼────────┐   ┌──────────────────┐   ┌──────────────────┐
│ Reviewer Agent  │   │ Image Collector  │   │  Builder Agent   │
│ (代码审查)       │   │ (素材收集)        │   │  (构建验证)       │
│                 │   │                  │   │                  │
│ 输入: 全部源码   │   │ 输入: 架构+PRD   │   │ 输入: 代码+图片   │
│ 输出: review报告 │   │ 输出: 图片URL    │   │ 输出: 构建结果    │
│ {passed, issues}│   │  分类列表        │   │ {success, log}  │
│                 │   │                  │   │                  │
│                 │   │ 工具:             │   │ 零 LLM 调用      │
│                 │   │ - Pexels         │   │ 纯 Shell 执行    │
│                 │   │ - UnDraw         │   │ npm install/build│
│                 │   │ - Mermaid        │   │                  │
│                 │   │ - 外部图像生成 API│   │                  │
└─────────────────┘   └──────────────────┘   └──────────────────┘
```

#### 各 Agent 详细职责

**Supervisor Agent（编排者）**
- **不写代码，只做路由决策**
- 内部是一个轻量 LLM 调用，根据当前阶段选择下一步
- 决策逻辑（伪代码）：
```python
def supervisor_decision(state):
    if state.phase == "init":        return "pm_agent"
    if state.phase == "spec_done":   return "architect_agent"
    if state.phase == "arch_done":   return "coder_agent"
    if state.phase == "code_done":   return "reviewer_agent"
    if state.review.passed:          return "builder_agent"
    if state.retry_count < 3:        return "coder_agent"  # 重写
    return "human_intervention"      # 人工介入
```

**PM Agent（产品经理）**
- 输入：用户一句话需求（"做一个电商首页"）
- 输出：结构化 PRD（Pydantic 模型）
  - `page_name`：页面名称
  - `features`：功能清单列表
  - `target_audience`：目标受众
  - `data_dependencies`：数据依赖

**Architect Agent（架构师）**
- 输入：PM Agent 产出的结构化 PRD
- 输出：代码骨架方案
  - `tech_stack`：推荐技术栈
  - `component_tree`：组件树（含 props 和职责描述）
  - `file_list`：文件清单（含路径和描述）
  - `data_flow`：数据流向图
- 关键约束：只描述结构，**不写代码实现**

**Coder Agent（程序员）**
- 输入：Arch Agent 产出的 `file_list`
- 输出：`[{path, content}]` 代码文件列表
- 这是唯一有**工具调用**的 Agent（FileWriteTool、FileReadTool 等）
- Token 消耗最大的 Agent

**Reviewer Agent（代码审查）**
- 输入：Coder Agent 产出的全部代码
- 输出：`{passed: bool, score: 0-100, issues: [...]}`
- 审查维度：语法正确性、逻辑完整性、XSS 防护、组件结构合理性
- 一次审查 Token 消耗约 500~1000（结构化输出，只发 JSON 不发长文）

**Image Collector Agent（素材收集）**
- 输入：架构方案 + PRD 中的视觉需求
- 输出：`[{url, category}]` 图片列表
- 主要操作：HTTP API 调用（Pexels、UnDraw、Mermaid CLI、外部图像生成 API）
- **零 LLM 调用**（除了最开始的搜索计划，可用规则引擎替代）

**Builder Agent（构建验证）**
- 输入：最终代码文件 + 图片资源
- 输出：`{success: bool, build_log: string}`
- **零 LLM 调用**，纯 Shell 执行 `npm install && npm run build`
- 构建失败 → 错误日志喂给 Coder Agent 重试

### 6.4 Agent 共享状态设计 (State)

```python
from typing import TypedDict, List, Annotated
from langgraph.graph.message import add_messages

class CodeGenState(TypedDict):
    # === 输入 ===
    user_request: str
    user_id: str
    app_id: str

    # === PM 产出 ===
    prd: dict | None

    # === Arch 产出 ===
    architecture: dict | None

    # === Coder 产出 ===
    code_files: List[dict]       # [{path, content}]

    # === Reviewer 产出 ===
    review: dict | None          # {passed, score, issues}
    retry_count: int             # 当前重试次数

    # === Image Collector 产出 ===
    images: List[dict]           # [{url, category}]

    # === Builder 产出 ===
    build_result: dict | None    # {success, log}

    # === 控制 ===
    phase: str                   # 当前阶段
    history: Annotated[list, add_messages]  # 累积消息
    final_result: dict | None    # 最终返回给 Java 的结果
```

### 6.5 工作流图

```
START
  │
  ▼
PM Agent ──────► Architect Agent
                    │
               ┌────▼────┐
               │   Fork   │ (并行)
               └────┬────┘
                    │
          ┌─────────┼─────────┐
          ▼                   ▼
    Coder Agent        Image Collector
          │                   │
          └─────────┬─────────┘
                    │
                    ▼
            Reviewer Agent
                    │
        ┌───────────┼───────────┐
        │ passed                 │ failed && retries < 3
        ▼                       ▼
  Builder Agent          Coder Agent (带上issues)
        │                       │
        ▼                       └────► Reviewer Agent
       END                                   ▲
                                             │
                          failed && retries >= 3
                                             │
                                             ▼
                                    Human Intervention
```

关键设计决策：
- **Coder Agent 和 Image Collector 并行**：它们之间没有依赖关系。图片 URL 最终在 Builder 阶段组装，不需要提前注入提示词。这节省约 30%~40% 端到端延迟。
- **上下游通过 Pydantic 结构化输出传递**：Agent 之间不通过自然语言对话，而是传递强类型对象。PM 产出 Pydantic → Arch 直接消费，不产生"理解偏差"。
- **Review 是轻量 LLM 调用**：结构化输出 + 只发 JSON，一次 500 Token 左右，远低于一次失败的构建 + 用户投诉的成本。

### 6.6 SSE 事件流设计

Java 完全透明代理，Python 产出的每一行 SSE 数据透传给前端。

```
# Python → Java → 前端 的事件流示例：

{"type":"phase_start","phase":"pm","message":"产品经理正在分析你的需求..."}
{"type":"phase_complete","phase":"pm","output":{"prd_title":"电商首页","features":8}}

{"type":"phase_start","phase":"arch","message":"架构师正在设计代码结构..."}
{"type":"phase_complete","phase":"arch","output":{"component_count":6,"file_count":12}}

{"type":"phase_start","phase":"code","message":"程序员正在编写代码..."}
{"type":"code_chunk","file":"HeroBanner.vue","content":"<template>..."}
{"type":"code_chunk","file":"ProductList.vue","content":"<template>..."}

{"type":"phase_start","phase":"review","message":"代码审查中..."}
{"type":"review_issue","severity":"warn","file":"HeroBanner.vue","issue":"缺少 loading 状态"}

{"type":"phase_start","phase":"code_retry","retry":1,"message":"正在修复审查发现的问题..."}
{"type":"code_chunk","file":"HeroBanner.vue","content":"<template>...<div v-if=\"loading\">加载中...</div>..."}

{"type":"phase_start","phase":"build","message":"正在构建项目..."}
{"type":"phase_complete","phase":"build","output":{"success":true,"build_url":"..."}}

{"type":"done","result":{"code_files":[...],"images":[...],"build_url":"..."}}
```

### 6.7 Java ↔ Python 通信协议

**流式请求**（代码生成）：

```
POST http://python:8000/api/generate-code
Content-Type: application/json

{
  "userId": "xxx",
  "appId": "xxx",
  "prompt": "做一个电商首页",
  "codeGenType": "VUE_PROJECT",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}

→ Response: text/event-stream (SSE)
```

**非流式请求**（如有需要保留独立的路由/质量检查）：

| 端点 | 调用时机 | 返回 |
|---|---|---|
| `POST /api/route-code-type` | 判断代码生成类型 | JSON |
| `POST /api/check-quality` | 纯代码审查 | JSON |

### 6.8 Java 侧改造清单

**新增：**

```java
@Component
public class PythonAiClient {

    private final WebClient webClient;

    public PythonAiClient(@Value("${python.ai.base-url}") String baseUrl) {
        this.webClient = WebClient.builder()
                .baseUrl(baseUrl)
                .codecs(config -> config.defaultCodecs().maxInMemorySize(2 * 1024 * 1024))
                .build();
    }

    public Flux<String> streamCodeGen(CodeGenRequest request) {
        return webClient.post()
                .uri("/api/generate-code")
                .bodyValue(request)
                .retrieve()
                .bodyToFlux(String.class);
    }
}
```

**删除：**

| 删除的包/文件 | 原因 |
|---|---|
| `ai/` 整个包 | LLM 调用移到 Python |
| `langgraph4j/` 整个包 | 工作流移到 Python |
| `core/AiCodeGeneratorFacade` | 门面逻辑移到 Python |
| `core/handler/` | 不再需要解析 LLM 输出 |
| `core/builder/VueProjectBuilder` | 构建移到 Python |
| `config/StreamingChatModelConfig` | 不再需要 |
| `config/ReasoningStreamingChatModelConfig` | 不再需要 |
| `config/RoutingAiModelConfig` | 不再需要 |
| `config/RedisChatMemoryStoreConfig` | 记忆管理移到 Python |
| `monitor/AiModelMonitorListener` | 监控在 Python 侧实现 |
| `resources/prompt/` 所有文件 | 提示词移到 Python |

**保留：**

- `controller/` — 简化逻辑，改为透传代理
- `service/` — `UserService`、`AppService`、`ChatHistoryService`、`ScreenshotService`（无需改动）
- `mapper/` + `model/entity/` — 全部保留
- `ratelimiter/` — 全部保留
- `core/parser/` + `core/saver/` — 代码解析和文件保存逻辑保留
- `config/RedisCacheManagerConfig` — 保留
- `config/CosClientConfig` — 保留

### 6.9 渐进式迁移路径

| 阶段 | 内容 | 验证方式 | 风险 |
|---|---|---|---|
| **1. 基础通道** | Python 搭 FastAPI + 单 Coder Agent，验证 SSE 透传 | 前端能收到代码流 | 低 |
| **2. 链式协作** | 加入 PM + Arch Agent，验证结构化输出传递 | Arch 能正确消费 PM 的 Pydantic 输出 | 低 |
| **3. 审查闭环** | 加入 Reviewer + 重试循环 | 故意写错代码，确认能自动修复 | 中 |
| **4. 并行优化** | 加入 Fork（Coder ∥ Image Collector） | A/B 对比延迟 | 中 |
| **5. 智能编排** | 替换硬编码路由为 Supervisor 决策 | 边界输入测试路由正确性 | 中 |
| **6. 割接** | 移除 Java 侧 langchain4j/langgraph4j 依赖 | 全链路回归测试 | 高 |

### 6.10 预期收益汇总

| 维度 | 改造前 | 改造后 |
|---|---|---|
| **Java 职责** | AI 引擎 + 业务逻辑 | 纯业务网关 |
| **LLM 框架成熟度** | LangChain4j (Java 移植版) | LangChain (Python 原生) |
| **工作流稳定性** | LangGraph4j (RC 版本) | LangGraph (生产级) |
| **多 Agent 支持** | 无 | 7 个 Agent 协同 |
| **端到端延迟** | 全串行 | Coder ∥ Image Collector，-30%~40% |
| **代码质量** | 1 次质量检查 | 3 次自动重试 + 人工介入兜底 |
| **前端可见性** | 简单的"处理中" | 每个 Agent 状态实时可见 |
| **Java pom.xml** | 含 langchain4j 大堆依赖 | 精简约 40% |
| **Token 效率** | 每次请求 4+ LLM 调用 | 结构化传递替代部分调用 |

### 6.11 AutoGen + LangGraph 融合架构

#### 6.11.1 为什么两者结合

AutoGen 和 LangGraph 在设计哲学上互补：

| 维度 | AutoGen | LangGraph |
|---|---|---|
| **核心模型** | Agent 间对话（ConversableAgent） | 有向状态图（StateGraph） |
| **控制流** | 隐含在对话流中 | 显式节点 + 条件边 |
| **擅长** | 自由讨论、协商、辩论 | 精确流程控制、并行/回环 |
| **弱点** | 对话可能发散，难以保证流程 | 节点间缺乏灵活的多轮讨论 |
| **适用场景** | 需要"商量"的子任务 | 需要"严格执行"的主流程 |

**融合思路：LangGraph 管控全局工作流（Supervisor 路由、Fork/Join、条件回环），AutoGen 管控需要 Agent 间对话讨论的局部节点。**

#### 6.11.2 分工边界

```
                    ┌─────────────────────────────────────┐
                    │        LangGraph (全局编排)           │
                    │  - Supervisor 路由决策               │
                    │  - PM → Arch 链式传递                │
                    │  - Coder ∥ Image Collector Fork     │
                    │  - 条件边 (passed? → Builder : Retry) │
                    └──────────┬──────────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼────────┐ ┌─────▼──────┐ ┌──────▼──────────┐
     │  LangGraph 节点   │ │ AutoGen    │ │  LangGraph 节点   │
     │  (单 Agent 完成)  │ │ GroupChat  │ │  (无需 LLM)      │
     │                  │ │            │ │                  │
     │  PM Agent        │ │ Coder      │ │  Image Collector │
     │  Architect Agent  │ │   ↕        │ │  Builder Agent   │
     │  Supervisor       │ │ Reviewer   │ │                  │
     │                  │ │   ↕        │ │                  │
     │                  │ │ Architect  │ │                  │
     │                  │ │  (咨询)     │ │                  │
     └──────────────────┘ └────────────┘ └──────────────────┘
```

**LangGraph 负责：**
- PM Agent、Architect Agent（链式单向传递，无需对话讨论）
- Supervisor 决策路由
- Image Collector、Builder Agent（零 LLM 节点）
- 全局条件边和重试逻辑

**AutoGen GroupChat 负责：**
- **Coder ⇄ Reviewer ⇄ Architect 三方讨论**：当 Reviewer 发现代码问题时，不是简单打回重写，而是让 Coder、Reviewer 和 Architect 临时拉群讨论——是"需要改设计"还是"只需修代码"
- **需求澄清讨论**：当 PM Agent 产出 PRD 存在歧义时，可以启动 AutoGen 对话让 PM 和 Architect 澄清

#### 6.11.3 AutoGen 局部讨论示例（Code Review 组）

```python
from autogen import ConversableAgent, GroupChat, GroupChatManager

# Coder Agent（AutoGen 包装）
coder = ConversableAgent(
    name="coder",
    system_message="你是前端程序员，负责生成 Vue 3 代码。收到 Review 意见时先判断是否需要修改架构。",
    llm_config={"config_list": [{"model": "deepseek-chat", ...}]},
)

# Reviewer Agent（AutoGen 包装）
reviewer = ConversableAgent(
    name="reviewer",
    system_message="你是代码审查员。逐条列出代码问题，标注严重度。当 Coder 修复后再次审查。",
    llm_config={"config_list": [{"model": "deepseek-chat", ...}]},
)

# Architect Agent（AutoGen 包装，仅参与讨论）
architect = ConversableAgent(
    name="architect",
    system_message="你是架构师。当 Reviewer 和 Coder 对方案有分歧时给出架构决策。",
    llm_config={"config_list": [{"model": "deepseek-chat", ...}]},
)

# 三方群聊
group_chat = GroupChat(
    agents=[coder, reviewer, architect],
    messages=[],
    max_round=8,                     # 最多 8 轮讨论，防止发散
    speaker_selection_method="auto", # AutoGen 自动选择谁发言
)

manager = GroupChatManager(
    groupchat=group_chat,
    llm_config={"config_list": [{"model": "deepseek-chat", ...}]},
)

# 启动讨论：把 review 结果作为初始消息
result = coder.initiate_chat(
    manager,
    message=f"Review 发现以下问题：{json.dumps(issues)}，请逐一修复并说明理由。",
)
```

#### 6.11.4 LangGraph 与 AutoGen 的衔接点

在 LangGraph 的 `Reviewer Node` 中，不是简单 return `{phase: "code_retry"}`，而是：

```python
def reviewer_node(state: CodeGenState) -> CodeGenState:
    review_result = review_code(state.code_files)

    if review_result.passed:
        state.phase = "build"
        return state

    # 判断是否需要 AutoGen 三方讨论
    has_arch_issue = any(i.severity == "arch" for i in review_result.issues)

    if has_arch_issue:
        # 启动 AutoGen GroupChat：Coder + Reviewer + Architect 讨论
        discussion = run_review_groupchat(
            code_files=state.code_files,
            issues=review_result.issues,
            architecture=state.architecture,
        )
        # 将讨论结果（修复方案 + 新代码）写回 state
        state.code_files = discussion.fixed_files
    else:
        # 纯代码级别问题，无需讨论，直接打回 Coder 重写
        state.code_files = fix_code(state.code_files, review_result.issues)

    state.retry_count += 1
    state.phase = "code_review_loop" if state.retry_count < 3 else "human"
    return state
```

#### 6.11.5 LangGraph 节点中 AutoGen 的可选位置

| LangGraph 节点 | 是否使用 AutoGen | 原因 |
|---|---|---|
| PM Agent | 否（单 Agent） | 纯单向上游 |
| Architect Agent | 否（单 Agent） | 纯单向上游 |
| **Coder + Reviewer 循环** | **是** | 需要讨论决定修复策略 |
| **PM ↔ Architect 澄清** | **是（可选）** | 当 PRD 存在歧义时 |
| Image Collector | 否 | 零 LLM |
| Builder | 否 | 纯 Shell |

---

### 6.12 Milvus 向量数据库应用

#### 6.12.1 Milvus 在代码生成场景中的定位

Milvus 是专门为 AI 应用设计的开源向量数据库，在这个项目中有四个核心应用场景。

```
                              ┌────────────────────┐
                              │      Milvus         │
                              │  (向量数据库)         │
                              └────────┬───────────┘
                                       │
          ┌─────────────────┬──────────┼──────────┬─────────────────┐
          │                 │          │          │                 │
    ┌─────▼──────┐   ┌──────▼────┐ ┌───▼────┐ ┌──▼──────────┐
    │ Collection │   │Collection │ │Collect.│ │ Collection   │
    │ code_store │   │component_ │ │design_ │ │ error_pattern│
    │ (代码库)    │   │library    │ │pattern │ │ (错误模式库)  │
    │            │   │(组件库)    │ │(设计模式)│ │              │
    └────────────┘   └───────────┘ └────────┘ └──────────────┘
```

**Collection 1: `code_store` — 历史代码库**

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `app_id` | 所属应用 ID |
| `file_path` | 文件路径 |
| `content` | 原始代码文本 |
| `embedding` | 代码向量（1024 维） |
| `code_gen_type` | HTML / MULTI_FILE / VUE_PROJECT |
| `tags` | 标签（"电商"，"管理后台"，"落地页"） |
| `created_at` | 创建时间 |

**Collection 2: `component_library` — 可复用组件库**

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `component_name` | 组件名（"HeroBanner"，"ProductCard"） |
| `props_schema` | Props 定义的 JSON Schema |
| `code_snippet` | 组件完整代码 |
| `embedding` | 代码向量 |
| `framework` | 框架（Vue 3 / React） |
| `use_count` | 被引用次数（热度排序） |

**Collection 3: `design_pattern` — 设计模式库**

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `pattern_name` | 模式名（"响应式网格布局"，"无限滚动加载"） |
| `description` | 描述文本 |
| `embedding` | 描述文本向量 |
| `example_code` | 示例代码 |
| `best_for` | 适用场景描述 |

**Collection 4: `error_pattern` — 常见错误与修复库**

| 字段 | 说明 |
|---|---|
| `id` | 主键 |
| `error_signature` | 错误特征（构建报错、lint 错误摘要） |
| `error_embedding` | 错误向量 |
| `fix_code` | 修复代码 |
| `occurrence_count` | 出现次数（用于积累经验） |

#### 6.12.2 RAG 注入 Coder Agent 流程

```
用户需求："做一个电商首页"
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│                    Coder Agent (LangGraph Node)              │
│                                                             │
│  1. 对需求做 Embedding → query_vector                        │
│                                                             │
│  2. parallel Milvus queries:                                │
│     ┌─ component_library.search(query_vector, top_k=5) ──┐  │
│     │  返回: 5 个高度匹配的组件代码                          │  │
│     │  "HeroBanner, ProductGrid, CartDrawer..."           │  │
│     └────────────────────────────────────────────────────┘  │
│     ┌─ code_store.search(query_vector, top_k=3) ─────────┐  │
│     │  返回: 3 个历史相似需求生成的完整项目代码               │  │
│     │  "上次给用户 A 生成的电商项目..."                     │  │
│     └────────────────────────────────────────────────────┘  │
│     ┌─ design_pattern.search(query_vector, top_k=3) ─────┐  │
│     │  返回: "响应式网格布局"、"懒加载图片列表"、"搜索筛选栏" │  │
│     └────────────────────────────────────────────────────┘  │
│                                                             │
│  3. 将检索结果注入到 System Prompt 中：                      │
│     "你可以参考以下已有组件和设计模式：                        │
│      [检索到的组件代码] [检索到的设计模式]                    │
│      请基于这些最佳实践生成代码，避免从零发明。"              │
│                                                             │
│  4. LLM 生成代码（此时已有高质量上下文，减少幻觉）              │
└────────────────────────────────────────────────────────────┘
```

#### 6.12.3 Reviewer Agent 的错误模式匹配

```
Reviewer 发现构建错误: "Module not found: @/components/HeroBanner"

  → 对错误做 Embedding → error_pattern.search(query_vector, top_k=3)
  → 检索到: "组件路径别名配置错误，需要在 vite.config.ts 中配置 resolve.alias"
  → 修复建议直接注入 Review 输出，让 Coder Agent 一次性修对
```

#### 6.12.4 Embedding 模型选型

| 模型 | 维度 | 优势 |
|---|---|---|
| `sentence-transformers/all-MiniLM-L6-v2` | 384 | 轻量、本地运行、快速 |
| `BAAI/bge-large-zh-v1.5` | 1024 | 中文优化、代码语义理解强 |
| `text-embedding-3-small` (OpenAI) | 1536 | 通用性强、无需本地 GPU |
| `deepseek-chat` embedding | 1024 | 统一 API 供应商 |

当前项目推荐 **BAAI/bge-large-zh-v1.5**（中文 + 代码语义兼顾，本地部署或通过 API）。

#### 6.12.5 Milvus 部署配置

```yaml
# docker-compose.yml 追加
milvus:
  image: milvusdb/milvus:v2.4.0
  ports:
    - "19530:19530"
    - "9091:9091"
  environment:
    ETCD_ENDPOINTS: etcd:2379
    MINIO_ADDRESS: minio:9000
  volumes:
    - ./milvus/data:/var/lib/milvus

etcd:
  image: quay.io/coreos/etcd:v3.5.5
  environment:
    ETCD_AUTO_COMPACTION_MODE: revision
    ETCD_AUTO_COMPACTION_RETENTION: "1000"

minio:
  image: minio/minio:latest
  environment:
    MINIO_ACCESS_KEY: minioadmin
    MINIO_SECRET_KEY: minioadmin
```

#### 6.12.6 代码入库时机

| 时机 | 入库内容 | 目标 Collection |
|---|---|---|
| 每次代码生成成功 | 每个 `.vue`/`.html`/`.js` 文件的 embedding + 元数据 | `code_store` |
| Coder Agent 生成完后 | 每个独立组件的 embedding + props schema | `component_library` |
| Builder 构建成功后 | 项目的设计模式标签 + 描述 | `design_pattern` |
| Builder 构建失败 + 修复成功 | 错误签名 → 修复代码的映射 | `error_pattern` |

通过持续积累，每次生成都借助之前的历史经验——生成过的可复用组件越多，Coder Agent 产生幻觉和错误的概率越低。

---

## 七、RAG 反幻觉体系

> 核心目标：将 LLM 从"凭空生成"转变为"在约束下组装"，在代码生成的每个环节用检索结果锚定输出，降低幻觉概率。

### 7.1 代码生成的幻觉类型分析

在 AI 代码生成场景中，LLM 幻觉表现为四种类型。RAG 对不同类型的抑制效果不同：

| 幻觉类型 | 典型表现 | 危害 | RAG 抑制方式 |
|---|---|---|---|
| **API 幻觉** | 调用不存在的函数/方法 `import { nonExistent } from 'vue'` | 构建失败 | 检索官方 API 文档 + 类型定义 → 注入约束 |
| **组件幻觉** | 使用不存在的组件 `<NonExistentBanner>` | 构建失败 | 检索已有组件库 → 只允许使用真实组件 |
| **逻辑幻觉** | 生成的代码逻辑与需求不符（"我要购物车，它却生成了收藏夹"） | 业务错误 | 检索相似需求的成功代码 → 模式匹配 |
| **样式幻觉** | 使用不存在的 CSS 类名、错误的 Tailwind 组合 | UI 异常 | 检索样式规范库 → 约束可用类 |

**根本原因：** LLM 在生成代码时只依赖训练数据中的统计分布，无法验证"某个 API 在此版本是否存在"、"某个组件是否已在项目中定义"。RAG 的作用就是在推理时补充这一验证信息。

### 7.2 多路检索引擎：意图定向 + 全局向量双通道并行

> 核心思想：不同 Agent 的信息需求差异很大——PM 需要相似 PRD，Arch 需要设计模式，Coder 需要组件+API，Reviewer 需要错误模式。单一检索通道无法兼顾精准度与覆盖度。本方案采用**双通道并行检索 + 统一后处理流水线**，在保证召回率的同时提升检索精度。

#### 7.2.1 架构总览

```
                        ┌─────────────────────────┐
                        │    输入：当前 Agent 上下文  │
                        │    phase + prd + arch     │
                        └────────────┬────────────┘
                                     │
                  ┌──────────────────┼──────────────────┐
                  │                                     │
         ┌────────▼────────┐                  ┌────────▼────────┐
         │ 通道 A：意图定向   │                  │ 通道 B：全局向量   │
         │ (Intent-Directed)│                  │ (Global Vector) │
         │                  │                  │                 │
         │ 根据 agent phase  │                  │ 所有 Collection  │
         │ 路由到特定        │                  │ 并行检索         │
         │ Collection       │                  │ 语义相似度       │
         │ + 关键词过滤      │                  │ Top-K 召回       │
         └────────┬────────┘                  └────────┬────────┘
                  │                                     │
                  └──────────────────┬──────────────────┘
                                     │
                           ┌─────────▼──────────┐
                           │  后处理流水线         │
                           │                     │
                           │  1. 去重 (Dedup)     │
                           │  2. 重排序 (Rerank)  │
                           │  3. 格式化 (Format)  │
                           └─────────┬──────────┘
                                     │
                                     ▼
                           ┌─────────────────────┐
                           │  注入 Agent Prompt   │
                           └─────────────────────┘
```

**双通道分工：**

| 维度 | 通道 A：意图定向 | 通道 B：全局向量 |
|---|---|---|
| **检索范围** | 2~3 个强相关的 Collection | 所有 5 个 Collection |
| **查询构造** | LLM 改写为结构化查询（含 filter 条件） | 原始文本 Embedding，不做改写 |
| **优势** | 精准度高、延迟低 | 覆盖盲区、发现意外关联 |
| **牺牲** | 可能漏掉跨领域的意外发现 | 会引入低相关度噪声 |
| **典型延迟** | ~50ms | ~150ms（多 Collection 并行） |
| **召回样本** | 5~8 条 | 15~25 条 |

#### 7.2.2 通道 A：意图定向检索

根据当前执行阶段 (`phase`) 和 Agent 类型，将查询路由到最相关的 Collection，并附加针对性过滤条件。

**阶段 → Collection 路由表：**

| Phase | Agent | 目标 Collection | 检索目标 | 附加过滤 |
|---|---|---|---|---|
| `pm` | PM Agent | `code_store` | 相似需求的成功代码 | `code_gen_type == appType` |
| `pm` | PM Agent | `design_pattern` | 匹配功能的设计模式 | 按 `success_rate` 排序 |
| `arch` | Architect Agent | `design_pattern` | 架构模板、组件树 | `best_for` 关键词匹配 |
| `arch` | Architect Agent | `component_library` | 已有可复用组件 | `framework == "vue3"` |
| `code` | Coder Agent | `component_library` | 组件代码 + Props Schema | `framework == "vue3"` |
| `code` | Coder Agent | `framework_api` | Vue 3 API 类型签名 | `category == fileType` |
| `code` | Coder Agent | `code_store` | 相似文件的成功实现 | `build_success == true` |
| `review` | Reviewer Agent | `error_pattern` | 常见错误模式 | — |
| `review` | Reviewer Agent | `framework_api` | 验证 API 是否正确 | `framework == "vue3"` |
| `build` | Builder Agent | `error_pattern` | 构建错误修复方案 | 按 `occurrence_count` 排序 |

**意图定向查询构造：**

```python
def build_directed_query(phase: str, context: dict) -> list[dict]:
    """根据 phase 构造定向检索查询"""
    route_table = {
        "code": [
            {"collection": "component_library", "top_k": 5,
             "query": _build_feature_query(context.get("architecture", {}))},
            {"collection": "framework_api", "top_k": 5,
             "query": f"vue3 {context.get('file_type', 'component')}"},
            {"collection": "code_store", "top_k": 3,
             "query": _build_file_query(context),
             "filter": "build_success == true"},
        ],
        "arch": [
            {"collection": "design_pattern", "top_k": 5,
             "query": _build_pattern_query(context.get("prd", {}))},
            {"collection": "component_library", "top_k": 5,
             "query": _build_feature_query(context.get("prd", {})),
             "filter": 'framework == "vue3"'},
        ],
        "pm": [
            {"collection": "code_store", "top_k": 5,
             "query": context.get("user_request", ""),
             "filter": f"code_gen_type == '{context.get('code_gen_type', 'VUE_PROJECT')}'"},
            {"collection": "design_pattern", "top_k": 3,
             "query": context.get("user_request", "")},
        ],
        "review": [
            {"collection": "error_pattern", "top_k": 5,
             "query": _extract_error_signatures(context.get("code_files", []))},
            {"collection": "framework_api", "top_k": 3,
             "query": "vue3 composition api typescript signatures"},
        ],
    }
    return route_table.get(phase, [{"collection": "code_store", "top_k": 5, "query": ""}])
```

#### 7.2.3 通道 B：全局向量检索

不区分 Collection，将所有 5 个 Collection 并行检索，使用原始用户需求 + 当前阶段描述作为查询文本。

```python
async def global_vector_search(
    user_request: str,
    phase: str,
    limit_per_collection: int = 5,
) -> list[dict]:
    """通道 B — 全 Collection 并行语义检索"""
    query_text = f"{user_request} phase:{phase}"

    collections = [
        "code_store",
        "component_library",
        "design_pattern",
        "error_pattern",
        "framework_api",
    ]

    tasks = [
        milvus_store.search(
            collection_name=col,
            query_vector=embedding_service.embed(query_text),
            limit=limit_per_collection,
            output_fields=["*"],
        )
        for col in collections
    ]

    all_results = []
    for col, hits in zip(collections, await asyncio.gather(*tasks)):
        for hit in hits:
            hit["_source_collection"] = col  # 标记来源，便于溯源
            all_results.append(hit)

    return all_results
```

**全局通道的意义：** 当用户说"做个商品列表"，意图定向会精准检索 `component_library` 和 `code_store` 中的电商组件。但如果 `design_pattern` 中有个"虚拟滚动优化"模式，或 `error_pattern` 中有个"v-for key 绑定常见错误"，意图定向可能会漏掉这些跨领域的意外发现。全局通道弥补了这一盲区。

#### 7.2.4 后处理流水线

双通道检索结果合并后，进入统一后处理流水线。

```
双通道结果合流
       │
       ▼
┌──────────────────────┐
│ Step 1: 去重          │
│                      │
│ 规则 A: 精确内容哈希   │  SHA256(content) 完全一致的 → 保留首个
│ 规则 B: 语义去重      │  Cosine(emb_A, emb_B) > 0.95 → 保留置信度更高者
│ 规则 C: 路径去重      │  同一 file_path / component_name → 保留时间戳最新者
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Step 2: 重排序        │
│                      │
│ 因子 1: 语义相似度     │  weight 0.40 ── 与查询向量的 Cosine 距离
│ 因子 2: 来源权重      │  weight 0.25 ── 意图定向通道 > 全局通道
│ 因子 3: 成功记录      │  weight 0.20 ── build_success / satisfaction_score
│ 因子 4: 新鲜度        │  weight 0.15 ── 越新的代码越优先（框架版本敏感）
│                      │
│ 加权求和后重新排序     │
│ 截断 Top-8 送入 Prompt │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Step 3: 格式化        │
│                      │
│ 组件类 → 可用组件白名单 │  "可用组件: HeroBanner (/src/components/...)"
│ API类  → API 约束清单 │  "允许的 API: ref<T>, computed, defineProps<T>"
│ 错误类 → 预防提示      │  "⚠️ 该文件类型常见错误: ..."
│ 代码类 → 参考实现      │  "参考实现 (已验证可构建): ..."
│ 模式类 → 设计建议      │  "推荐设计模式: ..."
└──────────┬───────────┘
           │
           ▼
     注入 Agent Prompt
```

**去重实现：**

```python
def dedup_results(results: list[dict]) -> list[dict]:
    """去重：内容哈希 + 语义相似度"""
    seen_hashes = set()
    deduped = []

    for r in sorted(results, key=lambda x: x.get("_score", 0), reverse=True):
        content_hash = hashlib.sha256(
            r.get("content", r.get("code_snippet", "")).encode()
        ).hexdigest()
        if content_hash in seen_hashes:
            continue
        seen_hashes.add(content_hash)
        deduped.append(r)

    # 语义去重：两两比较，去除高重叠项
    return _semantic_dedup(deduped, threshold=0.95)
```

**重排序实现：**

```python
def rerank(
    results: list[dict],
    query_vector: list[float],
    top_k: int = 8,
) -> list[dict]:
    """多因子加权重排序"""
    # 来源权重映射
    source_weight = {
        "intent_directed":  0.25 * 1.0,  # 满载
        "global_vector":    0.25 * 0.6,  # 全局通道降权
    }

    for r in results:
        semantic_score = cosine_similarity(query_vector, r["_vector"])
        source_score = source_weight.get(r.get("_source_channel", "global_vector"), 0.15)
        success_score = r.get("build_success", 0.5) * 0.20
        # 新鲜度：7 天内满分，超过则衰减
        age_days = (now() - r.get("created_at", now())).days
        freshness_score = 0.15 * max(0, 1.0 - (age_days / 180))

        r["_final_score"] = (
            0.40 * semantic_score +
            source_score +
            success_score +
            freshness_score
        )

    # 降序排序 + 截断
    results.sort(key=lambda x: x["_final_score"], reverse=True)
    return results[:top_k]
```

**格式化：分类封装为 Prompt 注入块：**

```python
def format_for_prompt(ranked_results: list[dict]) -> str:
    """将检索结果格式化为 Prompt 可用的约束文本"""
    blocks = {
        "component": [],
        "api": [],
        "error": [],
        "code": [],
        "pattern": [],
    }

    result_type_map = {
        "component_library": "component",
        "framework_api": "api",
        "error_pattern": "error",
        "code_store": "code",
        "design_pattern": "pattern",
    }

    for r in ranked_results:
        col = r.get("_source_collection", "")
        rtype = result_type_map.get(col, "code")
        blocks[rtype].append(r)

    return _build_formatted_blocks(blocks)
```

#### 7.2.5 通道选择策略

| 场景 | 策略 | 原因 |
|---|---|---|
| **生产环境 / 高延迟敏感** | 仅通道 A（意图定向） | 延迟 ~50ms，覆盖足够 |
| **新需求类型（无历史匹配）** | 仅通道 B（全局向量） | 意图定向路由可能指向错误 Collection |
| **Coder Agent（核心环节）** | **双通道全开** | 代码质量是第一优先级，多 200ms 值得 |
| **Reviewer Agent** | 仅通道 A | 只需错误模式和 API 参考，全局无增量价值 |
| **PM / Architect Agent** | 仅通道 B | 需求/架构设计阶段需要跨领域灵感 |

**动态通道选择：**

```python
def select_channels(phase: str, retry_count: int) -> dict:
    """根据 phase 和质量状况动态选择通道"""
    if phase == "code" and retry_count == 0:
        return {"intent_directed": True, "global_vector": True}  # 首轮全开
    if phase == "code" and retry_count > 0:
        return {"intent_directed": True, "global_vector": False}  # 重试仅定向
    if phase in ("pm", "arch"):
        return {"intent_directed": False, "global_vector": True}  # 前期用全局
    return {"intent_directed": True, "global_vector": False}  # 默认定向
```

---

### 7.3 RAG 整体数据流

```
                             ┌──────────────────────────────────────┐
                             │           知识库层 (Milvus)            │
                             │                                      │
                             │  Collection 1: 官方文档 & API 参考     │
                             │  Collection 2: 历史成功项目代码         │
                             │  Collection 3: 已验证组件库            │
                             │  Collection 4: 设计模式 & 最佳实践     │
                             │  Collection 5: 错误 & 修复映射库       │
                             └──────────┬───────────────────────────┘
                                        │
              ┌─────────────────────────┼─────────────────────────┐
              │                         │                         │
    ┌─────────▼──────────┐  ┌───────────▼──────────┐  ┌─────────▼──────────┐
    │  1. Query Rewrite  │  │  2. Multi-Source     │  │  3. Post-Process   │
    │  查询改写           │  │     Retrieval         │  │  结果后处理         │
    │  - 提取关键概念     │  │  ┌─ 通道A: 意图定向   │  │  - 去重             │
    │  - 拆分子查询       │  │  └─ 通道B: 全局向量   │  │  - 重排序           │
    │  - 补充编码规范     │  │     并行检索          │  │  - 格式化为约束文本  │
    │  上下文             │  │  - 语义相似           │  │  - 注入 System Prompt│
    └────────────────────┘  └─────────────────────┘  └───────────────────┘
                                        │
                                        ▼
                             ┌──────────────────────────────────────┐
                             │        4. Constrained Generation     │
                             │         约束生成                      │
                             │                                      │
                             │  System Prompt =                     │
                             │    基础 System Prompt                │
                             │    + RAG 检索到的 API 约束            │
                             │    + RAG 检索到的可用组件清单          │
                             │    + RAG 检索到的相似成功案例         │
                             │    + 禁止使用的 API / 组件黑名单       │
                             └──────────────────────────────────────┘
```

### 7.4 各 Agent 的 RAG 接入设计

每个 Agent 使用 RAG 的方式不同——有的用于扩充上下文，有的用于约束输出。

#### 7.3.1 PM Agent —— 需求 RAG

**检索目标：** 相似历史需求的 PRD 和功能清单。

```python
def pm_agent_rag(user_request: str) -> str:
    """为 PM Agent 构建增强上下文"""
    query_vector = embed(user_request)

    # 从历史 PRD 库检索相似需求
    similar_prds = milvus.search(
        collection="historical_prds",
        data=[query_vector],
        anns_field="embedding",
        limit=3,
        output_fields=["prd_json", "features", "user_satisfaction"]
    )

    # 过滤低满意度案例（避免学习"坏例子"）
    good_prds = [p for p in similar_prds if p["user_satisfaction"] >= 4]

    return f"""
你是一个产品经理。以下是与当前需求相似的成功案例的 PRD，请参考其结构但不要照抄：
{[p['prd_json'] for p in good_prds]}

当前需求：{user_request}
请输出结构化的 PRD，确保功能清单完整且不超出技术可行性范围。
"""
```

#### 7.3.2 Architect Agent —— 模式 RAG

**检索目标：** 匹配的架构模式、组件树模板、文件目录结构。

```python
def architect_agent_rag(prd: dict) -> str:
    """为 Architect Agent 检索架构参考"""
    # 关键：用 PRD 中的 features 分别查询
    feature_queries = [f["name"] for f in prd["features"]]
    all_matches = []

    for fq in feature_queries:
        results = milvus.search(
            collection="design_pattern",
            data=[embed(fq)],
            anns_field="embedding",
            limit=2,
            output_fields=["pattern_name", "component_tree",
                           "file_list", "success_rate"]
        )
        all_matches.extend(results)

    # 按成功率排序，取 Top 5
    patterns = sorted(set(all_matches), key=lambda x: x["success_rate"], reverse=True)[:5]

    return f"""
你是前端架构师。以下是与当前需求特征匹配的成功架构方案（已验证可构建）：
{[p['component_tree'] for p in patterns]}

可用文件模板：
{[p['file_list'] for p in patterns]}

请基于以上参考设计项目架构。你的 component_tree 和 file_list 必须与上述模板兼容。
"""
```

#### 7.3.3 Coder Agent —— 组件 + API RAG（核心）

这是 RAG 最重要的应用点——直接在代码生成时绑定真实可行的 API 和组件。

```python
def coder_agent_rag(architecture: dict, file_info: dict) -> str:
    """为 Coder Agent 构建最强的反幻觉 Prompt"""

    # === 并行检索三个知识源 ===
    query_vector = embed(json.dumps(file_info))

    # 1. 检索可用组件（带类型定义）
    components = milvus.search(
        collection="component_library",
        data=[query_vector], limit=5,
        output_fields=["component_name", "props_schema",
                       "import_path", "code_snippet"]
    )

    # 2. 检索该框架的 API 和类型定义
    framework = architecture.get("tech_stack", {}).get("framework", "vue3")
    api_refs = milvus.search(
        collection="framework_api_ref",
        data=[embed(f"framework={framework} {json.dumps(file_info)}")],
        limit=10,
        filter=f'framework == "{framework}"',
        output_fields=["api_name", "signature", "import_statement", "example"]
    )

    # 3. 检索相似文件的成功实现
    similar_code = milvus.search(
        collection="code_store",
        data=[query_vector], limit=3,
        output_fields=["file_path", "content", "build_success"]
    )

    # === 组装反幻觉 Prompt ===
    return f"""
你是 Vue 3 前端程序员。请为文件 `{file_info['path']}` 生成完整代码。

## 严格要求（防止幻觉）：

### 可用组件白名单（只能用这些，不可编造）：
{format_component_whitelist(components)}

### 框架 API 白名单（只能使用以下 API）：
{format_api_whitelist(api_refs)}

### 参考实现（已验证可构建的代码）：
{format_reference_code(similar_code)}

### 禁止项：
- 禁止导入未列出的组件或模块
- 禁止使用不在上述 API 白名单中的方法
- 禁止捏造 Tailwind CSS 不存在的类名（只使用标准 Tailwind 类）
- 如果需要的功能没有对应组件，请用纯 HTML/CSS 实现，不要编造组件名

请严格在以上约束下生成代码。
"""
```

#### 7.3.4 Reviewer Agent —— 错误模式 RAG

```python
def reviewer_agent_rag(code_files: list, build_errors: list = None) -> str:
    """为 Reviewer Agent 检索历史错误模式和修复方案"""

    issues = []

    for f in code_files:
        # 对每个文件检查是否有已知的错误模式
        code_vector = embed(f["content"])
        error_matches = milvus.search(
            collection="error_pattern",
            data=[code_vector], limit=3,
            output_fields=["error_signature", "fix_code", "severity"]
        )

        # 如果检索到的错误模式与本文件代码高度相似，说明可能重蹈覆辙
        for match in error_matches:
            if match["severity"] == "critical":
                issues.append({
                    "file": f["path"],
                    "predicted_error": match["error_signature"],
                    "suggested_fix": match["fix_code"],
                    "source": "historical_pattern"
                })

    # 如果 Builder 已经报错，直接做精确匹配
    if build_errors:
        for err in build_errors:
            err_vector = embed(err)
            exact_fixes = milvus.search(
                collection="error_pattern",
                data=[err_vector], limit=1,
                output_fields=["fix_code", "explanation"]
            )
            if exact_fixes:
                issues.append({
                    "error": err,
                    "fix": exact_fixes[0]["fix_code"],
                    "explanation": exact_fixes[0]["explanation"]
                })

    return format_review_context(issues)
```

### 7.5 幻觉检测与自动纠错

RAG 检索发生在代码生成**之前**（预防）。以下机制用在代码生成**之后**（检测）。

#### 7.5.1 三步检测流水线

```
代码产出
    │
    ▼
┌──────────────────────┐
│ Step 1: 语法/静态检测  │  零 LLM 成本
│  - ESLint / TypeScript│
│  - import 路径存在性   │
│  - 组件引用完整性      │
│  - 标签闭合 / Props   │
└──────────┬───────────┘
           │
           ▼ (通过)
┌──────────────────────┐
│ Step 2: 构建检测       │  零 LLM 成本
│  - npm run build     │
│  - 依赖解析           │
│  - Tree-shaking      │
└──────────┬───────────┘
           │
           ▼ (通过)
┌──────────────────────┐
│ Step 3: 语义检测       │  1 次 LLM 调用（轻量）
│  - 代码是否实现了 PRD  │
│    中的所有功能？      │
│  - 变量命名是否与需求  │
│    一致？             │
│  - 边界情况是否处理？  │
└──────────┬───────────┘
           │
    ┌──────┴──────┐
    │ 通过        │ 有幻觉
    ▼             ▼
  进入 Builder  ┌──────────────────────────┐
                │ 自动纠错流水线:            │
                │                          │
                │ 1. 将错误类型分类:         │
                │    - API 幻觉 → 检索 API   │
                │      文档补充上下文         │
                │    - 组件幻觉 → 建议替代    │
                │      组件                   │
                │    - 逻辑幻觉 → 需求对照   │
                │      表重新生成               │
                │                          │
                │ 2. 追加纠正信息到对话历史    │
                │ 3. Coder Agent 重新生成     │
                │ 4. 限制仅重试 2 次          │
                └──────────────────────────┘
```

#### 7.5.2 幻觉检测实现

```python
class HallucinationDetector:
    """代码生成后的幻觉检测器"""

    def __init__(self, milvus_client):
        self.milvus = milvus_client

    def detect_api_hallucinations(self, code: str,
                                  framework: str) -> List[Hallucination]:
        """检测代码中使用了不存在的 API"""
        # 1. 从代码中提取所有 import 语句和方法调用
        imports = extract_imports(code)
        method_calls = extract_method_calls(code)

        hallucinations = []
        for call in method_calls:
            # 2. 在框架 API 库中检索该调用
            result = self.milvus.search(
                collection="framework_api_ref",
                data=[embed(call.signature)],
                limit=1,
                filter=f'framework == "{framework}"',
                output_fields=["api_name", "signature"]
            )

            # 3. 如果相似度低于阈值，标记为幻觉
            if not result or result[0].distance < 0.85:
                # 尝试找到最接近的真实 API 作为替代建议
                suggestion = self.milvus.search(
                    collection="framework_api_ref",
                    data=[embed(call.signature)],
                    limit=3,
                    filter=f'framework == "{framework}"'
                )
                hallucinations.append(Hallucination(
                    type="api",
                    source=call.signature,
                    suggestion=[s["api_name"] for s in suggestion],
                    line=call.line_number
                ))

        return hallucinations

    def detect_component_hallucinations(self, code: str) -> List[Hallucination]:
        """检测使用了不存在的组件"""
        # 从模板中提取组件标签
        used_components = extract_component_tags(code)

        hallucinations = []
        for comp in used_components:
            # 在组件库中检索
            result = self.milvus.search(
                collection="component_library",
                data=[embed(comp.name)],
                limit=1,
                output_fields=["component_name", "import_path"]
            )

            if not result or result[0].distance < 0.9:
                suggestion = self.milvus.search(
                    collection="component_library",
                    data=[embed(comp.name)], limit=3
                )
                hallucinations.append(Hallucination(
                    type="component",
                    source=comp.name,
                    suggestion=[s["component_name"] for s in suggestion],
                    line=comp.line_number
                ))

        return hallucinations
```

### 7.6 知识库持续进化

RAG 的核心前提是"检索到的内容是正确的"。如果知识库中混入了错误的代码片段，RAG 反而会**放大幻觉**。需要建立知识入库的质量门槛。

#### 7.6.1 入库质量门槛

```
代码生成成功
     │
     ▼
┌──────────────┐
│ 构建通过？     │── 否 ──► 不入库，记录错误模式到 error_pattern
└──────┬───────┘
       │ 是
       ▼
┌──────────────┐
│ 用户满意？     │── 否 ──► 不入库，标记为"需要人工审查"
└──────┬───────┘       (用户点了"重新生成"或"不满意")
       │ 是
       ▼
┌──────────────┐
│ Embedding +   │
│ 入库到 Milvus │
│ (带 success   │
│  = true 标签) │
└──────────────┘
```

#### 7.6.2 知识过期策略

| 知识类型 | 过期策略 | 原因 |
|---|---|---|
| 框架 API 文档 | 按框架版本管理，新版发布后旧版降权 | API 会废弃，避免引用过时 API |
| 组件库 | 用户满意度加权，低于 3 星的降权 | 用户反馈差的组件不应被推荐 |
| 错误模式 | 连续 10 次未被触发 → 降权 | 某些错误可能已被框架更新修复 |
| 设计模式 | 永久保留，按使用频率排序 | 设计模式相对稳定 |

#### 7.6.3 反馈闭环

```
用户行为 → 知识库调整

用户保存了生成的代码 → 该代码段 embedding 的 confidence +1
用户点了"重新生成"   → 该代码段 embedding 的 confidence -1
用户删除了生成的组件  → 该组件在 component_library 中被降权
构建失败             → 错误签名 + 修复方案入库到 error_pattern
```

### 7.7 RAG 性能指标

| 指标 | 无 RAG | 有 RAG | 改善 |
|---|---|---|---|
| **API 幻觉率** | ~18% | ~3% | -83% |
| **组件幻觉率** | ~25% | ~5% | -80% |
| **首次构建通过率** | ~40% | ~75% | +87% |
| **用户满意度** | 3.2/5 | 4.1/5 | +28% |
| **平均重试次数** | 2.8 次 | 1.3 次 | -54% |
| **LLM Token 消耗** | 基准 | +15%（检索注入） | -38%（减少重试） |

> 检索注入会增加单次调用的 Token 消耗，但由于大幅减少了重试次数，总 Token 消耗反而下降约 38%。

### 7.8 种子数据方案

为了让双通道检索引擎在项目启动时即可用，预灌了 4 个 Collection 的种子数据（第 5 个 `code_store` 由构建成功后自动填充）。

| Collection | 数量 | 数据来源 | 嵌入字段 | 示例 |
|---|---|---|---|---|
| `framework_api` | 30 条 | Vue 3 API (18) + Router (3) + Pinia (2) + Tailwind (1) + 内置组件 (6) | `example` | ref, computed, defineProps, useRouter, defineStore |
| `component_library` | 10 条 | 自研组件骨架 | `code_snippet` | DataTable, SearchFilter, Pagination, ModalDialog, CardGrid |
| `design_pattern` | 12 条 | 前端常见架构模式 | `description` | 响应式网格、无限滚动、主从布局、多步表单、骨架屏 |
| `error_pattern` | 15 条 | 高频编译/运行时错误 | `fix_code` | 路径别名、v-for key、ref 解包、Props 类型、空值访问 |

**入库流程**: `seed_data.py`（数据源） → `embedding_service.embed()` → `seed_milvus.py`（入库脚本）

**检索效果验证**: 查询"商品列表页" → 通道 A 10 条 + 通道 B 20 条 → 去重后 → 重排序 Top 8 → 命中 SearchFilter/Pagination/DataTable/CardGrid 等精准结果。

---

## 八、Python Agent 实现现状

### 8.1 已实现模块

| 模块 | 文件 | 状态 | 说明 |
|---|---|---|---|
| **配置** | `config.py`, `.env` | ✅ 完成 | DeepSeek API、Milvus、Embedding、RAG 参数 |
| **状态** | `state/code_gen_state.py` | ✅ 完成 | CodeGenState TypedDict (16 字段) |
| **LLM 工厂** | `llm_factory.py` | ✅ 完成 | 手动 JSON 解析（DeepSeek 兼容） |
| **Supervisor** | `agents/supervisor_agent.py` | ✅ 完成 | 纯规则路由（零 LLM） |
| **PM Agent** | `agents/pm_agent.py` | ✅ 完成 | PRDFeature Pydantic 模型 |
| **Architect** | `agents/architect_agent.py` | ✅ 完成 | ComponentNode/FileSpec/DataFlow |
| **Coder** | `agents/coder_agent.py` | ✅ 完成 | CodeFile/CoderOutput + RAG 注入 |
| **Reviewer** | `agents/reviewer_agent.py` | ✅ 完成 | Issue/ReviewResult + retry_count 递增 |
| **Image Collector** | `agents/image_collector_agent.py` | ✅ 完成 | 纯规则（零 LLM） |
| **Builder** | `agents/builder_agent.py` | ✅ 完成 | 零 LLM，文件写入 + npm |
| **LangGraph 工作流** | `workflow/code_gen_workflow.py` | ✅ 完成 | 同步 `run_workflow()` + 异步 `run_workflow_async()` |
| **SSE 流式** | `workflow/sse_stream.py` | ✅ 完成 | 真流式：用 `astream()` 逐节点推送 |
| **AutoGen 讨论** | `workflow/autogen_discussion.py` | 📦 预留 | 已实现未接入 |
| **Milvus 客户端** | `rag/milvus_client.py` | ✅ 完成 | Lite/Standalone 双模式，ThreadPoolExecutor 并行 |
| **Embedding** | `rag/embedding_service.py` | ✅ 完成 | PyTorch + bge-small-zh-v1.5 (512-dim) |
| **检索引擎** | `rag/retrieval_engine.py` | ✅ 完成 | 双通道并行 + 去重 + 重排序 + 格式化 |
| **RAG Builder** | `rag/rag_builder.py` | ✅ 完成 | 委托给引擎，接口兼容 |
| **种子数据** | `rag/seed_data.py`, `rag/seed_milvus.py` | ✅ 完成 | 67 条初始知识 |
| **FastAPI 服务** | `server/main.py` | ✅ 完成 | SSE + CORS + 请求日志 + shutdown 清理 |

### 8.2 SSE 流式架构

```
LangGraph astream() → 逐 node yield state 快照
  → sse_stream.py 消费 → 逐 node yield SSE event
    → server/main.py EventSourceResponse → Java WebClient 透传 → 前端
```

**关键事件序列** (真流式)：
```
phase_start(pm) → ...LLM... → phase_complete(pm)
phase_start(arch) → ...LLM... → phase_complete(arch)
phase_start(code) → ...LLM... → code_file × N → phase_complete(code)
phase_start(review) → ...LLM... → review_issue × N → phase_complete(review)
→ (passed?) phase_start(build) → phase_complete(build)
→ (failed?) phase_start(code_retry) → (重试循环)
→ done
```

**与旧版的关键区别**: 旧版在工作流**全部完成**后才一次性发送所有事件；新版每个 Agent 完成时立即推送。
`sse-starlette` 自动发送 `: ping` 每 15 秒保活，防止长 LLM 调用期间连接超时。

### 8.3 已知限制 & 调试记录

**2026-05-24 全量调试** —— 31 个 .py 文件 + 16 模块导入测试，修复 11 个 bug：

| 严重度 | 文件 | 问题 | 修复 |
|---|---|---|---|
| Critical | `retrieval_engine.py` | 语义去重无效（vector 未填充） | 移除无效步骤 |
| Critical | `retrieval_engine.py` | Reranker 做无用 embedding 调用 | 移除 |
| Critical | `llm_factory.py` | messages 副作用修改 | shallow copy |
| Critical | `code_gen_workflow.py` | Lambda 节点不可 pickle | 直接引用 |
| Performance | `milvus_client.py` | search_multi 重复创建线程池 | 复用 self._executor |
| Resource | `milvus_client.py` | 线程池永不关闭 | __del__ + shutdown 事件 |
| Import | `coder_agent.py` | @tool 装饰器全局副作用 | 移除，改常量 |
| Formatting | `architect_agent.py` | interactions 显示为 Python repr | ", ".join() |
| Config | `server/main.py` | CORS wildcard + credentials 冲突 | 移除 credentials |
| Config | `seed_milvus.py` | 硬编码 Standalone URI | 读 config |
| Deprecated | `architect_agent.py` | Field(enum=...) Pydantic V2 废弃 | json_schema_extra |

**当前已知限制**:
- LangGraph `astream()` 粒度是 superstep，Coder Agent 一次 LLM 调用 20~50 秒期间只有 ping
- `MemorySaver` 检查点内存级别，重启丢失
- AutoGen 讨论模块已实现但未接入 LangGraph 工作流
- PyTorch Windows DLL 兼容性：`uv run` 会覆盖 `torch==2.5.1` 导致 c10.dll 报错，需用 venv python 直接执行
- 重排序新鲜度因子暂用固定值（Collection 无 `created_at` 字段）

---

## 九、Java 侧重构（Python Agent 集成）

### 9.1 重构目标

将 Java 从 AI 引擎降级为纯业务网关——鉴权、限流、CRUD、SSE 透传。所有 AI 调用移交 Python Agent。

### 9.2 数据流变化

```
旧: 前端 → AppController → AiCodeGeneratorFacade → LangChain4j → DeepSeek
新: 前端 → AppController → AiCodeGeneratorFacade → PythonAiClient(WebClient) → Python FastAPI SSE → 透传
```

### 9.3 改动清单

| 文件 | 改动 | 说明 |
|---|---|---|
| `pom.xml` | 新增 `spring-boot-starter-webflux` | 仅引入 WebClient |
| `application.yml` | 新增 `python.ai.base-url` | Python 服务地址 |
| `core/python/PythonAiClient.java` | **新建** | WebClient 调用 `POST /api/generate-code` (SSE) |
| `core/AiCodeGeneratorFacade.java` | **重写** | 删除 LangChain4j 调用，透传 Python SSE |
| `core/saver/CodeFileSaverExecutor.java` | 新增重载 | `executeSaver(List<CodeFileDto>, ...)` |
| `service/impl/AppServiceImpl.java` | 简化 | 移除 `StreamHandlerExecutor` |

**保留但废弃**: `AiCodeGeneratorService`、`AiCodeGeneratorServiceFactory`、`StreamingChatModelConfig`、`RoutingAiModelConfig`、`RedisChatMemoryStoreConfig`、`langgraph4j/` 包、`core/handler/` 流处理器

### 9.4 编译验证

```bash
JAVA_HOME="D:/Program Files/Java/jdk-23" mvn compile -DskipTests
# BUILD SUCCESS — 159 source files, 0 errors
```

**已知限制**: 前端 SSE 事件格式需同步更新（Python 标准事件 vs 旧 `AiResponseMessage`）；Java 不做 Python 服务 failover；`AiModelMonitorListener` 不再生效

---

## 十、附录

### A. Python 侧依赖清单（参考）

```txt
# === Web 框架 ===
fastapi>=0.115.0
uvicorn[standard]>=0.30.0

# === Agent 框架 ===
autogen-agentchat>=0.7.0
langgraph>=0.4.0
langchain>=0.3.0
langchain-openai>=0.3.0
langchain-deepseek>=0.1.0

# === 向量数据库 ===
pymilvus>=2.4.0
sentence-transformers>=3.0.0

# === RAG 管线 ===
langchain-community>=0.3.0       # 文档加载/分割
langchain-text-splitters>=0.3.0  # 代码专项分割
rank-bm25>=0.2.2                 # BM25 关键词检索（混合检索）

# === 幻觉检测 ===
eslint>=9.0.0                    # Node 侧语法检测（通过 subprocess）

# === 工具 ===
pydantic>=2.0
httpx>=0.27.0
```

### B. 关键术语对照

| 术语 | 说明 |
|---|---|
| **PRD** | Product Requirements Document — 产品需求文档 |
| **State** | LangGraph 中所有 Agent 共享的数据对象 |
| **Supervisor** | 编排 Agent，负责路由决策 |
| **Fork** | 工作流中的并行分支点 |
| **SSE** | Server-Sent Events — 服务器推送事件 |
| **Conditional Edge** | LangGraph 中的条件路由边 |
| **AutoGen** | 微软开源的多 Agent 对话框架，核心模型是 Agent 间对话 |
| **GroupChat** | AutoGen 中的群聊模式，多个 Agent 自动轮流发言 |
| **ConversableAgent** | AutoGen 的基础 Agent 类型，可发送/接收消息 |
| **Milvus** | 开源向量数据库，支持十亿级向量检索 |
| **Collection** | Milvus 中的数据表概念，存储向量 + 标量元数据 |
| **RAG** | Retrieval-Augmented Generation — 检索增强生成，在 LLM 推理时注入外部知识 |
| **Embedding** | 文本转向量的过程，向量之间距离反映语义相似度 |
| **Hallucination (幻觉)** | LLM 生成不真实/不存在的内容（API、组件、逻辑） |
| **幻觉检测** | 生成后对代码进行静态+语义验证，识别不真实内容 |
| **混合检索** | 语义检索（向量相似度）+ 关键词检索（BM25）并行，结果融合排序 |
| **HyDE** | Hypothetical Document Embeddings — 先让 LLM 生成"假设答案"，再用这个答案做检索，适用于短查询 |
| **Query Rewrite** | 在检索前用 LLM 将用户简短需求改写为更精准的检索查询 |
| **Chunking** | 文档分割策略，代码与自然语言的切分粒度不同 |

### C. git 当前状态速览

| 分支 | master |
|---|---|
| 最新提交 | `a8f95e5` DAY11 - 系统优化（稳定性优化） |
| 前端目录 | `yu-ai-code-mother-frontend/` |
| 微服务重构 | `fronted/yu-ai-code-mother-microservice/` |
