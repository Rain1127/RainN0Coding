# API 接口文档

> 后端地址：`http://localhost:8123/api`  
> 所有 Java 侧 Controller 即为前端对接的全部 REST 接口。Python FastAPI（端口 8000）不对前端直接暴露，仅供 Java 内部调用。

---

## 通用规范

### 基础 URL

```
http://<host>:8123/api
```

### 通用响应格式 `BaseResponse<T>`

```json
{
  "code": 0,        // 0 = 成功，其他 = 错误码
  "data": {},       // 业务数据
  "message": ""     // 提示信息
}
```

### 分页请求参数 `PageRequest`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `pageNum` | int | 1 | 当前页码 |
| `pageSize` | int | 10 | 每页条数 |
| `sortField` | string | - | 排序字段 |
| `sortOrder` | string | descend | 排序方向 (ascend/descend) |

### 分页响应格式 `Page<T>`

```json
{
  "records": [],
  "totalRow": 100,
  "pageNum": 1,
  "pageSize": 10
}
```

### 认证说明

- 使用 **Sa-Token** 框架，登录后 Cookie 自动携带会话
- 部分接口需要登录，部分接口需要管理员角色（`@AuthCheck(mustRole = "admin")`）
- 限流注解 `@RateLimit` 对高频接口做了 IP/用户级别限制

---

## 1. 用户模块 `/api/user`

### 1.1 用户注册

```
POST /api/user/register
```

**限流：** 3次/60秒/IP

**请求体：**
```json
{
  "userAccount": "string",
  "userPassword": "string",
  "checkPassword": "string"
}
```

**响应：** `BaseResponse<Long>` — 新用户 ID

---

### 1.2 用户登录

```
POST /api/user/login
```

**限流：** 10次/60秒/IP

**请求体：**
```json
{
  "userAccount": "string",
  "userPassword": "string"
}
```

**响应：** `BaseResponse<LoginUserVO>` — 脱敏用户信息 + 设置 Cookie 会话

---

### 1.3 获取当前登录用户

```
GET /api/user/get/login
```

**响应：** `BaseResponse<LoginUserVO>` — 当前登录用户信息

---

### 1.4 用户登出

```
POST /api/user/logout
```

**响应：** `BaseResponse<Boolean>`

---

### 1.5 管理员 — 创建用户

```
POST /api/user/add
```

**权限：** 管理员

**请求体：**
```json
{
  "userName": "string",
  "userAccount": "string",
  "userAvatar": "string",
  "userProfile": "string",
  "userRole": "user|admin"
}
```

> 默认密码 `12345678`

**响应：** `BaseResponse<Long>` — 新用户 ID

---

### 1.6 管理员 — 根据 ID 获取用户

```
GET /api/user/get?id={id}
```

**权限：** 管理员

**响应：** `BaseResponse<User>`

---

### 1.7 根据 ID 获取用户 VO（脱敏）

```
GET /api/user/get/vo?id={id}
```

**响应：** `BaseResponse<UserVO>`

---

### 1.8 管理员 — 删除用户

```
POST /api/user/delete
```

**权限：** 管理员

**请求体：**
```json
{ "id": 123456789 }
```

**响应：** `BaseResponse<Boolean>`

---

### 1.9 管理员 — 更新用户

```
POST /api/user/update
```

**权限：** 管理员

**请求体：** `UserUpdateRequest`（包含 id + 要更新的字段）

**响应：** `BaseResponse<Boolean>`

---

### 1.10 管理员 — 分页查询用户

```
POST /api/user/list/page/vo
```

**权限：** 管理员

**请求体：** `UserQueryRequest`（继承 PageRequest 的查询字段）

**响应：** `BaseResponse<Page<UserVO>>`

---

## 2. 应用模块 `/api/app`

### 2.1 AI 对话生成代码 ⭐ 核心接口

```
GET /api/app/chat/gen/code?appId={appId}&message={message}
```

**限流：** 5次/60秒/用户  
**返回类型：** `text/event-stream` (SSE 流式)

**请求参数（Query）：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| appId | Long | 是 | 应用 ID |
| message | String | 是 | 用户发送的消息/需求 |

**SSE 事件格式：**

