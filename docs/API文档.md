# 鱼AI代码助手 后端接口文档

## 基础信息

- **Base URL**: `http://localhost:8123/api`
- **鉴权方式**: Cookie / Session（Spring Session + Redis）
- **Content-Type**: `application/json`（SSE 接口除外）

### 通用响应结构

```json
{
  "code": 0,         // 0 = 成功，其他值见错误码表
  "data": {},        // 业务数据
  "message": ""      // 提示信息
}
```

### 通用分页响应

```json
{
  "records": [],
  "totalRow": 100,
  "pageNumber": 1,
  "pageSize": 10
}
```

---

## 1. 认证接口

### 1.1 用户注册

```
POST /user/register
```

无鉴权。

**请求体**:
```json
{
  "userAccount": "rain",
  "userPassword": "123456",
  "checkPassword": "123456"
}
```

**响应**: `BaseResponse<Long>` — 新用户 ID。

---

### 1.2 用户登录

```
POST /user/login
```

无鉴权。登录成功后 Session 中保存用户信息。

**请求体**:
```json
{
  "userAccount": "rain",
  "userPassword": "123456"
}
```

**响应**: `BaseResponse<LoginUserVO>`
```json
{
  "code": 0,
  "data": {
    "id": 123456789,
    "userAccount": "rain",
    "userName": "rain",
    "userAvatar": "https://example.com/avatar.png",
    "userProfile": "个人简介",
    "userRole": "user",
    "createTime": "2025-01-01T00:00:00",
    "updateTime": "2025-01-01T00:00:00"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 用户 ID |
| userAccount | String | 账号 |
| userName | String | 昵称 |
| userAvatar | String | 头像 URL |
| userProfile | String | 个人简介 |
| userRole | String | 角色：user / admin |
| createTime | DateTime | 注册时间 |
| updateTime | DateTime | 更新时间 |

---

### 1.3 用户注销

```
POST /user/logout
```

需要登录。

**响应**: `BaseResponse<Boolean>`

---

### 1.4 获取当前登录用户

```
GET /user/get/login
```

需要登录，从 Session 中获取。

**响应**: `BaseResponse<LoginUserVO>`（结构同 1.2）

---

## 2. 应用接口

### 2.1 创建应用

```
POST /app/add
```

需要登录。创建后应用名默认为"未命名应用"。

**请求体**:
```json
{
  "initPrompt": "你是一个前端专家，帮我生成..."
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| initPrompt | String | 否 | 初始 prompt，用于定制 AI 行为 |

**响应**: `BaseResponse<Long>` — 新应用 ID。

---

### 2.2 获取应用详情

```
GET /app/get/vo?id=123
```

**响应**: `BaseResponse<AppVO>`
```json
{
  "code": 0,
  "data": {
    "id": 123456789,
    "appName": "我的应用",
    "cover": "https://example.com/cover.png",
    "initPrompt": "你是一个前端专家...",
    "codeGenType": "html",
    "deployKey": "abc123xyz",
    "deployedTime": "2025-01-15T10:30:00",
    "priority": 1,
    "userId": 123456789,
    "currentVersion": 3,
    "createTime": "2025-01-10T08:00:00",
    "updateTime": "2025-01-15T10:30:00",
    "editTime": "2025-01-15T09:00:00",
    "userVO": {
      "id": 123456789,
      "userName": "rain"
    }
  }
}
```

**AppVO 字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 应用 ID |
| appName | String | 应用名称 |
| cover | String | 封面图 URL |
| initPrompt | String | 初始 prompt |
| codeGenType | String | 代码生成类型枚举 |
| deployKey | String | 部署标识 key |
| deployedTime | DateTime | 部署时间，null 表示未部署 |
| priority | Integer | 优先级（精选标记阈值） |
| userId | Long | 创建者 ID |
| currentVersion | Integer | 当前版本号 |
| createTime | DateTime | 创建时间 |
| updateTime | DateTime | 更新时间 |
| editTime | DateTime | 编辑时间 |
| userVO.id | Long | 创建者 ID |
| userVO.userName | String | 创建者昵称 |

**代码生成类型 codeGenType 枚举值**:
`html`, `multi_file`, `vue_project`, `python`, `java`, `go`, `rust`, `nodejs`, `generic`

---

### 2.3 更新应用

```
POST /app/update
```

需要登录，仅应用创建者可操作。

**请求体**:
```json
{
  "id": 123456789,
  "appName": "新应用名称"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | Long | 是 | 应用 ID |
| appName | String | 是 | 新名称 |

**响应**: `BaseResponse<Boolean>`

---

### 2.4 删除应用

```
POST /app/delete
```

需要登录，仅创建者或管理员可删除。

**请求体**:
```json
{
  "id": 123456789
}
```

**响应**: `BaseResponse<Boolean>`

---

### 2.5 我的应用分页列表

```
POST /app/my/list/page/vo
```

需要登录，每页最多 20 条。

**请求体**:
```json
{
  "pageNum": 1,
  "pageSize": 10,
  "sortField": "createTime",
  "sortOrder": "descend",
  "appName": "搜索关键词",
  "codeGenType": "html"
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| pageNum | int | 否 | 1 | 页码 |
| pageSize | int | 否 | 10 | 每页条数（最大 20） |
| sortField | String | 否 | - | 排序字段 |
| sortOrder | String | 否 | descend | ascend / descend |
| appName | String | 否 | - | 按名称模糊搜索 |
| codeGenType | String | 否 | - | 按代码类型筛选 |

**响应**: `BaseResponse<Page<AppVO>>`
```json
{
  "code": 0,
  "data": {
    "records": [ { "...": "AppVO 结构见 2.2" } ],
    "totalRow": 25,
    "pageNumber": 1,
    "pageSize": 10
  }
}
```

---

### 2.6 精选应用分页列表

```
POST /app/good/list/page/vo
```

公开接口，无需登录。有服务端缓存（前 10 页），只返回 priority 达标的应用。

**请求体**: 同 2.5。

**响应**: `BaseResponse<Page<AppVO>>`（同 2.5）。

---

### 2.7 部署应用

```
POST /app/deploy
```

需要登录，仅应用创建者可操作。

**请求体**:
```json
{
  "appId": 123456789
}
```

**响应**: `BaseResponse<String>` — 部署后的可访问 URL。

---

### 2.8 下载应用代码

```
GET /app/download/{appId}
```

需要登录，仅应用创建者可下载。返回 ZIP 文件流。

---

### 2.9 管理员 — 分页获取应用列表

```
POST /app/admin/list/page/vo
```

需要 `admin` 角色。

**请求体**: 同 2.5（额外支持 id、userId、deployKey、priority 等筛选条件）。

**响应**: `BaseResponse<Page<AppVO>>`（同 2.5）。

---

### 2.10 管理员 — 获取应用详情

```
GET /app/admin/get/vo?id=123
```

需要 `admin` 角色。

**响应**: `BaseResponse<AppVO>`（同 2.2）。

---

### 2.11 管理员 — 更新应用

```
POST /app/admin/update
```

需要 `admin` 角色。

**请求体**:
```json
{
  "id": 123456789,
  "appName": "新名称",
  "cover": "https://example.com/new-cover.png",
  "priority": 10
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | Long | 是 | 应用 ID |
| appName | String | 否 | 应用名称 |
| cover | String | 否 | 封面图 URL |
| priority | Integer | 否 | 优先级 |

**响应**: `BaseResponse<Boolean>`

---

### 2.12 管理员 — 删除应用

```
POST /app/admin/delete
```

需要 `admin` 角色。

**请求体**:
```json
{
  "id": 123456789
}
```

**响应**: `BaseResponse<Boolean>`

---

## 3. AI 对话（SSE 流式）

```
GET /app/chat/gen/code?appId=123&message=帮我生成一个登录页面
```

需要登录。

**限流**: 每位用户 60 秒内最多 5 次请求。

**请求参数** (Query String):

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| appId | Long | 是 | 应用 ID |
| message | String | 是 | 用户消息（需 URL 编码） |

**响应格式**: `Content-Type: text/event-stream`

每条数据事件携带一段 AI 生成的文本：
```
data:{"d":"<!DOCTYPE html>\n<html>\n..."}

data:{"d":"  <body>\n    <div class=\"login\">\n..."}

event:done
data:
```

- `data:` 行 — JSON 对象 `{"d": "文本片段"}`，`d` 字段为本次推送的文本块
- `event:done` — 表示流结束
- `event:business-error` — 表示业务异常，下一条 `data:` 行携带错误信息

**注意**: 该接口不走通用 JSON 响应结构，直接返回 SSE 原始流。

---

## 4. 对话历史

### 4.1 查询应用的对话历史

```
GET /chatHistory/app/{appId}?pageSize=50&lastCreateTime=2025-01-15T10:00:00
```

需要登录，游标分页（按创建时间倒序）。

**请求参数**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| pageSize | int | 否 | 10 | 每页条数 |
| lastCreateTime | DateTime | 否 | - | 游标：查询早于此时间的记录 |

**响应**: `BaseResponse<Page<ChatHistory>>`
```json
{
  "code": 0,
  "data": {
    "records": [
      {
        "id": 1,
        "message": "帮我写一个登录页面",
        "messageType": "user",
        "appId": 123456789,
        "userId": 987654321,
        "createTime": "2025-01-15T10:00:00"
      },
      {
        "id": 2,
        "message": "好的，这是生成的HTML代码...",
        "messageType": "ai",
        "appId": 123456789,
        "userId": 987654321,
        "createTime": "2025-01-15T10:00:05"
      }
    ],
    "totalRow": 50,
    "pageNumber": 1,
    "pageSize": 50
  }
}
```

**ChatHistory 字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 记录 ID |
| message | String | 消息内容 |
| messageType | String | user / ai |
| appId | Long | 所属应用 ID |
| userId | Long | 用户 ID |
| createTime | DateTime | 创建时间 |

---

### 4.2 管理员 — 分页查询所有对话历史

```
POST /chatHistory/admin/list/page/vo
```

需要 `admin` 角色。标准分页查询。

**请求体**:
```json
{
  "pageNum": 1,
  "pageSize": 10,
  "message": "搜索关键词",
  "messageType": "user",
  "appId": 123,
  "userId": 456
}
```

**响应**: `BaseResponse<Page<ChatHistory>>`（结构同 4.1）。

---

## 5. 用户管理（管理员）

以下接口均需 `admin` 角色。

### 5.1 分页查询用户

```
POST /user/list/page/vo
```

**请求体**:
```json
{
  "pageNum": 1,
  "pageSize": 10,
  "id": 123,
  "userName": "搜索昵称",
  "userAccount": "搜索账号",
  "userProfile": "搜索简介",
  "userRole": "user"
}
```

**响应**: `BaseResponse<Page<UserVO>>`
```json
{
  "code": 0,
  "data": {
    "records": [
      {
        "id": 123456789,
        "userAccount": "rain",
        "userName": "rain",
        "userAvatar": "https://...",
        "userProfile": "个人简介",
        "userRole": "user",
        "createTime": "2025-01-01T00:00:00"
      }
    ],
    "totalRow": 100,
    "pageNumber": 1,
    "pageSize": 10
  }
}
```

**UserVO 字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Long | 用户 ID |
| userAccount | String | 账号 |
| userName | String | 昵称 |
| userAvatar | String | 头像 URL |
| userProfile | String | 个人简介 |
| userRole | String | user / admin |
| createTime | DateTime | 注册时间 |

---

### 5.2 新增用户

```
POST /user/add
```

**请求体**:
```json
{
  "userName": "新用户",
  "userAccount": "newuser",
  "userAvatar": "https://...",
  "userProfile": "个人简介",
  "userRole": "user"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| userName | String | 是 | 昵称 |
| userAccount | String | 是 | 账号 |
| userAvatar | String | 否 | 头像 URL |
| userProfile | String | 否 | 简介 |
| userRole | String | 是 | user / admin |

默认密码为 `12345678`。

**响应**: `BaseResponse<Long>` — 新用户 ID。

---

### 5.3 更新用户

```
POST /user/update
```

**请求体**:
```json
{
  "id": 123456789,
  "userName": "新昵称",
  "userAvatar": "https://...",
  "userProfile": "新简介",
  "userRole": "admin"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | Long | 是 | 用户 ID |
| userName | String | 否 | 昵称 |
| userAvatar | String | 否 | 头像 URL |
| userProfile | String | 否 | 简介 |
| userRole | String | 否 | user / admin |

**响应**: `BaseResponse<Boolean>`

---

### 5.4 删除用户

```
POST /user/delete
```

**请求体**:
```json
{
  "id": 123456789
}
```

**响应**: `BaseResponse<Boolean>`

---

### 5.5 获取用户详情（脱敏）

```
GET /user/get/vo?id=123
```

**响应**: `BaseResponse<UserVO>`（结构同 5.1）。

---

## 6. 意图配置

### 6.1 获取意图树

```
GET /intent-config/tree
```

公开接口，无需登录。

**响应**: `BaseResponse<Map>`
```json
{
  "code": 0,
  "data": {
    "customized": true,
    "treeJson": "[{\"key\":\"web\",\"title\":\"Web开发\",\"children\":[...]}]"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| customized | Boolean | true 表示管理员已自定义，false 表示使用默认配置 |
| treeJson | String | JSON 字符串，需 `JSON.parse` 后使用 |

`treeJson` 解析后的节点结构:
```json
{
  "key": "web",
  "title": "Web开发",
  "type": "category",
  "source": "system",
  "enabled": true,
  "description": "Web相关开发任务",
  "examples": ["创建登录页面", "搭建后台管理系统"],
  "parentKey": null,
  "sortOrder": 1,
  "collection": "default",
  "children": [
    {
      "key": "frontend",
      "title": "前端开发",
      "children": []
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| key | String | 唯一标识 |
| title | String | 显示名称 |
| type | String | 节点类型 |
| source | String | 来源标识 |
| enabled | Boolean | 是否启用 |
| description | String | 描述 |
| examples | String[] | 示例 prompt 列表 |
| parentKey | String | 父节点 key |
| sortOrder | Integer | 排序权重 |
| collection | String | 所属集合 |
| children | IntentNode[] | 子节点列表 |

---

### 6.2 保存自定义意图树

```
POST /intent-config/save
```

需要 `admin` 角色。

**请求体**:
```json
{
  "treeJson": "[{\"key\":\"web\",\"title\":\"Web开发\",...}]"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| treeJson | String | 是 | `JSON.stringify` 后的意图树数组 |

**响应**: `BaseResponse<Boolean>`

---

### 6.3 重置意图树

```
POST /intent-config/reset
```

需要 `admin` 角色。删除自定义配置，恢复默认意图树。

**响应**: `BaseResponse<Boolean>`

---

## 附录

### A. 错误码

| code | 说明 |
|------|------|
| 0 | 成功 |
| 40000 | 请求参数错误 |
| 40100 | 未登录 |
| 40300 | 无权限 |
| 40400 | 数据不存在 |
| 50000 | 系统内部错误 |

### B. 接口权限速查

| 接口 | 鉴权 | 备注 |
|------|------|------|
| `POST /user/register` | 无 | |
| `POST /user/login` | 无 | |
| `POST /user/logout` | 登录 | |
| `GET /user/get/login` | 登录 | |
| `GET /user/get/vo` | 登录 | |
| `POST /user/*` (add/delete/update/list) | admin | |
| `POST /app/add` | 登录 | |
| `GET /app/get/vo` | 无 | |
| `POST /app/update` | 登录 | 仅创建者 |
| `POST /app/delete` | 登录 | 创建者或 admin |
| `POST /app/my/list/page/vo` | 登录 | |
| `POST /app/good/list/page/vo` | 无 | 有缓存 |
| `POST /app/deploy` | 登录 | 仅创建者 |
| `GET /app/download/{appId}` | 登录 | 仅创建者 |
| `POST /app/admin/*` | admin | |
| `GET /app/admin/get/vo` | admin | |
| `GET /app/chat/gen/code` | 登录 | SSE 流式，限流 |
| `GET /chatHistory/app/{appId}` | 登录 | |
| `POST /chatHistory/admin/list/page/vo` | admin | |
| `GET /intent-config/tree` | 无 | |
| `POST /intent-config/save` | admin | |
| `POST /intent-config/reset` | admin | |