- 数据事件：`data: {"d":"<chunk>"}` — 流式输出的文本块
- 结束事件：`event: done` `data: ` — 流结束标记

**流程：** Java 接收请求 → 通过 WebClient 转发到 Python `/api/generate-code` → Python LangGraph 多 Agent 协作生成代码 → SSE 流式回传 → Java 透明代理给前端

---

### 2.2 创建应用

```
POST /api/app/add
```

**限流：** 30次/60秒/用户

**请求体：**
```json
{
  "initPrompt": "string"
}
```

**响应：** `BaseResponse<Long>` — 新应用 ID

---

### 2.3 删除应用

```
POST /api/app/delete
```

**说明：** 用户只能删除自己的应用，管理员可删除任意应用

**请求体：**
```json
{ "id": 123456789 }
```

**响应：** `BaseResponse<Boolean>`

---

### 2.4 更新应用

```
POST /api/app/update
```

**说明：** 用户只能更新自己的应用名称

**请求体：**
```json
{
  "id": 123456789,
  "appName": "新名称"
}
```

**响应：** `BaseResponse<Boolean>`

---

### 2.5 根据 ID 获取应用详情

```
GET /api/app/get/vo?id={id}
```

**响应：** `BaseResponse<AppVO>` — 包含应用信息 + 创建者信息

---

### 2.6 分页获取我的应用

```
POST /api/app/my/list/page/vo
```

**说明：** 仅返回当前登录用户的应用，每页最多 20 条

**请求体：** `AppQueryRequest`（继承 PageRequest）

**响应：** `BaseResponse<Page<AppVO>>`

---

### 2.7 分页获取精选应用

```
POST /api/app/good/list/page/vo
```

**说明：** 带缓存（前 10 页），无需登录

**请求体：** `AppQueryRequest`

**响应：** `BaseResponse<Page<AppVO>>`

---

### 2.8 部署应用

```
POST /api/app/deploy
```

**限流：** 10次/60秒/用户

**请求体：**
```json
{ "appId": 123456789 }
```

**响应：** `BaseResponse<String>` — 部署 URL

---

### 2.9 下载应用代码

```
GET /api/app/download/{appId}
```

**限流：** 20次/60秒/用户  
**说明：** 仅应用创建者可下载，返回 ZIP 文件流

---

### 2.10 管理员 — 删除应用

```
POST /api/app/admin/delete
```

**权限：** 管理员

**请求体：**
```json
{ "id": 123456789 }
```

**响应：** `BaseResponse<Boolean>`

---

### 2.11 管理员 — 更新应用

```
POST /api/app/admin/update
```

**权限：** 管理员

**请求体：** `AppAdminUpdateRequest`

**响应：** `BaseResponse<Boolean>`

---

### 2.12 管理员 — 分页查询应用

```
POST /api/app/admin/list/page/vo
```

**权限：** 管理员

**请求体：** `AppQueryRequest`

**响应：** `BaseResponse<Page<AppVO>>`

---

### 2.13 管理员 — 根据 ID 获取应用详情

```
GET /api/app/admin/get/vo?id={id}
```

**权限：** 管理员

**响应：** `BaseResponse<AppVO>`

---

## 3. 对话历史模块 `/api/chatHistory`

### 3.1 查询应用的对话历史（游标分页）

```
GET /api/chatHistory/app/{appId}?pageSize=10&lastCreateTime=2025-01-01T00:00:00
```

**限流：** 30次/60秒/用户

**请求参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| appId | Long | 是 (路径) | - | 应用 ID |
| pageSize | int | 否 | 10 | 每页条数 |
| lastCreateTime | LocalDateTime | 否 | - | 游标：获取早于此时间的记录 |

**响应：** `BaseResponse<Page<ChatHistory>>`

---

### 3.2 管理员 — 分页查询所有对话历史

```
POST /api/chatHistory/admin/list/page/vo
```

**权限：** 管理员

**请求体：** `ChatHistoryQueryRequest`（继承 PageRequest，支持按 appId/userId/messageType 等过滤）

**响应：** `BaseResponse<Page<ChatHistory>>`

---

## 4. 应用版本模块 `/api/appVersion`

> ⚠️ 所有接口均未加权限校验和限流，可能为内部接口/开发中

### 4.1 保存版本

```
POST /api/appVersion/save
```

**请求体：** `AppVersion` 实体

**响应：** `boolean`

---

### 4.2 删除版本

```
DELETE /api/appVersion/remove/{id}
```

**响应：** `boolean`

---

### 4.3 更新版本

```
PUT /api/appVersion/update
```

**请求体：** `AppVersion` 实体

**响应：** `boolean`

---

### 4.4 查询所有版本

```
GET /api/appVersion/list
```

**响应：** `List<AppVersion>`

---

### 4.5 根据 ID 获取版本详情

```
GET /api/appVersion/getInfo/{id}
```

**响应：** `AppVersion`

---

### 4.6 分页查询版本

```
GET /api/appVersion/page?pageNum=1&pageSize=10
```

**响应：** `Page<AppVersion>`

---

## 5. 意图配置模块 `/api/intent-config`

### 5.1 获取意图树

```
GET /api/intent-config/tree
```

**响应：**
```json
{
  "code": 0,
  "data": {
    "customized": true,
    "treeJson": "{...}"
  }
}
```

- `customized`: 是否使用了自定义配置
- `treeJson`: 意图树 JSON 字符串（自定义 → 默认）

---

### 5.2 管理员 — 保存自定义意图树

```
POST /api/intent-config/save
```

**权限：** 管理员

**请求体：**
```json
{ "treeJson": "{...}" }
```

**响应：** `BaseResponse<?>`

---

### 5.3 管理员 — 重置为默认意图树

```
POST /api/intent-config/reset
```

**权限：** 管理员

**响应：** `BaseResponse<?>`

---

## 6. 工作流模块 `/api/workflow`

> ⚠️ 使用已废弃的 LangGraph4j（Java 侧），新功能已迁移到 Python LangGraph

### 6.1 同步执行工作流

```
POST /api/workflow/execute?prompt={prompt}
```

**限流：** 20次/60秒/IP

**响应：** `WorkflowContext`

---

### 6.2 SSE 流式执行工作流

```
GET /api/workflow/execute-sse?prompt={prompt}
```

**限流：** 20次/60秒/IP  
**返回类型：** `text/event-stream`

---

## 7. 静态资源模块 `/api/static`

### 7.1 访问生成的代码静态文件

```
GET /api/static/{deployKey}/**
```

**说明：** 访问 AI 生成并部署的应用代码，用于预览

- 目录访问（无尾 `/`）→ 301 重定向到 `/{deployKey}/`
- `/{deployKey}/` → 返回 `index.html`
- `/{deployKey}/{fileName}` → 返回对应文件（支持 HTML/CSS/JS/PNG/JPG）

**示例：**
```
GET /api/static/abc123/              → index.html
GET /api/static/abc123/css/app.css   → app.css
```

---

## 8. 健康检查 `/api/health`

### 8.1 健康检查

```
GET /api/health/
```

**响应：**
```json
{ "code": 0, "data": "Healthy", "message": "" }
```

---

## 附录：前端核心交互流程

```
1. 注册/登录
   POST /api/user/register → POST /api/user/login

2. 创建应用
   POST /api/app/add → 获得 appId

3. 发起 AI 对话（核心）
   GET /api/app/chat/gen/code?appId=xxx&message=我要一个todo应用
   → 前端通过 EventSource 接收 SSE 流

4. 查看对话历史
   GET /api/chatHistory/app/{appId}

5. 部署/预览
   POST /api/app/deploy → 获得 deployKey → GET /api/static/{deployKey}/

6. 下载代码
   GET /api/app/download/{appId}
```

---

## 附录：限流一览

| 接口 | 限流策略 | 频率 |
|------|----------|------|
| 注册 `/user/register` | IP | 3次/60秒 |
| 登录 `/user/login` | IP | 10次/60秒 |
| AI对话 `/app/chat/gen/code` | USER | 5次/60秒 |
| 部署 `/app/deploy` | USER | 10次/60秒 |
| 下载 `/app/download/{appId}` | USER | 20次/60秒 |
| 创建应用 `/app/add` | USER | 30次/60秒 |
| 查询历史 `/chatHistory/app/{appId}` | USER | 30次/60秒 |
| 工作流 `/workflow/*` | IP | 20次/60秒 |
