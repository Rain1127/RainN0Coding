"""
RAG 种子数据 —— 契合 AI 代码生成业务（多语言 / 多框架）

4 个 Collection 的初始知识：
1. framework_api    — API 参考（Vue3 / FastAPI / Spring Boot / Gin / Express / Actix-web …）
2. component_library — 可复用代码骨架（Vue SFC / Python Service / Java Controller / Go Handler …）
3. design_pattern   — 通用架构模式（前端 UI + 后端 Repository / Service Layer / Middleware …）
4. error_pattern    — 高频错误与修复方案（覆盖 Vue / Python / Java / Go / Node.js / Rust）

覆盖技术栈：
  - 前端: Vue 3, Vue Router 4, Pinia, Tailwind CSS v3
  - Python: FastAPI, Flask, Pydantic v2, SQLAlchemy 2.0
  - Java: Spring Boot 3.x, Spring Data JPA, Bean Validation
  - Go: Gin, net/http, database/sql, sqlx
  - Node.js: Express, NestJS, Prisma
  - Rust: Actix-web, Axum, SQLx, Serde

code_store 由构建成功后自动填充，不在此处灌数据。
"""

# ============================================================
# Collection 1: framework_api
# ============================================================
FRAMEWORK_API_SEEDS = [
    # ---- Vue 3 响应式核心 ----
    {
        "api_name": "ref",
        "signature": "function ref<T>(value: T): Ref<T>",
        "import_statement": "import { ref } from 'vue'",
        "example": "const count = ref<number>(0)\ncount.value++  // 模板中自动解包，script 中需 .value",
        "framework": "vue3",
    },
    {
        "api_name": "reactive",
        "signature": "function reactive<T extends object>(target: T): UnwrapNestedRefs<T>",
        "import_statement": "import { reactive } from 'vue'",
        "example": "const state = reactive({ count: 0, name: 'Vue' })\n// 不能替换整个对象，不能解构（会丢失响应式）",
        "framework": "vue3",
    },
    {
        "api_name": "computed",
        "signature": "function computed<T>(getter: () => T): ComputedRef<T>",
        "import_statement": "import { computed } from 'vue'",
        "example": "const doubled = computed(() => count.value * 2)\n// 只读，自动追踪依赖，惰性求值",
        "framework": "vue3",
    },
    {
        "api_name": "watch",
        "signature": "function watch(source, callback: (newVal, oldVal) => void, options?: WatchOptions): StopHandle",
        "import_statement": "import { watch } from 'vue'",
        "example": "watch(() => state.count, (newVal, oldVal) => { console.log(newVal, oldVal) }, { immediate: true })",
        "framework": "vue3",
    },
    {
        "api_name": "watchEffect",
        "signature": "function watchEffect(effect: (onCleanup) => void, options?: WatchOptions): StopHandle",
        "import_statement": "import { watchEffect } from 'vue'",
        "example": "watchEffect(() => { console.log(count.value) })  // 自动追踪依赖，立即执行",
        "framework": "vue3",
    },
    # ---- 组件定义 ----
    {
        "api_name": "defineProps",
        "signature": "function defineProps<T>(): T  // 仅 <script setup> 可用",
        "import_statement": "// 编译器宏，无需 import",
        "example": "const props = defineProps<{ title: string; count?: number }>()\n// 或 withDefaults: withDefaults(defineProps<T>(), { count: 0 })",
        "framework": "vue3",
    },
    {
        "api_name": "defineEmits",
        "signature": "function defineEmits<T>(): (event: keyof T, ...args: any[]) => void",
        "import_statement": "// 编译器宏，无需 import",
        "example": "const emit = defineEmits<{ (e: 'update', value: number): void; (e: 'delete', id: string): void }>()",
        "framework": "vue3",
    },
    {
        "api_name": "defineExpose",
        "signature": "function defineExpose(exposed: Record<string, any>): void",
        "import_statement": "// 编译器宏，无需 import",
        "example": "defineExpose({ focus, reset })  // 暴露方法给父组件 ref 调用",
        "framework": "vue3",
    },
    {
        "api_name": "defineSlots",
        "signature": "function defineSlots<T extends Record<string, any>>(): T",
        "import_statement": "// 编译器宏，无需 import",
        "example": "const slots = defineSlots<{ default(): any; header(): any; footer(): any }>()",
        "framework": "vue3",
    },
    {
        "api_name": "defineOptions",
        "signature": "function defineOptions(options: ComponentOptions): void",
        "import_statement": "// 编译器宏，无需 import",
        "example": "defineOptions({ name: 'ProductCard', inheritAttrs: false })",
        "framework": "vue3",
    },
    # ---- 生命周期 ----
    {
        "api_name": "onMounted",
        "signature": "function onMounted(callback: () => void): void",
        "import_statement": "import { onMounted } from 'vue'",
        "example": "onMounted(() => { fetchData() })  // DOM 挂载后执行",
        "framework": "vue3",
    },
    {
        "api_name": "onUnmounted",
        "signature": "function onUnmounted(callback: () => void): void",
        "import_statement": "import { onUnmounted } from 'vue'",
        "example": "onUnmounted(() => { clearInterval(timer) })  // 组件卸载前清理",
        "framework": "vue3",
    },
    {
        "api_name": "onBeforeMount",
        "signature": "function onBeforeMount(callback: () => void): void",
        "import_statement": "import { onBeforeMount } from 'vue'",
        "example": "onBeforeMount(() => { /* DOM 挂载前 */ })",
        "framework": "vue3",
    },
    # ---- 依赖注入 ----
    {
        "api_name": "provide",
        "signature": "function provide<T>(key: InjectionKey<T> | string, value: T): void",
        "import_statement": "import { provide } from 'vue'",
        "example": "provide('theme', ref('dark'))  // 在父组件中提供，子组件用 inject 接收",
        "framework": "vue3",
    },
    {
        "api_name": "inject",
        "signature": "function inject<T>(key: InjectionKey<T> | string, defaultValue?: T): T",
        "import_statement": "import { inject } from 'vue'",
        "example": "const theme = inject<Ref<string>>('theme', ref('light'))",
        "framework": "vue3",
    },
    # ---- 模板指令 ----
    {
        "api_name": "v-model",
        "signature": "v-model / v-model:propName 双向绑定",
        "import_statement": "// 模板指令，无需 import",
        "example": "<input v-model=\"form.name\" />\n<ChildComp v-model:title=\"title\" />  // 对应 defineEmits('update:title')",
        "framework": "vue3",
    },
    {
        "api_name": "v-if",
        "signature": "v-if / v-else-if / v-else 条件渲染",
        "import_statement": "// 模板指令，无需 import",
        "example": "<div v-if=\"show\">可见</div><div v-else>隐藏</div>  // 真正销毁/重建 DOM",
        "framework": "vue3",
    },
    {
        "api_name": "v-for",
        "signature": "v-for=\"item in items\" :key=\"item.id\" 列表渲染",
        "import_statement": "// 模板指令，无需 import",
        "example": "<li v-for=\"item in items\" :key=\"item.id\">{{ item.name }}</li>\n// 必须提供唯一 key",
        "framework": "vue3",
    },
    {
        "api_name": "v-show",
        "signature": "v-show=\"visible\" 显示/隐藏",
        "import_statement": "// 模板指令，无需 import",
        "example": "<div v-show=\"visible\">频繁切换用 v-show，而非 v-if</div>  // 仅切换 display",
        "framework": "vue3",
    },
    {
        "api_name": "v-once",
        "signature": "v-once 一次性渲染",
        "import_statement": "// 模板指令，无需 import",
        "example": "<span v-once>{{ staticContent }}</span>  // 只渲染一次，不追踪依赖",
        "framework": "vue3",
    },
    # ---- 内置组件 ----
    {
        "api_name": "Transition",
        "signature": "<Transition name=\"fade\"> 动画过渡组件",
        "import_statement": "import { Transition } from 'vue'  // 可选，模板中自动可用",
        "example": "<Transition name=\"fade\"><div v-if=\"show\">内容</div></Transition>\n/* CSS: .fade-enter-active { transition: opacity 0.3s } */",
        "framework": "vue3",
    },
    {
        "api_name": "Teleport",
        "signature": "<Teleport to=\"body\"> 传送门组件",
        "import_statement": "// 模板中自动可用",
        "example": "<Teleport to=\"body\"><ModalDialog /></Teleport>  // 渲染到 body 下，避免 overflow hidden",
        "framework": "vue3",
    },
    {
        "api_name": "Suspense",
        "signature": "<Suspense> 异步组件加载",
        "import_statement": "// 模板中自动可用",
        "example": "<Suspense><template #default><AsyncComp /></template><template #fallback>加载中...</template></Suspense>",
        "framework": "vue3",
    },
    # ---- Vue Router 4 ----
    {
        "api_name": "createRouter",
        "signature": "function createRouter(options: RouterOptions): Router",
        "import_statement": "import { createRouter, createWebHistory } from 'vue-router'",
        "example": "const router = createRouter({\n  history: createWebHistory(),\n  routes: [{ path: '/', component: () => import('@/views/Home.vue') }]\n})",
        "framework": "vue-router4",
    },
    {
        "api_name": "useRouter",
        "signature": "function useRouter(): Router",
        "import_statement": "import { useRouter } from 'vue-router'",
        "example": "const router = useRouter()\nrouter.push('/user/' + id)\nrouter.replace('/login')",
        "framework": "vue-router4",
    },
    {
        "api_name": "useRoute",
        "signature": "function useRoute(): RouteLocationNormalizedLoaded",
        "import_statement": "import { useRoute } from 'vue-router'",
        "example": "const route = useRoute()\nconsole.log(route.params.id, route.query.page)\nwatch(() => route.params.id, (newId) => {...})",
        "framework": "vue-router4",
    },
    {
        "api_name": "router-link",
        "signature": "<router-link to=\"/path\"> 导航链接组件",
        "import_statement": "// 全局注册，无需 import",
        "example": "<router-link :to=\"{ name: 'user', params: { id: 1 } }\">用户</router-link>",
        "framework": "vue-router4",
    },
    # ---- Pinia ----
    {
        "api_name": "defineStore",
        "signature": "function defineStore(id, options): StoreDefinition  // Setup Store 风格",
        "import_statement": "import { defineStore } from 'pinia'",
        "example": "export const useUserStore = defineStore('user', () => {\n  const user = ref<User | null>(null)\n  const login = async (id: string) => { user.value = await fetchUser(id) }\n  return { user, login }\n})",
        "framework": "pinia",
    },
    {
        "api_name": "storeToRefs",
        "signature": "function storeToRefs(store): ToRefs  // 解构保持响应式",
        "import_statement": "import { storeToRefs } from 'pinia'",
        "example": "const store = useUserStore()\nconst { user } = storeToRefs(store)  // 不解构 actions\nconst { login } = store  // actions 直接解构",
        "framework": "pinia",
    },
    # ---- Tailwind CSS v3 ----
    {
        "api_name": "Tailwind utility classes",
        "signature": "utility-first CSS 框架，类名组合构建样式",
        "import_statement": "// 无需 import，直接在模板 class 中使用",
        "example": "flex / grid / hidden / block / relative / absolute / fixed\np-4 / m-2 / gap-4 / space-y-4\ntext-lg / font-bold / text-gray-900\ndark:bg-gray-800 / hover:bg-blue-500\nsm:flex-col / md:grid-cols-2 / lg:grid-cols-3\ntransition / duration-300 / ease-in-out",
        "framework": "tailwind3",
    },

    # ---- Python (FastAPI / Flask) ----
    {
        "api_name": "FastAPI()",
        "signature": "def FastAPI(*, debug=False, title='FastAPI', lifespan=None) -> FastAPI",
        "import_statement": "from fastapi import FastAPI",
        "example": "app = FastAPI(title='My API', version='1.0.0')\n# lifespan 用于管理启动/关闭时的资源：\n@app.on_event('startup')\nasync def startup(): ...",
        "framework": "fastapi",
    },
    {
        "api_name": "@app.get / @app.post / @app.put / @app.delete",
        "signature": "def get(path: str, *, response_model=None, status_code=200, ...) -> Callable",
        "import_statement": "from fastapi import FastAPI",
        "example": "@app.get('/users/{user_id}', response_model=UserOut)\nasync def get_user(user_id: int):\n    return await fetch_user(user_id)\n# 路径参数自动校验类型；response_model 控制输出序列化",
        "framework": "fastapi",
    },
    {
        "api_name": "Path / Query / Body",
        "signature": "Path(default, *, gt, ge, lt, le, min_length, max_length, regex, ...) / Query(...) / Body(...)",
        "import_statement": "from fastapi import Path, Query, Body",
        "example": "@app.get('/items')\nasync def list_items(\n    page: int = Query(1, ge=1, description='页码'),\n    size: int = Query(20, le=100),\n    q: str | None = Query(None, min_length=2),\n): ...\n# Query 用于 GET 参数，Body 用于 POST/PUT body，Path 用于路径参数",
        "framework": "fastapi",
    },
    {
        "api_name": "Depends",
        "signature": "def Depends(dependency: Callable, *, use_cache=True) -> Any",
        "import_statement": "from fastapi import Depends",
        "example": "async def get_db():\n    async with SessionLocal() as db:\n        yield db\n\n@app.get('/users', response_model=list[UserOut])\nasync def list_users(db: AsyncSession = Depends(get_db)):\n    return await db.execute(select(User))\n# Depends 实现依赖注入，支持嵌套、缓存和 yield 清理",
        "framework": "fastapi",
    },
    {
        "api_name": "HTTPException",
        "signature": "class HTTPException(status_code: int, detail: str = None, headers: dict = None)",
        "import_statement": "from fastapi import HTTPException",
        "example": "@app.get('/users/{user_id}')\nasync def get_user(user_id: int):\n    user = await find_user(user_id)\n    if not user:\n        raise HTTPException(status_code=404, detail=f'用户 {user_id} 不存在')\n    return user",
        "framework": "fastapi",
    },
    {
        "api_name": "BackgroundTasks",
        "signature": "class BackgroundTasks  // 在响应返回后执行后台任务",
        "import_statement": "from fastapi import BackgroundTasks",
        "example": "@app.post('/send-email')\nasync def send_email(background_tasks: BackgroundTasks):\n    background_tasks.add_task(send_email_async, to='user@example.com')\n    return {'message': '邮件已加入后台队列'}\n# 任务在响应返回后执行；不保证成功，适合非关键任务",
        "framework": "fastapi",
    },
    {
        "api_name": "APIRouter",
        "signature": "class APIRouter(*, prefix='', tags=[], dependencies=[]) -> Router",
        "import_statement": "from fastapi import APIRouter",
        "example": "# routers/users.py\nrouter = APIRouter(prefix='/users', tags=['用户管理'])\n\n@router.get('/', response_model=list[UserOut])\nasync def list_users(db = Depends(get_db)): ...\n\n# main.py\napp.include_router(router)\n# APIRouter 实现模块化路由拆分",
        "framework": "fastapi",
    },
    {
        "api_name": "CORSMiddleware",
        "signature": "class CORSMiddleware(app, allow_origins, allow_methods, allow_headers, ...)",
        "import_statement": "from fastapi.middleware.cors import CORSMiddleware",
        "example": "app.add_middleware(\n    CORSMiddleware,\n    allow_origins=['http://localhost:5173'],\n    allow_credentials=True,\n    allow_methods=['*'],\n    allow_headers=['*'],\n)\n# 在开发环境可用 allow_origins=['*']，生产环境必须指定具体域名",
        "framework": "fastapi",
    },
    {
        "api_name": "File / UploadFile",
        "signature": "class UploadFile(file, *, size=None, filename=None, headers=None)",
        "import_statement": "from fastapi import File, UploadFile",
        "example": "@app.post('/upload')\nasync def upload(file: UploadFile = File(...)):\n    content = await file.read()\n    with open(f'uploads/{file.filename}', 'wb') as f:\n        f.write(content)\n    return {'filename': file.filename, 'size': file.size}\n# UploadFile 支持大文件流式读取",
        "framework": "fastapi",
    },
    {
        "api_name": "pydantic BaseModel",
        "signature": "class BaseModel  // Pydantic v2 基础模型，自动校验 + 序列化",
        "import_statement": "from pydantic import BaseModel, Field",
        "example": "class UserCreate(BaseModel):\n    name: str = Field(..., min_length=1, max_length=50, description='用户名')\n    email: EmailStr\n    age: int = Field(ge=0, le=150)\n    tags: list[str] = []\n\n# Pydantic v2 用 Field 定义校验规则，支持自定义 validators",
        "framework": "pydantic",
    },
    {
        "api_name": "Field (Pydantic v2)",
        "signature": "def Field(default=PydanticUndefined, *, default_factory=None, alias=None, gt=None, ge=None, lt=None, le=None, min_length=None, max_length=None, pattern=None, description=None, ...) -> FieldInfo",
        "import_statement": "from pydantic import BaseModel, Field",
        "example": "class Product(BaseModel):\n    name: str = Field(..., min_length=1, max_length=100)\n    price: float = Field(..., gt=0, description='价格必须大于0')\n    tags: list[str] = Field(default_factory=list)\n    is_active: bool = Field(default=True)\n# default_factory 用于可变默认值（list/dict），避免全局共享",
        "framework": "pydantic",
    },
    {
        "api_name": "model_validator (Pydantic v2)",
        "signature": "@model_validator(mode: 'before' | 'after' | 'wrap')",
        "import_statement": "from pydantic import model_validator",
        "example": "class UserCreate(BaseModel):\n    password: str\n    password_confirm: str\n\n    @model_validator(mode='after')\n    def check_passwords_match(self):\n        if self.password != self.password_confirm:\n            raise ValueError('两次密码不一致')\n        return self\n# mode='before' 在字段校验前运行，可访问原始输入",
        "framework": "pydantic",
    },
    {
        "api_name": "ConfigDict (Pydantic v2)",
        "signature": "class ConfigDict  // 替代 v1 的 class Config 内部类",
        "import_statement": "from pydantic import ConfigDict",
        "example": "class UserOut(BaseModel):\n    model_config = ConfigDict(\n        from_attributes=True,  # 允许从 ORM 对象创建\n        str_strip_whitespace=True,\n        use_enum_values=True,\n        json_schema_extra={'example': {'name': 'Alice'}},\n    )\n    name: str\n    email: str\n# from_attributes=True 等价于 v1 的 orm_mode=True",
        "framework": "pydantic",
    },
    {
        "api_name": "create_async_engine (SQLAlchemy 2.0)",
        "signature": "def create_async_engine(url, *, echo=False, pool_size=5, max_overflow=10, ...) -> AsyncEngine",
        "import_statement": "from sqlalchemy.ext.asyncio import create_async_engine",
        "example": "DATABASE_URL = 'postgresql+asyncpg://user:pass@localhost/db'\n\nengine = create_async_engine(\n    DATABASE_URL,\n    echo=False,  # 生产环境关闭 SQL 日志\n    pool_size=20,\n    max_overflow=10,\n    pool_pre_ping=True,  # 连接前检查可用性\n)\n# pool_pre_ping=True 防止使用已断开的连接",
        "framework": "sqlalchemy",
    },
    {
        "api_name": "async_sessionmaker (SQLAlchemy 2.0)",
        "signature": "class async_sessionmaker(bind, *, class_=AsyncSession, expire_on_commit=False)",
        "import_statement": "from sqlalchemy.ext.asyncio import async_sessionmaker",
        "example": "async_sessionmaker(engine, expire_on_commit=False)\n# expire_on_commit=False 避免 commit 后访问属性触发 lazy load",
        "framework": "sqlalchemy",
    },
    {
        "api_name": "DeclarativeBase + Mapped (SQLAlchemy 2.0)",
        "signature": "class Base(DeclarativeBase)  // 声明式基类\nMapped[T] / mapped_column(...)",
        "import_statement": "from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column",
        "example": "class Base(DeclarativeBase):\n    pass\n\nclass User(Base):\n    __tablename__ = 'users'\n    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)\n    name: Mapped[str] = mapped_column(String(50), index=True)\n    email: Mapped[str] = mapped_column(String(100), unique=True)\n    created_at: Mapped[datetime] = mapped_column(server_default=func.now())\n# Mapped[T] 提供静态类型提示，mapped_column 定义列属性",
        "framework": "sqlalchemy",
    },
    {
        "api_name": "relationship (SQLAlchemy 2.0)",
        "signature": "def relationship(argument, *, back_populates=None, lazy='select', ...) -> Relationship",
        "import_statement": "from sqlalchemy.orm import relationship",
        "example": "class User(Base):\n    __tablename__ = 'users'\n    id: Mapped[int] = mapped_column(primary_key=True)\n    posts: Mapped[list['Post']] = relationship(back_populates='author', lazy='selectin')\n\nclass Post(Base):\n    __tablename__ = 'posts'\n    id: Mapped[int] = mapped_column(primary_key=True)\n    author_id: Mapped[int] = mapped_column(ForeignKey('users.id'))\n    author: Mapped['User'] = relationship(back_populates='posts')\n# back_populates 建立双向关系；lazy='selectin' 用 IN 查询避免 N+1",
        "framework": "sqlalchemy",
    },
    {
        "api_name": "select() (SQLAlchemy 2.0)",
        "signature": "def select(*entities) -> Select  // 类型安全的查询构建器",
        "import_statement": "from sqlalchemy import select, func",
        "example": "async def get_active_users(db: AsyncSession) -> list[User]:\n    stmt = (\n        select(User)\n        .where(User.is_active == True)\n        .order_by(User.created_at.desc())\n        .limit(100)\n    )\n    result = await db.execute(stmt)\n    return list(result.scalars().all())\n# scalars() 返回单列结果的迭代器；.all() 获取全部",
        "framework": "sqlalchemy",
    },
    {
        "api_name": "pytest fixture + conftest.py",
        "signature": "@pytest.fixture(scope='function' | 'class' | 'module' | 'session')",
        "import_statement": "import pytest",
        "example": "# conftest.py\n@pytest.fixture(scope='session')\ndef engine():\n    return create_engine(TEST_DB_URL)\n\n@pytest.fixture\nasync def db_session(engine):\n    async with async_sessionmaker(engine)() as session:\n        yield session\n        await session.rollback()  # 测试后回滚，保持数据库干净\n\n# test_users.py\n@pytest.mark.asyncio\nasync def test_create_user(db_session):\n    user = await create_user(db_session, UserCreate(name='Test'))\n    assert user.name == 'Test'",
        "framework": "python-stdlib",
    },
    {
        "api_name": "async def (异步函数)",
        "signature": "async def func_name(params) -> ReturnType:  // 定义协程",
        "import_statement": "# Python 3.5+ 原生支持，无需 import",
        "example": "async def fetch_users(limit: int = 10) -> list[User]:\n    async with httpx.AsyncClient() as client:\n        r = await client.get(f'/api/users?limit={limit}')\n        return [User(**item) for item in r.json()]\n# async def 内才能使用 await；await 只能用于 Awaitable 对象",
        "framework": "python-stdlib",
    },
    {
        "api_name": "contextmanager (上下文管理器)",
        "signature": "@contextmanager / @asynccontextmanager  // 将生成器转为上下文管理器",
        "import_statement": "from contextlib import contextmanager, asynccontextmanager",
        "example": "from contextlib import asynccontextmanager\n\n@asynccontextmanager\nasync def db_session():\n    session = async_sessionmaker(engine)()\n    try:\n        yield session\n        await session.commit()\n    except Exception:\n        await session.rollback()\n        raise\n    finally:\n        await session.close()\n# yield 前 = __enter__，yield 后 = __exit__；异常自动回滚",
        "framework": "python-stdlib",
    },
    {
        "api_name": "logging (Python 标准日志)",
        "signature": "logging.getLogger(name) / logger.info/debug/warning/error/exception(...)",
        "import_statement": "import logging\nlogger = logging.getLogger(__name__)",
        "example": "logger = logging.getLogger(__name__)\n\nasync def process_order(order_id: int):\n    logger.info('开始处理订单', extra={'order_id': order_id})\n    try:\n        await do_process(order_id)\n    except Exception:\n        logger.exception('订单处理失败')  # 自动附带 traceback\n        raise\n# 生产环境建议使用 structlog 进行结构化日志",
        "framework": "python-stdlib",
    },

    # ---- Java (Spring Boot 3.x) ----
    {
        "api_name": "@SpringBootApplication",
        "signature": "@SpringBootApplication  // 组合 @Configuration + @EnableAutoConfiguration + @ComponentScan",
        "import_statement": "import org.springframework.boot.autoconfigure.SpringBootApplication;",
        "example": "@SpringBootApplication\npublic class Application {\n    public static void main(String[] args) {\n        SpringApplication.run(Application.class, args);\n    }\n}\n// 必须放在根包下，确保组件扫描覆盖所有子包",
        "framework": "spring-boot",
    },
    {
        "api_name": "@RestController",
        "signature": "@RestController  // 组合 @Controller + @ResponseBody，自动序列化返回值为 JSON",
        "import_statement": "import org.springframework.web.bind.annotation.RestController;",
        "example": "@RestController\n@RequestMapping(\"/api/users\")\npublic class UserController {\n    @GetMapping(\"/{id}\")\n    public User getById(@PathVariable Long id) { ... }\n}",
        "framework": "spring-boot",
    },
    {
        "api_name": "@GetMapping / @PostMapping / @PutMapping / @DeleteMapping",
        "signature": "@GetMapping(path, produces, consumes) / @PostMapping / @PutMapping / @DeleteMapping",
        "import_statement": "import org.springframework.web.bind.annotation.*;",
        "example": "@GetMapping(\"/{id}\")\npublic ResponseEntity<UserDto> getById(@PathVariable Long id) {\n    return userService.findById(id)\n        .map(ResponseEntity::ok)\n        .orElse(ResponseEntity.notFound().build());\n}\n\n@PostMapping\npublic ResponseEntity<UserDto> create(@Valid @RequestBody CreateUserRequest req) {\n    return ResponseEntity.status(HttpStatus.CREATED).body(userService.create(req));\n}",
        "framework": "spring-boot",
    },
    {
        "api_name": "@RequestParam / @PathVariable / @RequestBody",
        "signature": "@RequestParam(name, required, defaultValue) / @PathVariable / @RequestBody",
        "import_statement": "import org.springframework.web.bind.annotation.*;",
        "example": "@GetMapping\npublic Page<UserDto> search(\n    @RequestParam(required = false) String keyword,\n    @RequestParam(defaultValue = \"0\") int page,\n    @RequestParam(defaultValue = \"20\") int size,\n) { ... }\n// required=false 表示可选参数；defaultValue 可省略 required",
        "framework": "spring-boot",
    },
    {
        "api_name": "@Autowired",
        "signature": "@Autowired  // 构造器注入（推荐）/ 字段注入 / Setter 注入",
        "import_statement": "import org.springframework.beans.factory.annotation.Autowired;",
        "example": "@RestController\npublic class UserController {\n    private final UserService userService;\n\n    // 构造器注入 —— @Autowired 可省略（Spring 4.3+ 单构造器自动注入）\n    public UserController(UserService userService) {\n        this.userService = userService;\n    }\n}\n# 构造器注入优于字段注入：不可变、易测试、避免循环依赖",
        "framework": "spring-boot",
    },
    {
        "api_name": "@Service",
        "signature": "@Service  // 标记业务逻辑层 Bean，语义同 @Component",
        "import_statement": "import org.springframework.stereotype.Service;",
        "example": "@Service\n@Transactional(readOnly = true)\npublic class UserService {\n    private final UserRepository userRepository;\n\n    @Transactional\n    public UserDto create(CreateUserRequest req) {\n        User user = User.builder().name(req.name()).email(req.email()).build();\n        return UserDto.from(userRepository.save(user));\n    }\n}",
        "framework": "spring-boot",
    },
    {
        "api_name": "@Repository",
        "signature": "@Repository  // 标记数据访问层 Bean，自动翻译 JDBC 异常为 DataAccessException",
        "import_statement": "import org.springframework.stereotype.Repository;",
        "example": "@Repository\npublic interface UserRepository extends JpaRepository<User, Long> {\n    Optional<User> findByEmail(String email);\n\n    @Query(\"SELECT u FROM User u WHERE u.isActive = true ORDER BY u.createdAt DESC\")\n    Page<User> findActiveUsers(Pageable pageable);\n}\n// Spring Data JPA 根据方法名自动生成查询；@Query 用于复杂 SQL",
        "framework": "spring-boot",
    },
    {
        "api_name": "@Transactional",
        "signature": "@Transactional(propagation, isolation, readOnly, timeout, rollbackFor)  // 声明式事务",
        "import_statement": "import org.springframework.transaction.annotation.Transactional;",
        "example": "@Service\npublic class OrderService {\n    @Transactional(rollbackFor = Exception.class)\n    public Order createOrder(CreateOrderRequest req) {\n        orderRepository.save(order);\n        inventoryService.deduct(req.items());  // 同个事务\n        paymentService.charge(req.payment());  // 同个事务\n        return order;\n    }\n}\n# rollbackFor = Exception.class 确保 checked exception 也回滚",
        "framework": "spring-boot",
    },
    {
        "api_name": "@Entity + @Id + @GeneratedValue (JPA)",
        "signature": "@Entity / @Id / @GeneratedValue(strategy = GenerationType.IDENTITY | SEQUENCE | AUTO)",
        "import_statement": "import jakarta.persistence.*;",
        "example": "@Entity\n@Table(name = \"users\")\npublic class User {\n    @Id\n    @GeneratedValue(strategy = GenerationType.IDENTITY)\n    private Long id;\n\n    @Column(nullable = false, length = 50)\n    private String name;\n\n    @Column(unique = true, nullable = false)\n    private String email;\n\n    @CreationTimestamp\n    private LocalDateTime createdAt;\n}\n# IDENTITY 依赖数据库自增；SEQUENCE 需要 @SequenceGenerator (PostgreSQL 推荐)",
        "framework": "jpa",
    },
    {
        "api_name": "@OneToMany / @ManyToOne (JPA 关联)",
        "signature": "@OneToMany(mappedBy, cascade, fetch, orphanRemoval) / @ManyToOne / @ManyToMany",
        "import_statement": "import jakarta.persistence.*;",
        "example": "@Entity\npublic class User {\n    @OneToMany(mappedBy = \"author\", cascade = CascadeType.ALL, orphanRemoval = true)\n    private List<Post> posts = new ArrayList<>();\n}\n\n@Entity\npublic class Post {\n    @ManyToOne(fetch = FetchType.LAZY)\n    @JoinColumn(name = \"author_id\")\n    private User author;\n}\n# mappedBy 表示关联由对方维护；LAZY 避免 N+1 查询",
        "framework": "jpa",
    },
    {
        "api_name": "JpaRepository",
        "signature": "interface JpaRepository<T, ID> extends ListCrudRepository<T, ID>, ListPagingAndSortingRepository<T, ID>",
        "import_statement": "import org.springframework.data.jpa.repository.JpaRepository;",
        "example": "public interface UserRepository extends JpaRepository<User, Long> {\n    // Spring Data 3.x 内置方法：findAll / findById / save / deleteById / count\n    Optional<User> findByEmailIgnoreCase(String email);\n    List<User> findByAgeGreaterThanAndIsActiveTrue(int age);\n    boolean existsByEmail(String email);\n}\n# 方法命名规则：findBy + 属性 + 操作符(And/Or/GreaterThan/Like/In/OrderBy)",
        "framework": "jpa",
    },
    {
        "api_name": "@Valid + @Validated (参数校验)",
        "signature": "@Valid (Jakarta) / @Validated (Spring)  // 触发 Bean Validation",
        "import_statement": "import jakarta.validation.Valid;\nimport org.springframework.validation.annotation.Validated;",
        "example": "@PostMapping\npublic ResponseEntity<UserDto> create(@Valid @RequestBody CreateUserRequest req) {\n    // 校验失败抛 MethodArgumentNotValidException → 全局异常处理器返回 400\n    return ResponseEntity.ok(userService.create(req));\n}\n\npublic record CreateUserRequest(\n    @NotBlank(message = \"姓名不能为空\") String name,\n    @Email(message = \"邮箱格式不正确\") String email,\n    @Min(value = 0, message = \"年龄不能为负数\") @Max(150) int age\n) {}",
        "framework": "spring-boot",
    },
    {
        "api_name": "@NotNull / @NotBlank / @NotEmpty",
        "signature": "@NotNull (不为 null) / @NotBlank (不为 null 且 trim 后长度>0) / @NotEmpty (不为 null 且不为空集合/字符串)",
        "import_statement": "import jakarta.validation.constraints.*;",
        "example": "public record CreateOrderRequest(\n    @NotNull(message = \"商品列表不能为null\") List<OrderItem> items,\n    @NotBlank(message = \"收货地址不能为空\") String address,\n    @NotEmpty(message = \"至少需要一个商品\") List<@Valid OrderItem> items\n) {}\n# @NotBlank 仅用于 String；@NotEmpty 用于 String/Collection/Map/Array",
        "framework": "spring-boot",
    },
    {
        "api_name": "@RestControllerAdvice + @ExceptionHandler",
        "signature": "@RestControllerAdvice  // 全局异常处理，@ResponseBody + @ControllerAdvice",
        "import_statement": "import org.springframework.web.bind.annotation.RestControllerAdvice;\nimport org.springframework.web.bind.annotation.ExceptionHandler;",
        "example": "@RestControllerAdvice\npublic class GlobalExceptionHandler {\n    @ExceptionHandler(MethodArgumentNotValidException.class)\n    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException ex) {\n        String msg = ex.getBindingResult().getFieldErrors().stream()\n            .map(e -> e.getField() + \": \" + e.getDefaultMessage())\n            .collect(Collectors.joining(\"; \"));\n        return ResponseEntity.badRequest().body(new ErrorResponse(400, msg));\n    }\n\n    @ExceptionHandler(Exception.class)\n    public ResponseEntity<ErrorResponse> handleGeneral(Exception ex) {\n        return ResponseEntity.status(500).body(new ErrorResponse(500, \"服务器内部错误\"));\n    }\n}",
        "framework": "spring-boot",
    },
    {
        "api_name": "@Configuration + @Bean",
        "signature": "@Configuration / @Bean  // Java-based 配置，替代 XML",
        "import_statement": "import org.springframework.context.annotation.Bean;\nimport org.springframework.context.annotation.Configuration;",
        "example": "@Configuration\npublic class AppConfig {\n    @Bean\n    public RestClient restClient() {\n        return RestClient.builder()\n            .baseUrl(\"https://api.example.com\")\n            .defaultHeader(\"Authorization\", \"Bearer \" + apiKey)\n            .build();\n    }\n}\n# @Bean 方法名默认是 Bean 名称；@Configuration 确保单例",
        "framework": "spring-boot",
    },
    {
        "api_name": "@Value + @ConfigurationProperties",
        "signature": "@Value(\"${property.name:default}\") / @ConfigurationProperties(prefix)",
        "import_statement": "import org.springframework.beans.factory.annotation.Value;\nimport org.springframework.boot.context.properties.ConfigurationProperties;",
        "example": "// 简单注入\n@Value(\"${app.jwt.secret}\") private String jwtSecret;\n@Value(\"${app.jwt.expiration:3600}\") private long expiration;  // :3600 是默认值\n\n// 批量绑定（推荐）\n@ConfigurationProperties(prefix = \"app.jwt\")\npublic record JwtProperties(String secret, long expiration, String issuer) {}",
        "framework": "spring-boot",
    },
    {
        "api_name": "@SpringBootTest / @WebMvcTest / @DataJpaTest",
        "signature": "@SpringBootTest(webEnvironment) / @WebMvcTest(controllers) / @DataJpaTest",
        "import_statement": "import org.springframework.boot.test.context.SpringBootTest;",
        "example": "// 集成测试\n@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)\nclass UserIntegrationTest { ... }\n\n// Controller 层测试（轻量）\n@WebMvcTest(UserController.class)\nclass UserControllerTest {\n    @Autowired private MockMvc mockMvc;\n    @MockBean private UserService userService;\n}\n\n// JPA 层测试（自动回滚）\n@DataJpaTest\nclass UserRepositoryTest { @Autowired private UserRepository repo; }",
        "framework": "spring-boot",
    },
    {
        "api_name": "@MockBean + MockMvc",
        "signature": "@MockBean  // 替换 Spring 容器中的 Bean 为 Mockito mock",
        "import_statement": "import org.springframework.boot.test.mock.mockito.MockBean;\nimport static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;",
        "example": "@WebMvcTest(UserController.class)\nclass UserControllerTest {\n    @Autowired private MockMvc mockMvc;\n    @MockBean private UserService userService;\n\n    @Test\n    void shouldReturnUser() throws Exception {\n        when(userService.findById(1L)).thenReturn(Optional.of(mockUser));\n\n        mockMvc.perform(get(\"/api/users/1\"))\n            .andExpect(status().isOk())\n            .andExpect(jsonPath(\"$.name\").value(\"Alice\"));\n    }\n}",
        "framework": "spring-boot",
    },

    # ---- Go (Gin / net/http) ----
    {
        "api_name": "gin.Default() / gin.New()",
        "signature": "func Default() *Engine  // 带 Logger + Recovery 中间件\nfunc New() *Engine         // 无默认中间件，干净启动",
        "import_statement": "import \"github.com/gin-gonic/gin\"",
        "example": "r := gin.Default()\nr.GET(\"/ping\", func(c *gin.Context) {\n    c.JSON(200, gin.H{\"message\": \"pong\"})\n})\nr.Run(\":8080\")\n// Default() 自带 Logger 和 Recovery 中间件",
        "framework": "gin",
    },
    {
        "api_name": "router.GET / POST / PUT / DELETE / PATCH",
        "signature": "func (group *RouterGroup) GET(relativePath string, handlers ...HandlerFunc) IRoutes",
        "import_statement": "import \"github.com/gin-gonic/gin\"",
        "example": "r := gin.Default()\nr.GET(\"/users/:id\", getUser)\nr.POST(\"/users\", createUser)\nr.PUT(\"/users/:id\", updateUser)\nr.DELETE(\"/users/:id\", deleteUser)\n// 支持路径参数 :id 和通配符 *filepath",
        "framework": "gin",
    },
    {
        "api_name": "c.JSON() / c.XML() / c.String()",
        "signature": "func (c *Context) JSON(code int, obj any)  // 序列化并设置 Content-Type",
        "import_statement": "// Gin Context 方法，无需单独 import",
        "example": "func getUser(c *gin.Context) {\n    id := c.Param(\"id\")\n    user, err := service.FindByID(id)\n    if err != nil {\n        c.JSON(404, gin.H{\"error\": \"用户不存在\"})\n        return\n    }\n    c.JSON(200, user)\n}\n// gin.H 是 map[string]any 的别名",
        "framework": "gin",
    },
    {
        "api_name": "c.BindJSON() / c.ShouldBind() / c.ShouldBindJSON()",
        "signature": "func (c *Context) BindJSON(obj any) error           // 失败自动 400\nfunc (c *Context) ShouldBindJSON(obj any) error     // 失败不自动响应",
        "import_statement": "// Gin Context 方法",
        "example": "type CreateUserReq struct {\n    Name  string `json:\"name\" binding:\"required,min=1,max=50\"`\n    Email string `json:\"email\" binding:\"required,email\"`\n}\n\nfunc createUser(c *gin.Context) {\n    var req CreateUserReq\n    if err := c.ShouldBindJSON(&req); err != nil {\n        c.JSON(400, gin.H{\"error\": err.Error()})\n        return\n    }\n    // BindJSON 失败自动返回 400；ShouldBindJSON 手动处理\n}",
        "framework": "gin",
    },
    {
        "api_name": "c.Param() / c.Query() / c.DefaultQuery()",
        "signature": "func (c *Context) Param(key string) string\nfunc (c *Context) Query(key string) string\nfunc (c *Context) DefaultQuery(key, defaultValue string) string",
        "import_statement": "// Gin Context 方法",
        "example": "func getUser(c *gin.Context) {\n    id := c.Param(\"id\")           // /users/:id → /users/42 → \"42\"\n    page := c.DefaultQuery(\"page\", \"1\")\n    keyword := c.Query(\"q\")\n    c.JSON(200, gin.H{\"id\": id, \"page\": page, \"q\": keyword})\n}",
        "framework": "gin",
    },
    {
        "api_name": "Gin middleware (c.Next / c.Abort)",
        "signature": "func (c *Context) Next()     // 执行后续 handler\nfunc (c *Context) Abort()   // 阻止后续 handler 执行",
        "import_statement": "// Gin Context 方法",
        "example": "func AuthMiddleware() gin.HandlerFunc {\n    return func(c *gin.Context) {\n        token := c.GetHeader(\"Authorization\")\n        if token == \"\" {\n            c.JSON(401, gin.H{\"error\": \"未登录\"})\n            c.Abort()  // 阻止后续 handler\n            return\n        }\n        c.Set(\"user_id\", parseToken(token))\n        c.Next()  // 执行下一个 handler\n    }\n}\n// c.Abort() 后必须 return，否则会继续执行当前函数",
        "framework": "gin",
    },
    {
        "api_name": "gin.Recovery() + gin.Logger()",
        "signature": "func Recovery() HandlerFunc  // panic 恢复中间件\nfunc Logger() HandlerFunc     // 请求日志中间件",
        "import_statement": "// gin.Default() 已包含，手动使用：\nr := gin.New()\nr.Use(gin.Logger(), gin.Recovery())",
        "example": "// Recovery 捕获 panic 返回 500 而非 crash\n// Logger 输出格式：[GIN] 2024/01/01 - 12:00:00 | 200 | 1.234ms | GET /api/users",
        "framework": "gin",
    },
    {
        "api_name": "http.HandleFunc + http.ListenAndServe (标准库)",
        "signature": "func HandleFunc(pattern string, handler func(ResponseWriter, *Request))\nfunc ListenAndServe(addr string, handler Handler) error",
        "import_statement": "import \"net/http\"",
        "example": "func main() {\n    http.HandleFunc(\"/hello\", func(w http.ResponseWriter, r *http.Request) {\n        fmt.Fprintf(w, \"Hello, %s!\", r.URL.Query().Get(\"name\"))\n    })\n    http.ListenAndServe(\":8080\", nil)\n}\n# 标准库 net/http 无需第三方依赖，适合简单 API",
        "framework": "net-http",
    },
    {
        "api_name": "http.ResponseWriter + http.Request",
        "signature": "type ResponseWriter interface { Header() Header; Write([]byte) (int, error); WriteHeader(statusCode int) }\ntype Request struct { Method, URL, Header, Body, ... }",
        "import_statement": "import \"net/http\"",
        "example": "func handler(w http.ResponseWriter, r *http.Request) {\n    // 读取请求\n    query := r.URL.Query()\n    body, _ := io.ReadAll(r.Body)\n    defer r.Body.Close()\n\n    // 设置响应\n    w.Header().Set(\"Content-Type\", \"application/json\")\n    w.WriteHeader(http.StatusOK)\n    w.Write([]byte(`{\"status\": \"ok\"}`))\n}\n# WriteHeader 必须在 Write 之前调用；Header().Set 必须在 WriteHeader 之前",
        "framework": "net-http",
    },
    {
        "api_name": "http.ServeMux (Go 1.22+ 路由)",
        "signature": "type ServeMux  // Go 1.22+ 支持 method + path 模式",
        "import_statement": "import \"net/http\"",
        "example": "mux := http.NewServeMux()\nmux.HandleFunc(\"GET /users/{id}\", func(w http.ResponseWriter, r *http.Request) {\n    id := r.PathValue(\"id\")  // Go 1.22+\n    fmt.Fprintf(w, \"User: %s\", id)\n})\nmux.HandleFunc(\"POST /users\", createUser)\nhttp.ListenAndServe(\":8080\", mux)",
        "framework": "net-http",
    },
    {
        "api_name": "database/sql (Open / Query / QueryRow / Scan)",
        "signature": "func Open(driverName, dataSourceName string) (*DB, error)\nfunc (db *DB) Query(query string, args ...any) (*Rows, error)\nfunc (db *DB) QueryRow(query string, args ...any) *Row",
        "import_statement": "import (\n    \"database/sql\"\n    _ \"github.com/lib/pq\"  // PostgreSQL driver\n)",
        "example": "db, err := sql.Open(\"postgres\", \"postgres://user:pass@localhost/db?sslmode=disable\")\ndb.SetMaxOpenConns(25)\ndb.SetMaxIdleConns(5)\ndb.SetConnMaxLifetime(5 * time.Minute)\n\nrow := db.QueryRow(\"SELECT name, email FROM users WHERE id = $1\", id)\nvar name, email string\nif err := row.Scan(&name, &email); err != nil {\n    if errors.Is(err, sql.ErrNoRows) {\n        // 处理未找到\n    }\n}",
        "framework": "go-stdlib",
    },
    {
        "api_name": "sqlx (StructScan / NamedExec / Get / Select)",
        "signature": "func (db *DB) Get(dest any, query string, args ...any) error\nfunc (db *DB) Select(dest any, query string, args ...any) error",
        "import_statement": "import \"github.com/jmoiron/sqlx\"",
        "example": "type User struct {\n    ID    int    `db:\"id\"`\n    Name  string `db:\"name\"`\n    Email string `db:\"email\"`\n}\n\nvar users []User\nerr := db.Select(&users, \"SELECT id, name, email FROM users WHERE is_active = $1\", true)\n\nvar user User\nerr = db.Get(&user, \"SELECT * FROM users WHERE id = $1\", id)\n// sqlx 自动将列映射到 struct 字段",
        "framework": "go-stdlib",
    },
    {
        "api_name": "context.WithTimeout / WithCancel / WithValue",
        "signature": "func WithTimeout(parent Context, timeout time.Duration) (Context, CancelFunc)\nfunc WithCancel(parent Context) (Context, CancelFunc)",
        "import_statement": "import \"context\"",
        "example": "func fetchUser(ctx context.Context, id string) (*User, error) {\n    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)\n    defer cancel()  // 避免资源泄漏\n\n    // 将 ctx 传递给 DB/HTTP 调用\n    row := db.QueryRowContext(ctx, \"SELECT ... WHERE id = $1\", id)\n    ...\n}",
        "framework": "go-stdlib",
    },
    {
        "api_name": "goroutine + WaitGroup",
        "signature": "go func()  // 启动 goroutine\nvar wg sync.WaitGroup  // 等待一组 goroutine 完成",
        "import_statement": "import \"sync\"",
        "example": "func fetchAll(userIDs []int) ([]User, error) {\n    var (\n        wg    sync.WaitGroup\n        mu    sync.Mutex\n        users []User\n    )\n    for _, id := range userIDs {\n        wg.Add(1)\n        go func(id int) {\n            defer wg.Done()\n            user, _ := fetchUser(id)\n            mu.Lock()\n            users = append(users, user)\n            mu.Unlock()\n        }(id)\n    }\n    wg.Wait()\n    return users, nil\n}\n# 注意闭包变量捕获；用 errgroup 可简化错误传播",
        "framework": "go-stdlib",
    },
    {
        "api_name": "defer (延迟执行)",
        "signature": "defer funcCall(args)  // 函数返回前执行，LIFO 顺序",
        "import_statement": "# Go 关键字，无需 import",
        "example": "func readFile(path string) ([]byte, error) {\n    f, err := os.Open(path)\n    if err != nil {\n        return nil, err\n    }\n    defer f.Close()  // 保证文件关闭，无论函数如何返回\n\n    return io.ReadAll(f)\n}\n# defer 参数在声明时求值；多个 defer 按 LIFO 执行",
        "framework": "go-stdlib",
    },
    {
        "api_name": "errors.Is / errors.As / errors.Join",
        "signature": "func Is(err, target error) bool     // 检查错误链中是否包含 target\nfunc As(err error, target any) bool   // 提取错误链中特定类型的 error\nfunc Join(errs ...error) error        // Go 1.20+ 合并多个错误",
        "import_statement": "import \"errors\"",
        "example": "if errors.Is(err, sql.ErrNoRows) {\n    return nil, ErrNotFound\n}\n\nvar valErr *validator.ValidationErrors\nif errors.As(err, &valErr) {\n    // 处理校验错误\n}\n\nreturn errors.Join(err1, err2)  // 组合多个错误",
        "framework": "go-stdlib",
    },
    {
        "api_name": "encoding/json (Marshal / Unmarshal)",
        "signature": "func Marshal(v any) ([]byte, error)\nfunc Unmarshal(data []byte, v any) error",
        "import_statement": "import \"encoding/json\"",
        "example": "type User struct {\n    Name  string `json:\"name\"`\n    Email string `json:\"email,omitempty\"`  // 空值省略\n    Age   int    `json:\"-\"`                 // 忽略字段\n}\n\n// 序列化\nb, _ := json.Marshal(user)\n\n// 反序列化\nvar u User\njson.Unmarshal([]byte(`{\"name\":\"Alice\",\"email\":\"alice@example.com\"}`), &u)",
        "framework": "go-stdlib",
    },

    # ---- Node.js (Express / NestJS) ----
    {
        "api_name": "express() 应用创建",
        "signature": "const app = express()  // 创建 Express 应用实例",
        "import_statement": "const express = require('express');  // CommonJS\nimport express from 'express';      // ES Module",
        "example": "import express from 'express';\nconst app = express();\napp.use(express.json());  // 解析 JSON body\napp.use(express.urlencoded({ extended: true }));\n\napp.listen(3000, () => console.log('Server running on :3000'));",
        "framework": "express",
    },
    {
        "api_name": "app.get / app.post / app.put / app.delete",
        "signature": "app.METHOD(path, ...handlers)  // 路由定义，支持多个中间件",
        "import_statement": "// express 实例方法",
        "example": "app.get('/users/:id', async (req, res) => {\n    const user = await UserService.findById(req.params.id);\n    if (!user) return res.status(404).json({ error: '用户不存在' });\n    res.json(user);\n});\n\napp.post('/users', validate(createUserSchema), async (req, res) => {\n    const user = await UserService.create(req.body);\n    res.status(201).json(user);\n});",
        "framework": "express",
    },
    {
        "api_name": "req.params / req.query / req.body",
        "signature": "req.params   // 路由参数 { id: '42' }\nreq.query    // 查询字符串 { page: '1', q: 'search' }\nreq.body     // 请求体（需 express.json() 中间件）",
        "import_statement": "// Request 对象属性",
        "example": "app.get('/users/:id/posts', async (req, res) => {\n    const { id } = req.params;\n    const { page = 1, limit = 20 } = req.query;\n    const posts = await PostService.findByUser(id, +page, +limit);\n    res.json(posts);\n});\n# req.query 的值都是 string，需手动转换类型",
        "framework": "express",
    },
    {
        "api_name": "res.json / res.status / res.send",
        "signature": "res.json(body)       // 发送 JSON 响应\nres.status(code)     // 设置状态码（链式调用）\nres.send(body)       // 发送任意类型响应",
        "import_statement": "// Response 对象方法",
        "example": "app.get('/health', (req, res) => {\n    res.status(200).json({ status: 'ok', uptime: process.uptime() });\n});\n\napp.use((err, req, res, next) => {\n    console.error(err);\n    res.status(err.status || 500).json({ error: err.message });\n});\n# 错误处理中间件必须有 4 个参数 (err, req, res, next)",
        "framework": "express",
    },
    {
        "api_name": "Express Router() 模块化路由",
        "signature": "const router = express.Router()  // 创建模块化路由",
        "import_statement": "import { Router } from 'express';",
        "example": "// routes/users.ts\nimport { Router } from 'express';\nconst router = Router();\n\nrouter.get('/', UserController.list);\nrouter.get('/:id', UserController.getById);\nrouter.post('/', validate(createUserSchema), UserController.create);\n\nexport default router;\n\n// app.ts\nimport usersRouter from './routes/users';\napp.use('/api/users', usersRouter);",
        "framework": "express",
    },
    {
        "api_name": "@Module (NestJS 模块)",
        "signature": "@Module({ imports, controllers, providers, exports })  // 定义功能模块",
        "import_statement": "import { Module } from '@nestjs/common';",
        "example": "@Module({\n    imports: [TypeOrmModule.forFeature([User])],\n    controllers: [UserController],\n    providers: [UserService],\n    exports: [UserService],  // 导出给其他模块使用\n})\nexport class UserModule {}",
        "framework": "nestjs",
    },
    {
        "api_name": "@Controller + @Get/@Post (NestJS)",
        "signature": "@Controller(prefix)  // 定义控制器路由前缀",
        "import_statement": "import { Controller, Get, Post, Body, Param, Query } from '@nestjs/common';",
        "example": "@Controller('users')\nexport class UserController {\n    constructor(private readonly userService: UserService) {}\n\n    @Get(':id')\n    async findOne(@Param('id') id: string): Promise<User> {\n        return this.userService.findById(id);\n    }\n\n    @Post()\n    async create(@Body() dto: CreateUserDto): Promise<User> {\n        return this.userService.create(dto);\n    }\n}",
        "framework": "nestjs",
    },
    {
        "api_name": "@Injectable + @Inject (NestJS 依赖注入)",
        "signature": "@Injectable()  // 标记为可注入的 Provider",
        "import_statement": "import { Injectable, Inject } from '@nestjs/common';",
        "example": "@Injectable()\nexport class UserService {\n    constructor(\n        @InjectRepository(User)\n        private readonly userRepo: Repository<User>,\n    ) {}\n\n    async findById(id: string): Promise<User> {\n        return this.userRepo.findOne({ where: { id } });\n    }\n}",
        "framework": "nestjs",
    },
    {
        "api_name": "@UseGuards / @UsePipes (NestJS)",
        "signature": "@UseGuards(...guards)  // 应用 Guard（认证/授权）\n@UsePipes(...pipes)    // 应用 Pipe（校验/转换）",
        "import_statement": "import { UseGuards, UsePipes, ValidationPipe } from '@nestjs/common';",
        "example": "@Controller('users')\n@UseGuards(JwtAuthGuard)  // 全局 Guard\n@UsePipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true }))\nexport class UserController {\n    @Get('profile')\n    getProfile(@Req() req) {\n        return this.userService.findById(req.user.id);\n    }\n}",
        "framework": "nestjs",
    },
    {
        "api_name": "PrismaClient (Prisma ORM)",
        "signature": "const prisma = new PrismaClient()  // 数据库客户端",
        "import_statement": "import { PrismaClient } from '@prisma/client';",
        "example": "const users = await prisma.user.findMany({\n    where: { isActive: true },\n    include: { posts: true },\n    orderBy: { createdAt: 'desc' },\n    skip: 0,\n    take: 20,\n});\n\nconst user = await prisma.user.create({\n    data: { name: 'Alice', email: 'alice@example.com' },\n});",
        "framework": "nestjs",
    },

    # ---- Rust (Actix-web / Axum) ----
    {
        "api_name": "App::new() + route (Actix-web)",
        "signature": "App::new().route(path, web::get().to(handler))  // 构建路由",
        "import_statement": "use actix_web::{web, App, HttpServer, HttpResponse};",
        "example": "#[actix_web::main]\nasync fn main() -> std::io::Result<()> {\n    HttpServer::new(|| {\n        App::new()\n            .route(\"/health\", web::get().to(|| async { HttpResponse::Ok().json(\"ok\") }))\n            .route(\"/users/{id}\", web::get().to(get_user))\n    })\n    .bind(\"127.0.0.1:8080\")?\n    .run()\n    .await\n}",
        "framework": "actix-web",
    },
    {
        "api_name": "web::Json<T> (Actix-web 请求体提取器)",
        "signature": "web::Json<T>  // 自动反序列化 JSON body 到 T",
        "import_statement": "use actix_web::web;",
        "example": "use serde::{Deserialize, Serialize};\n\n#[derive(Deserialize)]\nstruct CreateUser {\n    name: String,\n    email: String,\n}\n\nasync fn create_user(body: web::Json<CreateUser>) -> HttpResponse {\n    HttpResponse::Created().json(serde_json::json!({\"name\": body.name}))\n}",
        "framework": "actix-web",
    },
    {
        "api_name": "web::Path<T> / web::Query<T> (Actix-web 提取器)",
        "signature": "web::Path<T>  // 路径参数\nweb::Query<T> // 查询参数",
        "import_statement": "use actix_web::web;",
        "example": "#[derive(Deserialize)]\nstruct UserParams { id: i64 }\n\nasync fn get_user(path: web::Path<UserParams>) -> HttpResponse {\n    let id = path.id;\n    ...\n}\n\n#[derive(Deserialize)]\nstruct ListQuery { page: Option<u32>, size: Option<u32> }\n\nasync fn list_users(query: web::Query<ListQuery>) -> HttpResponse { ... }",
        "framework": "actix-web",
    },
    {
        "api_name": "web::Data<T> (Actix-web 共享状态)",
        "signature": "web::Data<T>  // 线程安全的共享状态（Arc<T> 包装）",
        "import_statement": "use actix_web::web;",
        "example": "struct AppState {\n    db: sqlx::PgPool,\n}\n\nlet pool = PgPoolOptions::new().connect(&db_url).await?;\nHttpServer::new(move || {\n    App::new()\n        .app_data(web::Data::new(AppState { db: pool.clone() }))\n        .route(\"/users\", web::get().to(list_users))\n})\n\nasync fn list_users(state: web::Data<AppState>) -> HttpResponse {\n    let users = sqlx::query_as!(User, \"SELECT * FROM users\").fetch_all(&state.db).await?;\n    HttpResponse::Ok().json(users)\n}",
        "framework": "actix-web",
    },
    {
        "api_name": "Router::new() + .route() (Axum)",
        "signature": "Router::new().route(path, method(handler))  // Axum 路由构建",
        "import_statement": "use axum::{Router, routing::get, extract::{Path, Query, State, Json}};",
        "example": "let app = Router::new()\n    .route(\"/health\", get(health_check))\n    .route(\"/users/:id\", get(get_user).post(create_user))\n    .with_state(shared_state);\n\nlet listener = tokio::net::TcpListener::bind(\"0.0.0.0:8080\").await?;\naxum::serve(listener, app).await?;",
        "framework": "axum",
    },
    {
        "api_name": "State / Json / Path (Axum 提取器)",
        "signature": "State(app_state): State<AppState>  // 共享状态提取器\nJson(body): Json<T>              // JSON body 提取器\nPath(params): Path<P>            // 路径参数提取器",
        "import_statement": "use axum::{extract::{State, Json, Path, Query}, response::IntoResponse};",
        "example": "async fn create_user(\n    State(state): State<AppState>,\n    Json(body): Json<CreateUser>,\n) -> impl IntoResponse {\n    let user = sqlx::query_as!(User, \"INSERT INTO users ...\")\n        .fetch_one(&state.db).await?;\n    (StatusCode::CREATED, Json(user))\n}",
        "framework": "axum",
    },
    {
        "api_name": "#[derive(Serialize, Deserialize)] (Serde)",
        "signature": "// 自动实现序列化/反序列化 trait",
        "import_statement": "use serde::{Deserialize, Serialize};",
        "example": "#[derive(Debug, Clone, Serialize, Deserialize)]\nstruct User {\n    pub id: i64,\n    pub name: String,\n    #[serde(rename = \"emailAddress\")]  // 自定义 JSON 字段名\n    pub email: String,\n    #[serde(skip_serializing_if = \"Option::is_none\")]\n    pub bio: Option<String>,\n    #[serde(default)]  // 缺失时用 Default::default()\n    pub is_active: bool,\n}",
        "framework": "rust-stdlib",
    },
    {
        "api_name": "sqlx::query_as! / fetch_all (SQLx)",
        "signature": "sqlx::query_as!(Struct, \"SQL\", params...)  // 编译时检查 SQL 语法",
        "import_statement": "use sqlx::postgres::PgPoolOptions;",
        "example": "let pool = PgPoolOptions::new()\n    .max_connections(20)\n    .connect(&database_url).await?;\n\nlet users = sqlx::query_as!(User, \"SELECT id, name, email FROM users WHERE is_active = $1\", true)\n    .fetch_all(&pool).await?;\n\nlet user = sqlx::query_as!(User, \"SELECT * FROM users WHERE id = $1\", id)\n    .fetch_optional(&pool).await?;  // Option<User>",
        "framework": "rust-stdlib",
    },
    {
        "api_name": "tokio::test (异步测试)",
        "signature": "#[tokio::test]  // 标记异步测试函数",
        "import_statement": "use actix_web::test;",
        "example": "#[cfg(test)]\nmod tests {\n    use super::*;\n    use actix_web::{test, App};\n\n    #[actix_web::test]\n    async fn test_get_user() {\n        let app = test::init_service(App::new().route(\"/users/{id}\", web::get().to(get_user))).await;\n        let req = test::TestRequest::get().uri(\"/users/1\").to_request();\n        let resp = test::call_service(&app, req).await;\n        assert!(resp.status().is_success());\n    }\n}",
        "framework": "actix-web",
    },
]

# ============================================================
# Collection 2: component_library
# ============================================================
COMPONENT_LIBRARY_SEEDS = [
    {
        "component_name": "DataTable",
        "props_schema": "{ columns: { key: string; title: string; sortable?: boolean }[]; data: T[]; loading: boolean; emptyText: string }",
        "code_snippet": """<script setup lang="ts">
interface Column<T = any> { key: string; title: string; sortable?: boolean }
const props = defineProps<{ columns: Column[]; data: any[]; loading?: boolean; emptyText?: string }>()
const emit = defineEmits<{ (e: 'row-click', row: any): void; (e: 'sort', key: string, order: 'asc' | 'desc'): void }>()
const sortKey = ref(''); const sortOrder = ref<'asc' | 'desc'>('asc')
function handleSort(key: string) { sortKey.value = key; sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc'; emit('sort', key, sortOrder.value) }
</script>
<template>
  <div class="overflow-x-auto rounded-lg border">
    <table class="w-full text-left text-sm">
      <thead class="bg-gray-50 text-gray-600"><tr><th v-for="col in columns" :key="col.key" @click="col.sortable && handleSort(col.key)" class="px-4 py-3 font-medium cursor-pointer">{{ col.title }}</th></tr></thead>
      <tbody><tr v-if="loading"><td :colspan="columns.length" class="px-4 py-8 text-center text-gray-400">加载中...</td></tr><tr v-else-if="!data.length"><td :colspan="columns.length" class="px-4 py-8 text-center text-gray-400">{{ emptyText || '暂无数据' }}</td></tr><tr v-for="row in data" :key="row.id" @click="emit('row-click', row)" class="border-t hover:bg-gray-50 cursor-pointer"><td v-for="col in columns" :key="col.key" class="px-4 py-3">{{ row[col.key] }}</td></tr></tbody>
    </table>
  </div>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "SearchFilter",
        "props_schema": "{ filters: { key: string; label: string; type: 'text' | 'select' | 'date'; options?: { label: string; value: string }[] }[]; modelValue: Record<string, string> }",
        "code_snippet": """<script setup lang="ts">
interface FilterDef { key: string; label: string; type: 'text' | 'select' | 'date'; options?: { label: string; value: string }[] }
const props = defineProps<{ filters: FilterDef[]; modelValue: Record<string, string> }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: Record<string, string>): void; (e: 'search'): void; (e: 'reset'): void }>()
function update(key: string, value: string) { emit('update:modelValue', { ...props.modelValue, [key]: value }) }
</script>
<template>
  <div class="flex flex-wrap gap-3 p-4 bg-gray-50 rounded-lg">
    <template v-for="f in filters" :key="f.key">
      <input v-if="f.type === 'text'" :placeholder="f.label" :value="modelValue[f.key] || ''" @input="update(f.key, ($event.target as HTMLInputElement).value)" class="px-3 py-2 border rounded-md text-sm" />
      <select v-else-if="f.type === 'select'" :value="modelValue[f.key] || ''" @change="update(f.key, ($event.target as HTMLSelectElement).value)" class="px-3 py-2 border rounded-md text-sm"><option value="">{{ f.label }}</option><option v-for="o in f.options" :key="o.value" :value="o.value">{{ o.label }}</option></select>
    </template>
    <button @click="emit('search')" class="px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700">搜索</button>
    <button @click="emit('reset')" class="px-4 py-2 border rounded-md text-sm hover:bg-gray-100">重置</button>
  </div>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "Pagination",
        "props_schema": "{ current: number; total: number; pageSize: number; showTotal?: boolean }",
        "code_snippet": """<script setup lang="ts">
const props = withDefaults(defineProps<{ current: number; total: number; pageSize?: number; showTotal?: boolean }>(), { pageSize: 10, showTotal: true })
const emit = defineEmits<{ (e: 'change', page: number): void }>()
const totalPages = computed(() => Math.ceil(props.total / props.pageSize))
const pages = computed(() => { const p = []; const start = Math.max(1, props.current - 2); const end = Math.min(totalPages.value, props.current + 2); for (let i = start; i <= end; i++) p.push(i); return p })
</script>
<template>
  <div class="flex items-center justify-between px-4 py-3">
    <span v-if="showTotal" class="text-sm text-gray-500">共 {{ total }} 条</span>
    <div class="flex gap-1">
      <button :disabled="current <= 1" @click="emit('change', current - 1)" class="px-3 py-1 border rounded text-sm disabled:opacity-40">上一页</button>
      <button v-for="p in pages" :key="p" @click="emit('change', p)" :class="['px-3 py-1 border rounded text-sm', p === current ? 'bg-blue-600 text-white border-blue-600' : 'hover:bg-gray-50']">{{ p }}</button>
      <button :disabled="current >= totalPages" @click="emit('change', current + 1)" class="px-3 py-1 border rounded text-sm disabled:opacity-40">下一页</button>
    </div>
  </div>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "ModalDialog",
        "props_schema": "{ visible: boolean; title: string; width?: string; confirmText?: string; cancelText?: string; loading?: boolean }",
        "code_snippet": """<script setup lang="ts">
const props = withDefaults(defineProps<{ visible: boolean; title: string; width?: string; confirmText?: string; cancelText?: string; loading?: boolean }>(), { width: '520px', confirmText: '确定', cancelText: '取消' })
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'confirm'): void; (e: 'cancel'): void }>()
function close() { emit('update:visible', false); emit('cancel') }
</script>
<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-50 flex items-center justify-center">
      <div class="absolute inset-0 bg-black/40" @click="close"></div>
      <div class="relative bg-white rounded-lg shadow-xl" :style="{ width }">
        <div class="flex items-center justify-between px-6 py-4 border-b"><h3 class="text-lg font-semibold">{{ title }}</h3><button @click="close" class="text-gray-400 hover:text-gray-600 text-xl">&times;</button></div>
        <div class="px-6 py-4"><slot /></div>
        <div class="flex justify-end gap-3 px-6 py-4 border-t bg-gray-50 rounded-b-lg">
          <button @click="close" class="px-4 py-2 border rounded-md text-sm hover:bg-gray-100">{{ cancelText }}</button>
          <button @click="emit('confirm')" :disabled="loading" class="px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700 disabled:opacity-60">{{ loading ? '处理中...' : confirmText }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "CardGrid",
        "props_schema": "{ items: T[]; columns?: number; gap?: number }",
        "code_snippet": """<script setup lang="ts">
const props = withDefaults(defineProps<{ items: any[]; columns?: number; gap?: number }>(), { columns: 3, gap: 4 })
</script>
<template>
  <div :class="['grid', { 1: 'grid-cols-1', 2: 'grid-cols-1 sm:grid-cols-2', 3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3', 4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4' }[columns], `gap-${gap}`]">
    <slot v-for="(item, i) in items" :key="i" :item="item" />
  </div>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "PageHeader",
        "props_schema": "{ title: string; subtitle?: string; showBack?: boolean }",
        "code_snippet": """<script setup lang="ts">
const props = defineProps<{ title: string; subtitle?: string; showBack?: boolean }>()
const emit = defineEmits<{ (e: 'back'): void }>()
</script>
<template>
  <div class="mb-6">
    <div class="flex items-center gap-3">
      <button v-if="showBack" @click="emit('back')" class="text-gray-400 hover:text-gray-600">&larr; 返回</button>
      <h1 class="text-2xl font-bold text-gray-900">{{ title }}</h1>
    </div>
    <p v-if="subtitle" class="mt-1 text-gray-500">{{ subtitle }}</p>
  </div>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "Tabs",
        "props_schema": "{ tabs: { key: string; label: string }[]; modelValue: string }",
        "code_snippet": """<script setup lang="ts">
const props = defineProps<{ tabs: { key: string; label: string }[]; modelValue: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', key: string): void }>()
</script>
<template>
  <div class="border-b">
    <nav class="flex gap-0 -mb-px">
      <button v-for="tab in tabs" :key="tab.key" @click="emit('update:modelValue', tab.key)" :class="['px-4 py-2 text-sm font-medium border-b-2 transition-colors', modelValue === tab.key ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500 hover:text-gray-700']">{{ tab.label }}</button>
    </nav>
  </div>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "EmptyState",
        "props_schema": "{ icon?: string; title: string; description?: string; actionText?: string }",
        "code_snippet": """<script setup lang="ts">
const props = defineProps<{ icon?: string; title: string; description?: string; actionText?: string }>()
const emit = defineEmits<{ (e: 'action'): void }>()
</script>
<template>
  <div class="flex flex-col items-center justify-center py-16 text-center">
    <span class="text-5xl mb-4">{{ icon || '📭' }}</span>
    <h3 class="text-lg font-medium text-gray-900">{{ title }}</h3>
    <p v-if="description" class="mt-1 text-sm text-gray-500 max-w-sm">{{ description }}</p>
    <button v-if="actionText" @click="emit('action')" class="mt-4 px-4 py-2 bg-blue-600 text-white rounded-md text-sm hover:bg-blue-700">{{ actionText }}</button>
  </div>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "SkeletonLoader",
        "props_schema": "{ type: 'card' | 'list' | 'text'; count?: number }",
        "code_snippet": """<script setup lang="ts">
const props = withDefaults(defineProps<{ type: 'card' | 'list' | 'text'; count?: number }>(), { count: 3 })
</script>
<template>
  <div v-if="type === 'card'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
    <div v-for="i in count" :key="i" class="rounded-lg border p-4 animate-pulse"><div class="h-40 bg-gray-200 rounded mb-3" /><div class="h-4 bg-gray-200 rounded w-3/4 mb-2" /><div class="h-3 bg-gray-200 rounded w-1/2" /></div>
  </div>
  <div v-else-if="type === 'list'" class="space-y-3">
    <div v-for="i in count" :key="i" class="flex gap-3 animate-pulse"><div class="h-10 w-10 bg-gray-200 rounded-full" /><div class="flex-1"><div class="h-4 bg-gray-200 rounded w-2/3 mb-1" /><div class="h-3 bg-gray-200 rounded w-1/3" /></div></div>
  </div>
  <div v-else class="space-y-2">
    <div v-for="i in count" :key="i" class="h-4 bg-gray-200 rounded animate-pulse" :style="{ width: (80 - i * 10) + '%' }" />
  </div>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },
    {
        "component_name": "ConfirmDialog",
        "props_schema": "{ visible: boolean; title: string; message: string; type?: 'danger' | 'warning' | 'info' }",
        "code_snippet": """<script setup lang="ts">
const props = withDefaults(defineProps<{ visible: boolean; title: string; message: string; type?: 'danger' | 'warning' | 'info' }>(), { type: 'info' })
const emit = defineEmits<{ (e: 'update:visible', v: boolean): void; (e: 'confirm'): void; (e: 'cancel'): void }>()
const colors = { danger: 'bg-red-600 hover:bg-red-700', warning: 'bg-yellow-600 hover:bg-yellow-700', info: 'bg-blue-600 hover:bg-blue-700' }
</script>
<template>
  <ModalDialog :visible="visible" :title="title" @update:visible="emit('update:visible', $event)" @confirm="emit('confirm')" @cancel="emit('cancel')" :confirmText="type === 'danger' ? '确认删除' : '确认'">
    <p class="text-gray-600">{{ message }}</p>
  </ModalDialog>
</template>""",
        "framework": "vue3",
        "use_count": 1,
    },

    # ---- Python (FastAPI) ----
    {
        "component_name": "CRUDServiceBase",
        "props_schema": "{ model: type; session: AsyncSession; create_schema: BaseModel; update_schema: BaseModel }",
        "code_snippet": """class CRUDServiceBase(Generic[ModelType, CreateSchema, UpdateSchema]):
    \"\"\"通用异步 CRUD 服务基类\"\"\"
    def __init__(self, model: type[ModelType]):
        self.model = model

    async def get(self, db: AsyncSession, id: int) -> ModelType | None:
        result = await db.execute(select(self.model).where(self.model.id == id))
        return result.scalar_one_or_none()

    async def list(self, db: AsyncSession, *, skip: int = 0, limit: int = 100) -> list[ModelType]:
        result = await db.execute(select(self.model).order_by(self.model.id).offset(skip).limit(limit))
        return list(result.scalars().all())

    async def create(self, db: AsyncSession, *, obj_in: CreateSchema) -> ModelType:
        db_obj = self.model(**obj_in.model_dump())
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def update(self, db: AsyncSession, *, db_obj: ModelType, obj_in: UpdateSchema) -> ModelType:
        update_data = obj_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def delete(self, db: AsyncSession, *, id: int) -> ModelType | None:
        obj = await self.get(db, id)
        if obj:
            await db.delete(obj)
            await db.commit()
        return obj""",
        "framework": "fastapi",
        "use_count": 1,
    },
    {
        "component_name": "FastAPI Router Module",
        "props_schema": "{ prefix: str; tags: list[str]; routes: list[APIRoute] }",
        "code_snippet": """# routers/users.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.deps import get_db
from app.schemas.user import UserCreate, UserUpdate, UserOut
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["用户管理"])
user_service = UserService()

@router.get("/", response_model=list[UserOut])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await user_service.list(db, skip=skip, limit=limit)

@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = await user_service.get(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user

@router.post("/", response_model=UserOut, status_code=201)
async def create_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    return await user_service.create(db, obj_in=user_in)

@router.put("/{user_id}", response_model=UserOut)
async def update_user(user_id: int, user_in: UserUpdate, db: AsyncSession = Depends(get_db)):
    user = await user_service.get(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return await user_service.update(db, db_obj=user, obj_in=user_in)

@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    await user_service.delete(db, id=user_id)
    return None""",
        "framework": "fastapi",
        "use_count": 1,
    },
    {
        "component_name": "Pydantic RequestResponse Schema",
        "props_schema": "{ model_config: ConfigDict; fields: BaseModel fields with validation }",
        "code_snippet": """# schemas/user.py
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from datetime import datetime

class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱地址")
    is_active: bool = Field(default=True)

class UserCreate(UserBase):
    password: str = Field(..., min_length=8, description="密码（最少8位）")
    password_confirm: str = Field(..., min_length=8)

    @model_validator(mode="after")
    def check_passwords_match(self) -> "UserCreate":
        if self.password != self.password_confirm:
            raise ValueError("两次密码不一致")
        return self

class UserUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    email: EmailStr | None = None
    is_active: bool | None = None

class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime""",
        "framework": "pydantic",
        "use_count": 1,
    },
    {
        "component_name": "Database Session Dependency",
        "props_schema": "{ engine: AsyncEngine; session_factory: async_sessionmaker }",
        "code_snippet": """# deps/database.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_db() -> AsyncSession:
    \"\"\"FastAPI 依赖：每个请求获取独立数据库会话\"\"\"
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()""",
        "framework": "fastapi",
        "use_count": 1,
    },
    {
        "component_name": "JWT Auth Dependency",
        "props_schema": "{ secret_key: str; algorithm: str = 'HS256'; token_url: str = '/auth/login' }",
        "code_snippet": """# deps/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from app.core.config import settings

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    \"\"\"验证 Bearer Token 并返回当前用户\"\"\"
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="无效的认证令牌")
    except JWTError:
        raise HTTPException(status_code=401, detail="无法解析认证令牌")

    user = await user_service.get(db, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")
    return user""",
        "framework": "fastapi",
        "use_count": 1,
    },
    {
        "component_name": "PaginatedResponse",
        "props_schema": "{ items: list[T]; total: int; page: int; size: int; pages: int }",
        "code_snippet": """from pydantic import BaseModel, Field
from typing import Generic, TypeVar

T = TypeVar("T")

class PaginatedResponse(BaseModel, Generic[T]):
    \"\"\"通用分页响应\"\"\"
    items: list[T] = Field(..., description="当前页数据")
    total: int = Field(..., description="总条数")
    page: int = Field(..., description="当前页码")
    size: int = Field(..., description="每页条数")
    pages: int = Field(..., description="总页数")

    @classmethod
    def from_items(cls, items: list[T], total: int, page: int, size: int) -> "PaginatedResponse[T]":
        return cls(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=(total + size - 1) // size,
        )""",
        "framework": "fastapi",
        "use_count": 1,
    },

    # ---- Java (Spring Boot) ----
    {
        "component_name": "REST CRUD Controller (Spring Boot)",
        "props_schema": "{ entity: JPA Entity; dto: Record class; service: @Service class }",
        "code_snippet": """@RestController
@RequestMapping("/api/users")
@RequiredArgsConstructor
public class UserController {
    private final UserService userService;

    @GetMapping
    public ResponseEntity<Page<UserDto>> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size,
        @RequestParam(required = false) String keyword
    ) {
        return ResponseEntity.ok(userService.findAll(keyword, PageRequest.of(page, size)));
    }

    @GetMapping("/{id}")
    public ResponseEntity<UserDto> getById(@PathVariable Long id) {
        return userService.findById(id)
            .map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    @PostMapping
    public ResponseEntity<UserDto> create(@Valid @RequestBody CreateUserRequest req) {
        return ResponseEntity.status(HttpStatus.CREATED).body(userService.create(req));
    }

    @PutMapping("/{id}")
    public ResponseEntity<UserDto> update(@PathVariable Long id, @Valid @RequestBody UpdateUserRequest req) {
        return ResponseEntity.ok(userService.update(id, req));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        userService.delete(id);
        return ResponseEntity.noContent().build();
    }
}""",
        "framework": "spring-boot",
        "use_count": 1,
    },
    {
        "component_name": "JPA Entity with Audit",
        "props_schema": "{ @Id: Long; @CreatedDate: LocalDateTime; @LastModifiedDate: LocalDateTime }",
        "code_snippet": """@MappedSuperclass
@EntityListeners(AuditingEntityListener.class)
public abstract class BaseEntity {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @CreatedDate
    @Column(updatable = false)
    private LocalDateTime createdAt;

    @LastModifiedDate
    private LocalDateTime updatedAt;

    @Version
    private Long version;  // 乐观锁
}

@Entity
@Table(name = "users")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class User extends BaseEntity {
    @Column(nullable = false, length = 50)
    private String name;

    @Column(unique = true, nullable = false, length = 100)
    private String email;

    @Column(nullable = false)
    private String passwordHash;

    @Column(nullable = false)
    private Boolean isActive = true;
}""",
        "framework": "jpa",
        "use_count": 1,
    },
    {
        "component_name": "Service + @Transactional",
        "props_schema": "{ repository: JpaRepository; mapper: MapStruct interface }",
        "code_snippet": """@Service
@Transactional(readOnly = true)
@RequiredArgsConstructor
public class UserService {
    private final UserRepository userRepository;
    private final UserMapper userMapper;

    public Page<UserDto> findAll(String keyword, Pageable pageable) {
        Page<User> users = keyword == null
            ? userRepository.findAll(pageable)
            : userRepository.findByNameContainingIgnoreCase(keyword, pageable);
        return users.map(userMapper::toDto);
    }

    public Optional<UserDto> findById(Long id) {
        return userRepository.findById(id).map(userMapper::toDto);
    }

    @Transactional
    public UserDto create(CreateUserRequest req) {
        if (userRepository.existsByEmail(req.email())) {
            throw new BusinessException("邮箱已被使用");
        }
        User user = userMapper.toEntity(req);
        user.setPasswordHash(passwordEncoder.encode(req.password()));
        return userMapper.toDto(userRepository.save(user));
    }

    @Transactional
    public UserDto update(Long id, UpdateUserRequest req) {
        User user = userRepository.findById(id)
            .orElseThrow(() -> new NotFoundException("用户不存在"));
        userMapper.updateEntity(req, user);
        return userMapper.toDto(userRepository.save(user));
    }

    @Transactional
    public void delete(Long id) {
        if (!userRepository.existsById(id)) {
            throw new NotFoundException("用户不存在");
        }
        userRepository.deleteById(id);
    }
}""",
        "framework": "spring-boot",
        "use_count": 1,
    },
    {
        "component_name": "DTO + MapStruct Mapper",
        "props_schema": "{ entity: JPA Entity; request: Record; response: Record }",
        "code_snippet": """// Request DTOs (Java 17+ Record)
public record CreateUserRequest(
    @NotBlank String name,
    @Email @NotBlank String email,
    @Size(min = 8, max = 100) String password
) {}

public record UpdateUserRequest(
    @Size(min = 1, max = 50) String name,
    @Email String email
) {}

// Response DTO
public record UserDto(
    Long id,
    String name,
    String email,
    Boolean isActive,
    LocalDateTime createdAt
) {}

// MapStruct Mapper
@Mapper(componentModel = "spring")
public interface UserMapper {
    UserDto toDto(User user);
    User toEntity(CreateUserRequest req);
    @Mapping(target = "id", ignore = true)
    @Mapping(target = "passwordHash", ignore = true)
    void updateEntity(UpdateUserRequest req, @MappingTarget User user);
}""",
        "framework": "spring-boot",
        "use_count": 1,
    },
    {
        "component_name": "GlobalExceptionHandler",
        "props_schema": "{ @RestControllerAdvice: class; @ExceptionHandler: methods for each exception type }",
        "code_snippet": """@RestControllerAdvice
@Slf4j
public class GlobalExceptionHandler {
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException ex) {
        String message = ex.getBindingResult().getFieldErrors().stream()
            .map(e -> e.getField() + ": " + e.getDefaultMessage())
            .collect(Collectors.joining("; "));
        return ResponseEntity.badRequest().body(new ErrorResponse(400, message));
    }

    @ExceptionHandler(NotFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(NotFoundException ex) {
        return ResponseEntity.status(404).body(new ErrorResponse(404, ex.getMessage()));
    }

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> handleBusiness(BusinessException ex) {
        return ResponseEntity.badRequest().body(new ErrorResponse(400, ex.getMessage()));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneral(Exception ex) {
        log.error("未预期的错误", ex);
        return ResponseEntity.status(500).body(new ErrorResponse(500, "服务器内部错误"));
    }
}""",
        "framework": "spring-boot",
        "use_count": 1,
    },
    {
        "component_name": "JPA Specification Dynamic Query",
        "props_schema": "{ Specification<T>: where clause builder; CriteriaBuilder: query builder }",
        "code_snippet": """@Repository
public interface UserRepository extends JpaRepository<User, Long>, JpaSpecificationExecutor<User> {
}

public class UserSpecifications {
    public static Specification<User> withFilters(UserFilter filter) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (filter.keyword() != null && !filter.keyword().isBlank()) {
                String kw = "%" + filter.keyword() + "%";
                predicates.add(cb.or(
                    cb.like(root.get("name"), kw),
                    cb.like(root.get("email"), kw)
                ));
            }
            if (filter.isActive() != null) {
                predicates.add(cb.equal(root.get("isActive"), filter.isActive()));
            }
            if (filter.createdAfter() != null) {
                predicates.add(cb.greaterThanOrEqualTo(root.get("createdAt"), filter.createdAfter()));
            }
            return cb.and(predicates.toArray(new Predicate[0]));
        };
    }
}

// Usage
userRepository.findAll(UserSpecifications.withFilters(filter), pageable);""",
        "framework": "jpa",
        "use_count": 1,
    },

    # ---- Go (Gin) ----
    {
        "component_name": "Gin Handler + Service",
        "props_schema": "{ router: *gin.Engine; service: *UserService; handler: func(*gin.Context) }",
        "code_snippet": """// handler/user_handler.go
package handler

import (
    "net/http"
    "strconv"
    "github.com/gin-gonic/gin"
)

type UserHandler struct {
    svc *service.UserService
}

func NewUserHandler(svc *service.UserService) *UserHandler {
    return &UserHandler{svc: svc}
}

func (h *UserHandler) RegisterRoutes(r *gin.RouterGroup) {
    r.GET("/users", h.List)
    r.GET("/users/:id", h.GetByID)
    r.POST("/users", h.Create)
    r.PUT("/users/:id", h.Update)
    r.DELETE("/users/:id", h.Delete)
}

func (h *UserHandler) List(c *gin.Context) {
    page, _ := strconv.Atoi(c.DefaultQuery("page", "1"))
    size, _ := strconv.Atoi(c.DefaultQuery("size", "20"))
    users, total, err := h.svc.List(c.Request.Context(), page, size)
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, gin.H{"items": users, "total": total, "page": page, "size": size})
}

func (h *UserHandler) GetByID(c *gin.Context) {
    id, err := strconv.ParseInt(c.Param("id"), 10, 64)
    if err != nil {
        c.JSON(http.StatusBadRequest, gin.H{"error": "无效的ID"})
        return
    }
    user, err := h.svc.GetByID(c.Request.Context(), id)
    if err != nil {
        c.JSON(http.StatusNotFound, gin.H{"error": "用户不存在"})
        return
    }
    c.JSON(http.StatusOK, user)
}""",
        "framework": "gin",
        "use_count": 1,
    },
    {
        "component_name": "Repository with sqlx",
        "props_schema": "{ db: *sqlx.DB; model: struct with db tags }",
        "code_snippet": """// repository/user_repo.go
package repository

import (
    "context"
    "database/sql"
    "errors"
    "github.com/jmoiron/sqlx"
)

type User struct {
    ID        int64  `db:"id" json:"id"`
    Name      string `db:"name" json:"name"`
    Email     string `db:"email" json:"email"`
    IsActive  bool   `db:"is_active" json:"isActive"`
    CreatedAt string `db:"created_at" json:"createdAt"`
}

type UserRepo struct {
    db *sqlx.DB
}

func NewUserRepo(db *sqlx.DB) *UserRepo {
    return &UserRepo{db: db}
}

func (r *UserRepo) FindByID(ctx context.Context, id int64) (*User, error) {
    var user User
    err := r.db.GetContext(ctx, &user, "SELECT * FROM users WHERE id = $1", id)
    if errors.Is(err, sql.ErrNoRows) {
        return nil, ErrNotFound
    }
    return &user, err
}

func (r *UserRepo) FindAll(ctx context.Context, page, size int) ([]User, int, error) {
    var total int
    r.db.GetContext(ctx, &total, "SELECT COUNT(*) FROM users")

    var users []User
    offset := (page - 1) * size
    err := r.db.SelectContext(ctx, &users,
        "SELECT * FROM users ORDER BY id DESC LIMIT $1 OFFSET $2", size, offset)
    return users, total, err
}

func (r *UserRepo) Create(ctx context.Context, u *User) error {
    return r.db.QueryRowContext(ctx,
        "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id, created_at",
        u.Name, u.Email).Scan(&u.ID, &u.CreatedAt)
}""",
        "framework": "go-stdlib",
        "use_count": 1,
    },
    {
        "component_name": "JWT Auth Middleware (Gin)",
        "props_schema": "{ secret: []byte; tokenLookup: 'header:Authorization'; headerPrefix: 'Bearer ' }",
        "code_snippet": """// middleware/auth.go
package middleware

import (
    "net/http"
    "strings"
    "github.com/gin-gonic/gin"
    "github.com/golang-jwt/jwt/v5"
)

func AuthMiddleware(secret []byte) gin.HandlerFunc {
    return func(c *gin.Context) {
        authHeader := c.GetHeader("Authorization")
        if authHeader == "" || !strings.HasPrefix(authHeader, "Bearer ") {
            c.JSON(http.StatusUnauthorized, gin.H{"error": "未提供认证令牌"})
            c.Abort()
            return
        }

        tokenString := strings.TrimPrefix(authHeader, "Bearer ")
        token, err := jwt.Parse(tokenString, func(token *jwt.Token) (interface{}, error) {
            if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
                return nil, jwt.ErrSignatureInvalid
            }
            return secret, nil
        })

        if err != nil || !token.Valid {
            c.JSON(http.StatusUnauthorized, gin.H{"error": "无效的认证令牌"})
            c.Abort()
            return
        }

        claims := token.Claims.(jwt.MapClaims)
        c.Set("user_id", int64(claims["sub"].(float64)))
        c.Next()
    }
}""",
        "framework": "gin",
        "use_count": 1,
    },
    {
        "component_name": "Config Struct + Viper",
        "props_schema": "{ env: string; db: DBConfig; jwt: JWTConfig; server: ServerConfig }",
        "code_snippet": """// config/config.go
package config

import (
    "github.com/spf13/viper"
)

type Config struct {
    Server   ServerConfig
    Database DatabaseConfig
    JWT      JWTConfig
}

type ServerConfig struct {
    Port string
    Mode string  // debug | release
}

type DatabaseConfig struct {
    Host     string
    Port     int
    User     string
    Password string
    DBName   string
    SSLMode  string
}

func (d DatabaseConfig) DSN() string {
    return fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=%s",
        d.Host, d.Port, d.User, d.Password, d.DBName, d.SSLMode)
}

type JWTConfig struct {
    Secret     string
    Expiration time.Duration
}

func LoadConfig(path string) (*Config, error) {
    viper.SetConfigFile(path)
    viper.AutomaticEnv()
    if err := viper.ReadInConfig(); err != nil {
        return nil, err
    }
    var cfg Config
    if err := viper.Unmarshal(&cfg); err != nil {
        return nil, err
    }
    return &cfg, nil
}""",
        "framework": "go-stdlib",
        "use_count": 1,
    },
    {
        "component_name": "Graceful Shutdown (Go)",
        "props_schema": "{ server: *http.Server; shutdownTimeout: time.Duration }",
        "code_snippet": """// main.go
package main

import (
    "context"
    "net/http"
    "os"
    "os/signal"
    "syscall"
    "time"
)

func main() {
    srv := &http.Server{Addr: ":8080", Handler: router}

    // 在 goroutine 中启动服务器
    go func() {
        if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
            log.Fatalf("服务器启动失败: %v", err)
        }
    }()

    // 等待中断信号
    quit := make(chan os.Signal, 1)
    signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
    <-quit
    log.Println("正在优雅关闭服务器...")

    ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
    defer cancel()
    if err := srv.Shutdown(ctx); err != nil {
        log.Fatalf("服务器关闭失败: %v", err)
    }
    log.Println("服务器已关闭")
}""",
        "framework": "gin",
        "use_count": 1,
    },

    # ---- Node.js (Express / NestJS) ----
    {
        "component_name": "Express CRUD Router",
        "props_schema": "{ router: Router; model: Mongoose/Prisma model; middleware: validation + auth }",
        "code_snippet": """// routes/users.ts
import { Router, Request, Response, NextFunction } from 'express';
import { UserService } from '../services/user.service';
import { authenticate } from '../middleware/auth';
import { validate } from '../middleware/validate';
import { createUserSchema, updateUserSchema } from '../validators/user.validator';

const router = Router();
const userService = new UserService();

// 所有路由都需要认证
router.use(authenticate);

router.get('/', async (req: Request, res: Response, next: NextFunction) => {
    try {
        const page = parseInt(req.query.page as string) || 1;
        const limit = Math.min(parseInt(req.query.limit as string) || 20, 100);
        const result = await userService.findAll({ page, limit });
        res.json(result);
    } catch (error) {
        next(error);
    }
});

router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
    try {
        const user = await userService.findById(req.params.id);
        if (!user) return res.status(404).json({ error: '用户不存在' });
        res.json(user);
    } catch (error) {
        next(error);
    }
});

router.post('/', validate(createUserSchema), async (req: Request, res: Response, next: NextFunction) => {
    try {
        const user = await userService.create(req.body);
        res.status(201).json(user);
    } catch (error) {
        next(error);
    }
});

export default router;""",
        "framework": "express",
        "use_count": 1,
    },
    {
        "component_name": "NestJS CRUD Controller + Service",
        "props_schema": "{ @Controller: route prefix; @Injectable service; DTO classes with class-validator }",
        "code_snippet": """// user.controller.ts
@Controller('users')
@UseGuards(JwtAuthGuard)
export class UserController {
    constructor(private readonly userService: UserService) {}

    @Get()
    async findAll(@Query() query: PaginationQuery): Promise<PaginatedResult<UserDto>> {
        return this.userService.findAll(query);
    }

    @Get(':id')
    async findOne(@Param('id', ParseUUIDPipe) id: string): Promise<UserDto> {
        return this.userService.findById(id);
    }

    @Post()
    async create(@Body() dto: CreateUserDto): Promise<UserDto> {
        return this.userService.create(dto);
    }

    @Patch(':id')
    async update(
        @Param('id', ParseUUIDPipe) id: string,
        @Body() dto: UpdateUserDto,
    ): Promise<UserDto> {
        return this.userService.update(id, dto);
    }

    @Delete(':id')
    @HttpCode(HttpStatus.NO_CONTENT)
    async remove(@Param('id', ParseUUIDPipe) id: string): Promise<void> {
        await this.userService.remove(id);
    }
}

// user.service.ts
@Injectable()
export class UserService {
    constructor(@InjectRepository(User) private userRepo: Repository<User>) {}

    async findAll(query: PaginationQuery): Promise<PaginatedResult<UserDto>> {
        const [items, total] = await this.userRepo.findAndCount({
            skip: (query.page - 1) * query.limit,
            take: query.limit,
            order: { createdAt: 'DESC' },
        });
        return { items: items.map(u => UserDto.fromEntity(u)), total, page: query.page, limit: query.limit };
    }
}""",
        "framework": "nestjs",
        "use_count": 1,
    },
    {
        "component_name": "Express Async Error Wrapper",
        "props_schema": "{ fn: async (req, res, next) => void } -> { wrapped: (req, res, next) => void }",
        "code_snippet": """// utils/async-handler.ts
import { Request, Response, NextFunction } from 'express';

/**
 * 包装异步 Express 路由处理器，自动捕获异常并传递给错误处理中间件。
 * 避免每个路由手动 try-catch。
 */
export const asyncHandler = (fn: (req: Request, res: Response, next: NextFunction) => Promise<any>) => {
    return (req: Request, res: Response, next: NextFunction) => {
        Promise.resolve(fn(req, res, next)).catch(next);
    };
};

// 使用示例
router.get('/users', asyncHandler(async (req, res) => {
    const users = await UserService.findAll();
    res.json(users);
}));
// 如果 findAll() reject，错误自动传给 next(err)""",
        "framework": "express",
        "use_count": 1,
    },
    {
        "component_name": "JWT Auth Guard (NestJS Passport)",
        "props_schema": "{ strategy: PassportStrategy(JWT); guard: extends AuthGuard('jwt') }",
        "code_snippet": """// jwt.strategy.ts
@Injectable()
export class JwtStrategy extends PassportStrategy(Strategy) {
    constructor(private configService: ConfigService) {
        super({
            jwtFromRequest: ExtractJwt.fromAuthHeaderAsBearerToken(),
            ignoreExpiration: false,
            secretOrKey: configService.get<string>('JWT_SECRET'),
        });
    }

    async validate(payload: JwtPayload): Promise<UserPayload> {
        return { userId: payload.sub, email: payload.email, roles: payload.roles };
    }
}

// jwt-auth.guard.ts
@Injectable()
export class JwtAuthGuard extends AuthGuard('jwt') {}

// 使用
@Controller('users')
@UseGuards(JwtAuthGuard)
export class UserController { ... }""",
        "framework": "nestjs",
        "use_count": 1,
    },

    # ---- Rust (Actix-web) ----
    {
        "component_name": "Actix-web CRUD Handler + State",
        "props_schema": "{ pool: PgPool; handlers: async fn(State, Path, Json) -> impl Responder }",
        "code_snippet": """use actix_web::{web, HttpResponse, Responder};
use sqlx::PgPool;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, sqlx::FromRow)]
struct User {
    id: i64,
    name: String,
    email: String,
    is_active: bool,
}

#[derive(Deserialize)]
struct CreateUserRequest {
    name: String,
    email: String,
}

async fn list_users(pool: web::Data<PgPool>) -> impl Responder {
    match sqlx::query_as!(User, "SELECT id, name, email, is_active FROM users ORDER BY id")
        .fetch_all(pool.get_ref())
        .await
    {
        Ok(users) => HttpResponse::Ok().json(users),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"error": e.to_string()})),
    }
}

async fn create_user(
    pool: web::Data<PgPool>,
    body: web::Json<CreateUserRequest>,
) -> impl Responder {
    match sqlx::query_as!(User,
        "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id, name, email, is_active",
        body.name, body.email
    )
    .fetch_one(pool.get_ref())
    .await
    {
        Ok(user) => HttpResponse::Created().json(user),
        Err(e) => HttpResponse::InternalServerError().json(serde_json::json!({"error": e.to_string()})),
    }
}

// 路由注册
pub fn config(cfg: &mut web::ServiceConfig) {
    cfg.service(
        web::scope("/users")
            .route("", web::get().to(list_users))
            .route("", web::post().to(create_user))
    );
}""",
        "framework": "actix-web",
        "use_count": 1,
    },
    {
        "component_name": "Repository with sqlx (Rust)",
        "props_schema": "{ pool: PgPool; trait UserRepo: async fn find_by_id/create/update/delete }",
        "code_snippet": """use sqlx::PgPool;
use anyhow::Result;

#[derive(Debug, Clone)]
pub struct UserRepo {
    pool: PgPool,
}

impl UserRepo {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    pub async fn find_by_id(&self, id: i64) -> Result<Option<User>> {
        let user = sqlx::query_as!(User, "SELECT id, name, email, is_active FROM users WHERE id = $1", id)
            .fetch_optional(&self.pool)
            .await?;
        Ok(user)
    }

    pub async fn find_all(&self, page: i64, size: i64) -> Result<(Vec<User>, i64)> {
        let total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM users")
            .fetch_one(&self.pool).await?;
        let users = sqlx::query_as!(User,
            "SELECT id, name, email, is_active FROM users ORDER BY id DESC LIMIT $1 OFFSET $2",
            size, (page - 1) * size
        )
        .fetch_all(&self.pool).await?;
        Ok((users, total.0))
    }

    pub async fn create(&self, name: &str, email: &str) -> Result<User> {
        let user = sqlx::query_as!(User,
            "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id, name, email, is_active",
            name, email
        )
        .fetch_one(&self.pool).await?;
        Ok(user)
    }

    pub async fn delete(&self, id: i64) -> Result<bool> {
        let result = sqlx::query("DELETE FROM users WHERE id = $1")
            .bind(id).execute(&self.pool).await?;
        Ok(result.rows_affected() > 0)
    }
}""",
        "framework": "rust-stdlib",
        "use_count": 1,
    },
    {
        "component_name": "Actix-web Auth Middleware",
        "props_schema": "{ extractor: FromRequest; error: HttpResponse::Unauthorized }",
        "code_snippet": """use actix_web::{dev::ServiceRequest, Error, HttpMessage};
use actix_web_httpauth::extractors::bearer::BearerAuth;
use jsonwebtoken::{decode, DecodingKey, Validation};

pub struct AuthenticatedUser {
    pub user_id: i64,
    pub email: String,
}

pub fn extract_auth(req: &ServiceRequest, secret: &[u8]) -> Result<AuthenticatedUser, Error> {
    let bearer = req.headers().get("Authorization")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .ok_or_else(|| actix_web::error::ErrorUnauthorized("缺少认证令牌"))?;

    let token = decode::<Claims>(
        bearer,
        &DecodingKey::from_secret(secret),
        &Validation::default(),
    ).map_err(|_| actix_web::error::ErrorUnauthorized("无效的认证令牌"))?;

    Ok(AuthenticatedUser {
        user_id: token.claims.sub,
        email: token.claims.email,
    })
}

// 在 handler 中使用
async fn protected_route(user: AuthenticatedUser) -> impl Responder {
    HttpResponse::Ok().json(serde_json::json!({"user_id": user.user_id}))
}""",
        "framework": "actix-web",
        "use_count": 1,
    },
]

# ============================================================
# Collection 3: design_pattern
# ============================================================
DESIGN_PATTERN_SEEDS = [
    {
        "pattern_name": "响应式网格布局",
        "description": "使用 Tailwind CSS grid 配合 sm/md/lg/xl 断点，实现移动优先的多列自适应布局。默认单列，逐级增加列数。",
        "example_code": """<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
  <ProductCard v-for="item in items" :key="item.id" :product="item" />
</div>""",
        "best_for": "商品列表、卡片展示、图片画廊、文章列表",
    },
    {
        "pattern_name": "无限滚动加载",
        "description": "监听滚动事件，当滚动到底部时自动加载下一页数据。使用 IntersectionObserver 实现性能更好的方案。",
        "example_code": """<script setup lang="ts">
const sentinel = ref<HTMLElement>()
const loading = ref(false)
const hasMore = ref(true)
useIntersectionObserver(sentinel, ([{ isIntersecting }]) => {
  if (isIntersecting && hasMore.value && !loading.value) loadMore()
})
async function loadMore() { loading.value = true; const newItems = await fetchPage(currentPage.value + 1); items.value.push(...newItems); currentPage.value++; loading.value = false; if (newItems.length < pageSize) hasMore.value = false }
</script>
<template>
  <div class="space-y-4"><slot /></div>
  <div ref="sentinel" class="py-4 text-center text-gray-400">{{ loading ? '加载中...' : hasMore ? '下拉加载更多' : '没有更多了' }}</div>
</template>""",
        "best_for": "信息流、商品列表、搜索结果、评论列表",
    },
    {
        "pattern_name": "搜索筛选栏",
        "description": "页面顶部固定搜索框 + 分类/标签筛选的组合模式。支持关键词搜索和多项筛选条件同时生效。",
        "example_code": """<div class="sticky top-0 z-10 bg-white border-b p-4 space-y-3">
  <input v-model="keyword" placeholder="搜索..." class="w-full px-4 py-2 border rounded-lg" @input="debouncedSearch" />
  <div class="flex flex-wrap gap-2">
    <button v-for="tag in tags" :key="tag" @click="toggleTag(tag)" :class="['px-3 py-1 rounded-full text-sm', selectedTags.includes(tag) ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200']">{{ tag }}</button>
  </div>
</div>""",
        "best_for": "电商搜索、文章筛选、用户列表过滤、订单查询",
    },
    {
        "pattern_name": "主从布局 Master-Detail",
        "description": "左侧列表 + 右侧详情的双栏布局。点击列表项时右侧展示对应详情。移动端列表全屏，点击后切换为详情。",
        "example_code": """<div class="flex h-[calc(100vh-4rem)]">
  <aside class="w-72 border-r overflow-y-auto hidden md:block">
    <div v-for="item in items" :key="item.id" @click="selected = item" :class="['p-4 cursor-pointer border-b hover:bg-gray-50', selected?.id === item.id && 'bg-blue-50 border-l-4 border-l-blue-600']">{{ item.name }}</div>
  </aside>
  <main class="flex-1 overflow-y-auto p-6">
    <DetailPanel v-if="selected" :item="selected" />
    <EmptyState v-else title="请选择一个项目" />
  </main>
</div>""",
        "best_for": "邮件客户端、管理后台列表+编辑、文档浏览、聊天界面",
    },
    {
        "pattern_name": "多步骤表单",
        "description": "将复杂表单拆分为多个步骤，每步只展示部分字段。顶部步骤指示器显示进度，支持上一步/下一步导航。",
        "example_code": """<script setup lang="ts">
const step = ref(1); const totalSteps = 3
const form = reactive({ step1: {}, step2: {}, step3: {} })
function next() { if (step.value < totalSteps) step.value++ }
function prev() { if (step.value > 1) step.value-- }
</script>
<template>
  <div class="max-w-2xl mx-auto">
    <div class="flex items-center justify-center mb-8">
      <div v-for="s in totalSteps" :key="s" class="flex items-center">
        <div :class="['w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium', s <= step ? 'bg-blue-600 text-white' : 'bg-gray-200 text-gray-500']">{{ s }}</div>
        <div v-if="s < totalSteps" :class="['w-12 h-0.5', s < step ? 'bg-blue-600' : 'bg-gray-200']" />
      </div>
    </div>
    <Step1 v-if="step === 1" v-model="form.step1" />
    <Step2 v-else-if="step === 2" v-model="form.step2" />
    <Step3 v-else v-model="form.step3" />
    <div class="flex justify-between mt-6">
      <button v-if="step > 1" @click="prev" class="px-4 py-2 border rounded-md">上一步</button>
      <button v-if="step < totalSteps" @click="next" class="px-4 py-2 bg-blue-600 text-white rounded-md ml-auto">下一步</button>
      <button v-else @click="submit" class="px-4 py-2 bg-green-600 text-white rounded-md ml-auto">提交</button>
    </div>
  </div>
</template>""",
        "best_for": "注册流程、结账流程、配置向导、发布流程",
    },
    {
        "pattern_name": "仪表盘布局",
        "description": "统计卡片 + 图表 + 列表的仪表盘布局。统计卡片在上方一行展示关键指标，下方左右分栏展示图表和数据表格。",
        "example_code": """<div class="p-6 space-y-6">
  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
    <div v-for="stat in stats" :key="stat.label" class="rounded-lg border p-4"><p class="text-sm text-gray-500">{{ stat.label }}</p><p class="text-2xl font-bold mt-1">{{ stat.value }}</p><span :class="stat.trend > 0 ? 'text-green-600' : 'text-red-600'" class="text-xs">{{ stat.trend > 0 ? '+' : '' }}{{ stat.trend }}%</span></div>
  </div>
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <div class="lg:col-span-2 rounded-lg border p-4"><h3 class="font-medium mb-4">趋势图</h3><div class="h-64 bg-gray-50 rounded" /><!-- 图表 --></div>
    <div class="rounded-lg border p-4"><h3 class="font-medium mb-4">最近活动</h3><!-- 列表 --></div>
  </div>
</div>""",
        "best_for": "后台首页、数据分析页、监控面板、运营看板",
    },
    {
        "pattern_name": "固定头部 + 侧边栏",
        "description": "管理后台经典布局：顶部固定导航栏 + 左侧可折叠侧边栏 + 右侧内容区。移动端侧边栏变为抽屉式。",
        "example_code": """<div class="min-h-screen bg-gray-50">
  <header class="sticky top-0 z-20 h-14 bg-white border-b flex items-center justify-between px-4">
    <button @click="sidebarOpen = !sidebarOpen" class="md:hidden">☰</button>
    <h1 class="text-lg font-bold">Admin</h1>
    <UserMenu />
  </header>
  <div class="flex">
    <aside :class="['fixed md:sticky top-14 z-10 w-60 h-[calc(100vh-3.5rem)] bg-white border-r overflow-y-auto transition-transform', sidebarOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0']">
      <nav class="p-4 space-y-1">
        <router-link v-for="item in menuItems" :key="item.path" :to="item.path" class="block px-3 py-2 rounded-md text-sm hover:bg-gray-100" active-class="bg-blue-50 text-blue-600">{{ item.label }}</router-link>
      </nav>
    </aside>
    <main class="flex-1 p-6"><router-view /></main>
  </div>
</div>""",
        "best_for": "管理后台、内容管理 CMS、企业应用、配置中心",
    },
    {
        "pattern_name": "标签页切换",
        "description": "使用 Tabs 组件组织不同内容区域，切换时只渲染当前激活的标签内容。",
        "example_code": """<Tabs :tabs="tabs" v-model="activeTab" />
<KeepAlive>
  <component :is="tabComponents[activeTab]" />
</KeepAlive>""",
        "best_for": "设置页、个人主页、商品详情、多维度数据展示",
    },
    {
        "pattern_name": "骨架屏加载态",
        "description": "数据加载时展示灰色占位块动画，避免白屏，提升用户感知性能。与真实内容结构一致。",
        "example_code": """<template>
  <SkeletonLoader v-if="loading" type="card" :count="6" />
  <CardGrid v-else :items="products"><ProductCard :product="item" /></CardGrid>
</template>""",
        "best_for": "任何有异步数据加载的页面，尤其是列表和卡片",
    },
    {
        "pattern_name": "错误状态与重试",
        "description": "API 请求失败时展示错误信息和重试按钮，而非白屏或崩溃。包含网络错误、权限错误、服务器错误三种状态。",
        "example_code": """<script setup lang="ts">
const error = ref<string | null>(null)
const loading = ref(false)
async function fetchData() { loading.value = true; error.value = null; try { data.value = await api.getProducts() } catch (e) { error.value = e.message || '加载失败，请重试' } finally { loading.value = false } }
</script>
<template>
  <EmptyState v-if="error" icon="⚠️" :title="error" actionText="重试" @action="fetchData" />
</template>""",
        "best_for": "所有数据请求场景",
    },
    {
        "pattern_name": "乐观更新 Optimistic Update",
        "description": "用户操作（点赞、删除、修改）时先更新 UI，再异步请求 API。失败时回滚 UI 并提示错误。",
        "example_code": """<script setup lang="ts">
async function toggleLike(item: Item) {
  const previous = item.liked
  item.liked = !item.liked  // 立即更新 UI
  try { await api.toggleLike(item.id) }
  catch { item.liked = previous; message.error('操作失败，请重试') }
}
</script>""",
        "best_for": "点赞、收藏、切换开关、拖拽排序",
    },
    {
        "pattern_name": "防抖搜索",
        "description": "用户在搜索框输入时，延迟 300ms 后再发请求，避免每个字符都触发一次 API 调用。",
        "example_code": """<script setup lang="ts">
const keyword = ref('')
let timer: ReturnType<typeof setTimeout>
function onInput() { clearTimeout(timer); timer = setTimeout(() => { fetchResults(keyword.value) }, 300) }
onUnmounted(() => clearTimeout(timer))
</script>
<template><input :value="keyword" @input="keyword = ($event.target as HTMLInputElement).value; onInput()" placeholder="输入关键词搜索" /></template>""",
        "best_for": "搜索框、自动补全、筛选器",
    },

    # ---- 后端通用设计模式 ----
    {
        "pattern_name": "Repository 模式 (数据访问层抽象)",
        "description": "将数据访问逻辑封装在独立的 Repository 层中，屏蔽底层数据库细节。上层 Service 只依赖 Repository 接口，不直接操作 ORM/Driver。便于单元测试（可 mock Repository）和切换数据源。",
        "example_code": """# Python (SQLAlchemy)
class UserRepo:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_id(self, id: int) -> User | None:
        return await self.db.get(User, id)

    async def find_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

# Service 层依赖注入 Repository
class UserService:
    def __init__(self, repo: UserRepo):
        self.repo = repo

// Java (Spring Data JPA)
@Repository
public interface UserRepository extends JpaRepository<User, Long> {
    Optional<User> findByEmail(String email);
    @Query("SELECT u FROM User u WHERE u.isActive = true")
    Page<User> findActiveUsers(Pageable pageable);
}

// Go (sqlx)
type UserRepo struct { db *sqlx.DB }
func (r *UserRepo) FindByID(ctx context.Context, id int64) (*User, error) { ... }""",
        "best_for": "所有涉及数据库操作的后端项目（Python/Java/Go/Node.js）",
    },
    {
        "pattern_name": "Service 层模式 (业务逻辑隔离)",
        "description": "在 Controller/Handler 和 Repository 之间引入 Service 层，承载业务逻辑、事务管理、权限校验。Controller 只负责请求解析和响应格式化，保持瘦控制器。",
        "example_code": """# Python FastAPI
class OrderService:
    def __init__(self, order_repo: OrderRepo, inventory_svc: InventoryService):
        self.order_repo = order_repo
        self.inventory_svc = inventory_svc

    async def create_order(self, dto: CreateOrderDto) -> Order:
        # 业务逻辑：校验库存、计算价格、创建订单
        for item in dto.items:
            if not await self.inventory_svc.check_availability(item.product_id, item.quantity):
                raise BusinessException(f"商品 {item.product_id} 库存不足")
        order = await self.order_repo.create(dto)
        await self.inventory_svc.deduct(dto.items)
        return order

// Java Spring Boot
@Service
@Transactional
public class OrderService {
    public OrderDto createOrder(CreateOrderRequest req) {
        // 1. 校验库存
        // 2. 计算总价
        // 3. 创建订单
        // 4. 扣减库存
        // 全部在同一事务中
    }
}

// Go
type OrderService struct {
    orderRepo     *repository.OrderRepo
    inventorySvc  *service.InventoryService
}
func (s *OrderService) CreateOrder(ctx context.Context, req CreateOrderReq) (*Order, error) { ... }""",
        "best_for": "任何有业务逻辑的后端项目",
    },
    {
        "pattern_name": "中间件管道模式 (Middleware Pipeline)",
        "description": "将横切关注点（认证、日志、限流、CORS、压缩）封装为独立的中间件函数，按顺序链式处理请求。每个中间件可决定放行（next）或拦截（return error）。",
        "example_code": """# Python FastAPI
@app.middleware("http")
async def log_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    logger.info(f"{request.method} {request.url.path} {response.status_code} {time.time()-start:.3f}s")
    return response

# 使用 Depends 做中间件式依赖
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    # 认证中间件逻辑
    pass

// Go Gin
func LoggerMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        t := time.Now()
        c.Next()
        latency := time.Since(t)
        log.Printf("%s %s %d %v", c.Request.Method, c.Request.URL.Path, c.Writer.Status(), latency)
    }
}
r.Use(LoggerMiddleware(), AuthMiddleware(), CORSMiddleware())

// Java Spring Boot
// Filter / HandlerInterceptor / @Aspect 三种中间件实现
@Component
public class LogInterceptor implements HandlerInterceptor {
    public boolean preHandle(HttpServletRequest req, HttpServletResponse res, Object handler) {
        req.setAttribute("startTime", System.currentTimeMillis());
        return true;
    }
    public void afterCompletion(...) { /* 计算耗时 */ }
}""",
        "best_for": "所有后端项目（认证、日志、限流、追踪等横切关注点）",
    },
    {
        "pattern_name": "依赖注入与组合 (DI / IoC)",
        "description": "通过构造函数或框架注入依赖，而非在类内部 new 或 import 全局单例。降低耦合，提高可测试性。FastAPI 用 Depends，Spring 用 @Autowired，NestJS 用 @Injectable，Go 用构造函数。",
        "example_code": """# Python FastAPI — Depends 函数式 DI
async def get_db():
    async with SessionLocal() as db:
        yield db

@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),  # 可嵌套
):
    ...

// Java Spring — 构造器注入（推荐）
@RestController
@RequiredArgsConstructor  // Lombok 生成构造器
public class UserController {
    private final UserService userService;  // final + 构造器 = 不可变 + 易测试
}

// Go — 构造函数注入（手动 DI）
func NewUserService(repo *UserRepo, cache *redis.Client) *UserService {
    return &UserService{repo: repo, cache: cache}
}

// NestJS — 装饰器 DI
@Injectable()
export class UserService {
    constructor(
        @InjectRepository(User) private userRepo: Repository<User>,
        private cacheService: CacheService,
    ) {}
}""",
        "best_for": "所有后端项目（提高可测试性和模块化）",
    },
    {
        "pattern_name": "统一错误处理模式",
        "description": "定义异常层次结构 + 全局异常处理器，将业务异常自动转换为标准 HTTP 响应。避免在每个 Controller 中写 try-catch 和重复的错误响应格式。",
        "example_code": """# Python FastAPI
class AppException(Exception):
    def __init__(self, status_code: int, detail: str, code: str = ""):
        self.status_code = status_code
        self.detail = detail

class NotFoundException(AppException):
    def __init__(self, detail: str = "资源不存在"):
        super().__init__(404, detail)

@app.exception_handler(AppException)
async def app_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

// Java Spring Boot
@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> handleBusiness(BusinessException ex) {
        return ResponseEntity.badRequest().body(new ErrorResponse(ex.getCode(), ex.getMessage()));
    }
}

// Go Gin
func ErrorHandler() gin.HandlerFunc {
    return func(c *gin.Context) {
        c.Next()
        if len(c.Errors) > 0 {
            c.JSON(-1, gin.H{"error": c.Errors.Last().Err.Error()})
        }
    }
}""",
        "best_for": "所有后端项目（标准化错误响应格式）",
    },
    {
        "pattern_name": "分页查询模式",
        "description": "统一的游标/偏移分页方案。前端传 page+size，后端返回 items+total+pages。对大数据集使用游标分页（cursor-based）避免 OFFSET 性能问题。",
        "example_code": """# Python FastAPI — 通用分页
class PaginationParams:
    def __init__(self, page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)):
        self.page = page
        self.size = size
        self.offset = (page - 1) * size

# 使用
async def list_users(pagination: PaginationParams = Depends(), db = Depends(get_db)):
    total = await db.scalar(select(func.count()).select_from(User))
    items = await db.scalars(select(User).offset(pagination.offset).limit(pagination.size))
    return PaginatedResponse(items=items.all(), total=total, **pagination.__dict__)

// Java Spring Boot — Pageable
@GetMapping
public Page<UserDto> list(@PageableDefault(size = 20) Pageable pageable) {
    return userRepository.findAll(pageable).map(userMapper::toDto);
}

// Go — Offset/Limit
func (r *UserRepo) FindAll(ctx context.Context, page, size int) ([]User, int, error) {
    var total int; r.db.GetContext(ctx, &total, "SELECT COUNT(*) FROM users")
    var users []User
    offset := (page - 1) * size
    err := r.db.SelectContext(ctx, &users, "SELECT * FROM users ORDER BY id LIMIT $1 OFFSET $2", size, offset)
    return users, total, err
}""",
        "best_for": "任何需要列表查询的 API 端点",
    },
    {
        "pattern_name": "后台任务 + 消息队列模式",
        "description": "耗时操作（发送邮件、生成报表、图片处理）不应阻塞 HTTP 响应。轻量场景用 BackgroundTasks/Future，重量场景用 Celery/BullMQ/RabbitMQ 异步处理。",
        "example_code": """# Python FastAPI — 轻量后台任务
@router.post("/send-verification")
async def send_verification(background_tasks: BackgroundTasks, email: str):
    background_tasks.add_task(email_service.send_verification, email)
    return {"message": "验证邮件将在后台发送"}

# Python — Celery 重量任务
@celery_app.task
def generate_report(report_id: str):
    # 生成 PDF / Excel 报表...
    pass

// Node.js — BullMQ 队列
const emailQueue = new Queue('email');
await emailQueue.add('send-verification', { email: 'user@example.com' });

// 消费者
const worker = new Worker('email', async (job) => {
    await sendgrid.send({ to: job.data.email, ... });
});

// Go — goroutine + channel
go func() {
    if err := sendEmail(to); err != nil {
        log.Printf("邮件发送失败: %v", err)
    }
}()""",
        "best_for": "邮件发送、报表生成、图片处理等耗时操作",
    },
    {
        "pattern_name": "API 版本管理策略",
        "description": "通过 URL 前缀（/api/v1/）或请求头（Accept: application/vnd.api+v2）管理 API 版本。大版本不兼容变更走新版本，小版本向前兼容。",
        "example_code": """# Python FastAPI — URL 前缀版本
app = FastAPI()

v1 = APIRouter(prefix="/api/v1")
v1.include_router(users.router, prefix="/users")
app.include_router(v1)

v2 = APIRouter(prefix="/api/v2")
v2.include_router(users_v2.router, prefix="/users")  # 破坏性变更
app.include_router(v2)

// Java Spring Boot — RequestMapping 前缀
@RestController
@RequestMapping("/api/v1/users")
public class UserControllerV1 { }

@RestController
@RequestMapping("/api/v2/users")
public class UserControllerV2 { }

// Go Gin — 路由分组
v1 := r.Group("/api/v1")
{ v1.GET("/users", handlerV1.ListUsers) }
v2 := r.Group("/api/v2")
{ v2.GET("/users", handlerV2.ListUsers) }""",
        "best_for": "需要长期维护的公共 API",
    },
    {
        "pattern_name": "缓存策略模式 (Cache-Aside / Read-Through)",
        "description": "Cache-Aside：读时先查缓存，miss 则查库并回填；写时先写库再删缓存。适用于读多写少的热点数据（用户信息、配置、商品详情）。使用 Redis/Memcached 作为缓存层。",
        "example_code": """# Python — 手动 Cache-Aside
async def get_user(user_id: int) -> User | None:
    cached = await redis.get(f"user:{user_id}")
    if cached:
        return User.model_validate(json.loads(cached))

    user = await db.get(User, user_id)
    if user:
        await redis.setex(f"user:{user_id}", 600, user.model_dump_json())
    return user

async def update_user(user_id: int, data: UserUpdate):
    await db.execute(update(User).where(User.id == user_id).values(**data.model_dump()))
    await redis.delete(f"user:{user_id}")  # 先写库，再删缓存

// Java Spring Boot — @Cacheable 声明式
@Cacheable(value = "users", key = "#id", unless = "#result == null")
public UserDto findById(Long id) { ... }

@CacheEvict(value = "users", key = "#id")
public void update(Long id, UpdateUserRequest req) { ... }

// Go — Redis 缓存
func (s *UserService) GetByID(ctx context.Context, id int64) (*User, error) {
    key := fmt.Sprintf("user:%d", id)
    cached, _ := s.redis.Get(ctx, key).Result()
    if cached != "" {
        var user User; json.Unmarshal([]byte(cached), &user)
        return &user, nil
    }
    user, err := s.repo.FindByID(ctx, id)
    if user != nil {
        data, _ := json.Marshal(user)
        s.redis.SetEx(ctx, key, data, 10*time.Minute)
    }
    return user, err
}""",
        "best_for": "热点数据缓存、Session 管理、限流计数器",
    },
    {
        "pattern_name": "数据库连接池配置",
        "description": "正确配置连接池大小（pool_size + max_overflow）和超时参数，避免连接泄漏和连接耗尽。启用 pool_pre_ping 检测断连，设置合理的回收时间。",
        "example_code": """# Python SQLAlchemy
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,           # 基础连接数
    max_overflow=10,        # 额外允许的连接数（总计最多 30）
    pool_pre_ping=True,     # 使用前检测连接有效性
    pool_recycle=3600,      # 1小时后回收连接
    pool_timeout=30,        # 获取连接超时
)

// Java HikariCP (Spring Boot 默认)
spring.datasource.hikari.maximum-pool-size=20
spring.datasource.hikari.minimum-idle=5
spring.datasource.hikari.idle-timeout=300000
spring.datasource.hikari.connection-timeout=30000
spring.datasource.hikari.max-lifetime=1800000

// Go database/sql
db.SetMaxOpenConns(25)               # 最大打开连接数
db.SetMaxIdleConns(5)                # 最大空闲连接数
db.SetConnMaxLifetime(5 * time.Minute)  # 连接最大存活时间
db.SetConnMaxIdleTime(1 * time.Minute)  # 空闲连接最大存活时间""",
        "best_for": "所有连接数据库的后端项目",
    },
    {
        "pattern_name": "环境配置管理 (12-Factor App)",
        "description": "将配置与代码分离，通过环境变量或配置文件管理不同环境的参数。使用 .env 文件开发，生产环境注入真实环境变量。敏感信息（密码、密钥）绝不硬编码。",
        "example_code": """# Python — pydantic-settings
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    DATABASE_URL: str
    JWT_SECRET: str
    REDIS_URL: str = "redis://localhost:6379"

settings = Settings()

// Java Spring Boot — application.yml
spring:
  profiles:
    active: ${SPRING_PROFILES_ACTIVE:dev}
  datasource:
    url: ${DATASOURCE_URL}
    username: ${DATASOURCE_USERNAME}
    password: ${DATASOURCE_PASSWORD}

// Go — Viper + 环境变量
viper.SetDefault("server.port", "8080")
viper.BindEnv("database.host", "DB_HOST")  # 环境变量优先
viper.BindEnv("jwt.secret", "JWT_SECRET")""",
        "best_for": "所有需要区分 dev/staging/prod 环境的项目",
    },
    {
        "pattern_name": "请求校验 + 响应序列化分层",
        "description": "请求使用 DTO/Schema 校验输入合法性（类型、长度、格式），响应使用专用 Response Model 控制输出字段。避免直接暴露 ORM Entity 到 API 响应（安全性 + 避免循环引用）。",
        "example_code": """# Python FastAPI — Pydantic Schema 分层
class UserCreate(BaseModel):  # 输入校验
    name: str = Field(..., min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)

class UserOut(BaseModel):  # 输出序列化
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    created_at: datetime
    # 注意：password 不在输出中！

// Java Spring Boot — Record DTO
public record CreateUserRequest(@NotBlank String name, @Email String email, @Size(min=8) String password) {}
public record UserResponse(Long id, String name, String email, LocalDateTime createdAt) {}

// Go — Request/Response struct
type CreateUserReq struct {
    Name  string `json:"name" binding:"required,min=1,max=50"`
    Email string `json:"email" binding:"required,email"`
}
type UserResponse struct {
    ID        int64  `json:"id"`
    Name      string `json:"name"`
    Email     string `json:"email"`
    CreatedAt string `json:"createdAt"`
}""",
        "best_for": "所有 API 开发（安全性 + 输入校验 + 版本演进）",
    },
]

# ============================================================
# Collection 4: error_pattern
# ============================================================
ERROR_PATTERN_SEEDS = [
    {
        "error_signature": "Module not found: Can't resolve '@/components/...' or path alias not working",
        "fix_code": "检查 vite.config.ts 中 resolve.alias 配置：\nresolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } }\n同时检查 tsconfig.json 中 paths: { \"@/*\": [\"src/*\"] }",
        "occurrence_count": 5,
    },
    {
        "error_signature": "v-for directive requires :key attribute (missing or duplicate keys)",
        "fix_code": "每个 v-for 必须提供唯一且稳定的 key，用 item.id 而非 index：\n<li v-for=\"item in items\" :key=\"item.id\">{{ item.name }}</li>\n避免用 Math.random() 或 index 作为 key（会导致渲染错误和性能问题）",
        "occurrence_count": 5,
    },
    {
        "error_signature": "ref.value used in template or reactive object destructuring",
        "fix_code": "模板中 ref 自动解包，不需要 .value。但 script 中必须 .value。\nreactive 对象不可解构：const { count } = state 丢失响应式，应使用 toRefs(state)。\nPinia store 解构用 storeToRefs(store) 而非直接解构。",
        "occurrence_count": 4,
    },
    {
        "error_signature": "defineProps type argument must be a literal type or reference to an interface/type in the same file",
        "fix_code": "defineProps<T>() 的泛型必须是本地定义的 interface/type，不能从外部导入。如需复用，用独立 .ts 类型文件 + 组件内 import type：\nimport type { ProductCardProps } from '@/types'\ndefineProps<ProductCardProps>()",
        "occurrence_count": 3,
    },
    {
        "error_signature": "Property 'xxx' does not exist on type '{}' or TS2339",
        "fix_code": "ref 初始值类型推断问题：const items = ref([]) → Ref<never[]>，需显式泛型 const items = ref<Item[]>([])。\nreactive 同理：const state = reactive<{ items: Item[] }>({ items: [] })。\n模板中的变量也需在 script 中声明。",
        "occurrence_count": 4,
    },
    {
        "error_signature": "Cannot read properties of null (reading 'xxx') — optional chaining missing",
        "fix_code": "异步数据在请求完成前为 null，模板访问需可选链：\n{{ user?.name }} 而非 {{ user.name }}\n或用 v-if=\"user\" 包裹，或提供初始默认值。计算属性中做防御：return user.value?.name ?? ''",
        "occurrence_count": 4,
    },
    {
        "error_signature": "Component is missing template or render function",
        "fix_code": ".vue 文件必须包含 <template> 块（即使是空的）。单文件组件中 <script setup> 和 <style scoped> 是可选的，但 <template> 必须有。",
        "occurrence_count": 3,
    },
    {
        "error_signature": "Emit event not declared in defineEmits — 'xxx' is not defined in component emits",
        "fix_code": "子组件 emit 的事件必须在 defineEmits 中声明：\nconst emit = defineEmits<{ (e: 'update', val: number): void }>()\nVue 3.3+ 支持简写：defineEmits<{ update: [val: number] }>()\n父组件使用 v-model:xxx 对应 emit('update:xxx')。",
        "occurrence_count": 3,
    },
    {
        "error_signature": "Reactivity lost when passing props to nested composable or watch",
        "fix_code": "将 props 传给 composable 时需用 toRef：\nconst { name } = toRefs(props)\nuseFeature(toRef(props, 'id'))  // 单个 prop\nwatch 中直接使用 props.xxx 会自动追踪，但解构后的变量不会。",
        "occurrence_count": 3,
    },
    {
        "error_signature": "CSS class not applied or Tailwind class not working (no effect on element)",
        "fix_code": "确保 tailwind.config.ts 的 content 路径包含所有 .vue 文件：\ncontent: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}']\n动态拼接的类名不会被 Tailwind 识别，需使用完整类名：\n:class=\"active ? 'bg-blue-600' : 'bg-gray-200'\" 而非 :class=\"'bg-' + color\"",
        "occurrence_count": 4,
    },
    {
        "error_signature": "Pinia store not reactive after page navigation or useStore() called outside setup",
        "fix_code": "useStore() 必须在 setup() / <script setup> 顶层调用，或在 Pinia 的 action 中。\n不能在 router.beforeEach 回调、普通函数内部、或生命周期外调用。\n路由守卫中如需访问 store，将 useStore() 放在守卫内部第一个参数处。",
        "occurrence_count": 3,
    },
    {
        "error_signature": "build failed: 'defineProps' is not defined / 'ref' is not defined",
        "fix_code": "使用 <script setup lang=\"ts\"> 时，defineProps/defineEmits 是编译器宏，不需要 import。\n但 ref/reactive/computed 等必须从 vue 导入：\nimport { ref, reactive, computed, watch, onMounted } from 'vue'\n检查 ESLint 配置中的 vue/setup-compiler-macros 环境是否开启。",
        "occurrence_count": 3,
    },
    {
        "error_signature": "TypeError: Cannot read properties of undefined (reading 'xxx') — nested object access",
        "fix_code": "深层嵌套对象访问前检查每一级：\nuser.value?.profile?.address?.city ?? '未知'\n或使用计算属性做安全访问：\nconst city = computed(() => user.value?.profile?.address?.city ?? '')\nPinia store 中初始状态应包含完整结构（允许值为 null 但不能缺少键）。",
        "occurrence_count": 3,
    },
    {
        "error_signature": "Vue Router warning: No match found for location with path '/xxx'",
        "fix_code": "检查路由配置是否包含该路径，通配符路由放在最后：\n{ path: '/:pathMatch(.*)*', redirect: '/404' }  // Vue Router 4\n动态路由参数变化时组件不会重新创建，需要用 watch 监听 route.params：\nwatch(() => route.params.id, (newId) => { fetchData(newId) })",
        "occurrence_count": 2,
    },
    {
        "error_signature": "npm run build: Rollup failed to resolve import 'xxx' — dependency missing",
        "fix_code": "检查 package.json 是否包含该依赖。如果是项目内文件，确保路径拼写正确且文件存在。\nTypeScript 路径别名（@/xxx）需在 vite.config.ts 中配置 resolve.alias。\n检查 import 语句中的大小写（Windows 不敏感但 Linux/CI 敏感）。",
        "occurrence_count": 3,
    },
    # ---- Python ----
    {
        "error_signature": "AttributeError: 'NoneType' object has no attribute 'xxx'",
        "fix_code": "检查返回值是否为 None：\nuser = await user_repo.find_by_id(id)\nif not user:  # 或 if user is None\n    raise HTTPException(status_code=404, detail='用户不存在')\n# 使用 Optional 类型提示明确表示可能为 None\ndef find_by_id(id: int) -> User | None: ...",
        "occurrence_count": 5,
    },
    {
        "error_signature": "pydantic.ValidationError: 1 validation error for UserCreate",
        "fix_code": "检查 Pydantic schema 定义：\n1. 字段类型是否与请求 body 匹配\n2. Field() 约束是否过严（min_length / max_length / gt / lt）\n3. 前端发送 JSON key 是否与 Pydantic field name 一致\n4. 可选字段是否设为 Optional[T] = None\n调试：print(UserCreate.model_validate(req_body))",
        "occurrence_count": 5,
    },
    {
        "error_signature": "RuntimeError: This event loop is already running (asyncio.run() in nested context)",
        "fix_code": "asyncio.run() 不能在已有事件循环的环境中调用（Jupyter、部分 FastAPI 测试）。\n解决方案：\n1. Jupyter 中直接 await，无需 asyncio.run()\n2. FastAPI 环境用 @app.on_event() 或 lifespan\n3. 已处于事件循环中：loop = asyncio.get_running_loop(); loop.create_task(...)",
        "occurrence_count": 3,
    },
    {
        "error_signature": "ImportError: attempted relative import beyond top-level package",
        "fix_code": "相对导入 `from ..module import X` 只能在包内使用。\n1. 确保项目根目录有 __init__.py\n2. 运行脚本时使用 `python -m package.module` 而非 `python package/module.py`\n3. 或改用绝对导入 `from app.core.config import settings`\n4. 在 pyproject.toml 中配置 [tool.setuptools.packages.find]",
        "occurrence_count": 4,
    },
    {
        "error_signature": "sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) connection to server ... failed",
        "fix_code": "数据库连接失败排查：\n1. 检查 DATABASE_URL 格式（postgresql+asyncpg://user:pass@host:port/db）\n2. 确认数据库服务运行中\n3. 检查 pool_size + max_overflow 是否超过数据库 max_connections\n4. 启用 pool_pre_ping=True 检测断连\n5. pool_recycle 设置合理的回收时间（小于数据库连接超时）\n6. async session 需要 commit/rollback/close 防止连接泄漏",
        "occurrence_count": 4,
    },
    {
        "error_signature": "TypeError: Object of type X is not JSON serializable (FastAPI / json.dumps)",
        "fix_code": "非标准类型无法直接 JSON 序列化：\n1. datetime → 用 Pydantic model 输出，或在 response_model 中声明\n2. Decimal → 使用 json_encoders = {Decimal: str}\n3. ObjectId (MongoDB) → 转为 str\n4. 自定义类 → 实现 def __json__(self) 或使用 json.dumps(default=str)\n5. SQLAlchemy 对象 → 设置 from_attributes=True 或手动 model_dump()",
        "occurrence_count": 4,
    },
    # ---- Java ----
    {
        "error_signature": "LazyInitializationException: could not initialize proxy [org.hibernate.proxy...] – no Session",
        "fix_code": "JPA 懒加载代理对象在 Session 关闭后无法访问。解决方案：\n1. 在 @Transactional 方法内访问关联数据\n2. 使用 @EntityGraph 或 JOIN FETCH 预加载需要的数据\n3. DTO 投影：@Query(\"SELECT new UserDto(u.id, u.name) FROM User u\")\n4. 设置 spring.jpa.open-in-view=false 并显式管理事务边界",
        "occurrence_count": 5,
    },
    {
        "error_signature": "NullPointerException: Cannot invoke \"com.example.model.User.getName()\" because \"user\" is null",
        "fix_code": "Java NPE 常见原因及修复：\n1. Repository 返回 Optional → 使用 .orElseThrow() 而非 .get()\n   userRepo.findById(id).orElseThrow(() -> new NotFoundException(...))\n2. 外部 API 返回值 → 使用 Optional.ofNullable() 包装\n3. 链式调用前检查 → Objects.requireNonNull(obj, \"obj must not be null\")\n4. 考虑使用 @Nullable / @NonNull 注解 + IDE 警告",
        "occurrence_count": 5,
    },
    {
        "error_signature": "DataIntegrityViolationException: could not execute statement; constraint [uk_email]",
        "fix_code": "数据库约束冲突（唯一键、外键、非空）：\n1. 唯一键冲突 → 插入前用 existsByEmail() 检查，返回友好错误\n2. 外键冲突 → 确保关联实体存在，或级联操作\n3. 非空约束 → 检查 Entity 字段是否都有默认值\n4. 全局异常处理捕获 DataIntegrityViolationException，解析 constraint name 返回中文提示",
        "occurrence_count": 4,
    },
    {
        "error_signature": "HttpMessageNotReadableException: JSON parse error: Cannot deserialize value of type...",
        "fix_code": "请求体 JSON 反序列化失败：\n1. 前端发送的字段类型与后端 DTO 不匹配（发送 string 给 int 字段）\n2. 枚举值不匹配 → 检查前端发送的值是否在 enum 定义中\n3. 日期格式不一致 → 使用 @JsonFormat(pattern = \"yyyy-MM-dd\") 指定格式\n4. 未知属性 → @JsonIgnoreProperties(ignoreUnknown = true) 忽略多余字段\n5. 确保请求 Content-Type: application/json",
        "occurrence_count": 3,
    },
    {
        "error_signature": "NoSuchBeanDefinitionException: No qualifying bean of type 'com.example.UserRepository' available",
        "fix_code": "Spring Bean 未找到的排查：\n1. 检查类是否标注 @Repository / @Service / @Component / @Bean\n2. 确认 @SpringBootApplication 在根包下（组件扫描从该类所在包开始）\n3. 接口实现类必须有 @Component 或 @Service 注解\n4. JPA Repository 接口不需要注解，但需要 @EnableJpaRepositories 配置\n5. 多模块项目检查 @ComponentScan basePackages",
        "occurrence_count": 4,
    },
    {
        "error_signature": "MethodArgumentNotValidException: Validation failed for argument [0] in method...",
        "fix_code": "请求参数校验失败：\n1. 确保 @Valid 或 @Validated 注解在 Controller 方法参数上\n2. DTO 字段注解 @NotNull / @NotBlank / @Size 是否正确\n3. 全局异常处理器捕获 MethodArgumentNotValidException 返回 400 和字段级错误\n4. BindingResult 可在 Controller 方法中手动获取错误详情\n5. 嵌套校验：List<@Valid Item> items 必须添加 @Valid",
        "occurrence_count": 3,
    },
    # ---- Go ----
    {
        "error_signature": "panic: runtime error: invalid memory address or nil pointer dereference",
        "fix_code": "Go 空指针解引用是最常见 panic：\n1. 函数返回指针时检查 nil：user, err := repo.FindByID(id); if err != nil { ... }; if user == nil { return ErrNotFound }\n2. 结构体字段为指针类型时，使用前检查 nil\n3. interface 变量可能为 nil 但有类型信息 → 用 reflect 或直接判 nil\n4. json.Unmarshal 前确保目标 struct 已初始化（new() 或 &T{}）\n5. 用竞争检测器排查并发写入：go run -race main.go",
        "occurrence_count": 5,
    },
    {
        "error_signature": "sql: no rows in result set (Scan / QueryRow without error check)",
        "fix_code": "QueryRow().Scan() 返回 sql.ErrNoRows 时表示没有匹配记录：\nvar user User\nerr := db.QueryRow(\"SELECT * FROM users WHERE id = $1\", id).Scan(&user)\nif errors.Is(err, sql.ErrNoRows) {\n    return nil, ErrNotFound  // 业务层处理\n}\n# 不要忽略 QueryRow 的 Scan 错误，否则 user 为零值（id=0, name=\"\"）导致逻辑错误",
        "occurrence_count": 4,
    },
    {
        "error_signature": "cannot use X (type Y) as type Z in argument / assignment",
        "fix_code": "Go 类型不兼容错误（Go 不支持隐式类型转换）：\n1. int 和 int64 不兼容 → int64(x) 显式转换\n2. []MyType 和 []interface{} 不兼容 → 需要逐元素转换\n3. *User 和 User 不兼容 → 解引用 *user 或取地址 &user\n4. interface{} 转具体类型 → v, ok := val.(User) 类型断言\n5. 函数类型不匹配 → 确保参数和返回值类型完全一致",
        "occurrence_count": 3,
    },
    {
        "error_signature": "fatal error: all goroutines are asleep - deadlock!",
        "fix_code": "Goroutine 死锁常见场景：\n1. 无缓冲 channel 上阻塞发送但没有接收者 → 使用 buffered channel 或 goroutine 接收\n2. sync.WaitGroup 的 Add 和 Done 不匹配 → Add(1) 后必须调用 Done()\n3. 同一个 goroutine 中 Lock() 两次（非可重入锁） → 使用 sync.RWMutex\n4. channel 已关闭但仍向其中发送（panic: send on closed channel）\n5. select {} 空 select 永久阻塞 → 加 default 分支或 timeout",
        "occurrence_count": 3,
    },
    {
        "error_signature": "import cycle not allowed: package a imports package b imports package a",
        "fix_code": "Go 禁止循环导入。解决方法：\n1. 提取公共接口到独立包（如 types/ 或 interfaces/）\n2. 用接口解耦：A 定义接口，B 实现接口，A 依赖接口而非 B\n3. 合并循环依赖的包\n4. 使用依赖反转：高层模块定义接口，低层模块实现\n# 示例：handler 包定义 UserService interface，service 包实现，handler 依赖 interface 而非 service 包",
        "occurrence_count": 4,
    },
    {
        "error_signature": "undefined: X (compiler) / missing import",
        "fix_code": "Go 编译器报 undefined：\n1. 未导入包 → import \"package/path\"\n2. 标识符未导出（小写开头）→ 改为大写开头使其公开\n3. 变量在 if/for 块内声明，外部访问 → 在块外声明\n4. 拼写错误 → 检查大小写和字母\n5. go.sum 缺失 → go mod tidy 同步依赖",
        "occurrence_count": 3,
    },
    # ---- Node.js ----
    {
        "error_signature": "Error [ERR_HTTP_HEADERS_SENT]: Cannot set headers after they are sent to the client",
        "fix_code": "Express 在响应已发送后再次尝试发送响应：\n1. 确保每个路由只调用一次 res.json() / res.send() / res.end()\n2. if-else 中遗漏 return：\n   if (!user) { res.status(404).json({error: 'Not found'}); return; }  // 别忘了 return\n3. 异步回调中多次响应 → 使用 async/await + try-catch\n4. 中间件中调用 next() 后又调用 res.send() → 二选一",
        "occurrence_count": 4,
    },
    {
        "error_signature": "TypeError: Cannot read properties of undefined (reading 'xxx')",
        "fix_code": "JS 访问 undefined/null 的属性：\n1. 使用可选链：user?.profile?.address?.city ?? '未知'\n2. 解构前给默认值：const { name = '' } = user || {}\n3. API 响应数据先校验：if (!data || !data.items) return []\n4. TypeScript 严格模式启用 strictNullChecks\n5. 数组方法前检查：items?.map(...)  // 安全访问",
        "occurrence_count": 5,
    },
    {
        "error_signature": "Error: connect ECONNREFUSED ::1:5432 (PostgreSQL / Redis 连接被拒)",
        "fix_code": "数据库连接被拒绝排查：\n1. 确认数据库服务正在运行：systemctl status postgresql\n2. 检查 host/port 配置是否正确（localhost vs 127.0.0.1 vs Docker 服务名）\n3. Docker Compose 中用服务名而非 localhost：DATABASE_URL=postgresql://user:pass@db:5432/mydb\n4. 防火墙/安全组是否放行端口\n5. PostgreSQL pg_hba.conf 是否允许连接\n6. 数据库连接池上限是否达到 max_connections",
        "occurrence_count": 4,
    },
    {
        "error_signature": "PrismaClientInitializationError: Can't reach database server at `localhost:5432` / P1001",
        "fix_code": "Prisma 连接数据库失败：\n1. 检查 .env 中 DATABASE_URL 格式\n2. 运行 `npx prisma db push` 验证连接\n3. Docker 环境用服务名：postgresql://user:pass@postgres:5432/db\n4. 确保数据库已创建：`npx prisma db push` 或 `npx prisma migrate dev`\n5. 检查 Prisma schema 的 datasource provider 与实际数据库一致（postgresql/mysql/sqlite）",
        "occurrence_count": 3,
    },
    # ---- Rust ----
    {
        "error_signature": "error[E0382]: borrow of moved value: `user` (value moved into closure / function)",
        "fix_code": "Rust 所有权移动后继续使用：\n1. 使用 clone() 显式复制：let user2 = user.clone()\n2. 传递引用而非所有权：fn process(user: &User) 而非 fn process(user: User)\n3. 实现 Copy trait（小型数据结构）\n4. 使用 Rc<T> 或 Arc<T> 共享所有权\n5. 闭包中使用 move 但外部仍需变量 → 先 clone 再 move\n6. 模式匹配中 ref 绑定：Some(ref user) 而非 Some(user)",
        "occurrence_count": 4,
    },
    {
        "error_signature": "error[E0277]: the trait bound `CreateUserRequest: Deserialize<'_>` is not satisfied",
        "fix_code": "Serde 反序列化 trait 未实现：\n1. 添加 #[derive(Deserialize)] 注解\n2. 嵌套类型也需实现 Deserialize\n3. serde 依赖未添加到 Cargo.toml（需启用 derive feature）：\n   serde = { version = \"1\", features = [\"derive\"] }\n4. 泛型约束：where T: Deserialize<'de>\n5. actix-web / axum 的 Json<T> 要求 T: DeserializeOwned",
        "occurrence_count": 3,
    },
    {
        "error_signature": "error[E0277]: the trait bound `fn(State<AppState>, Json<CreateUserReq>) -> impl Future<Output = impl Responder> {handler}: Handler<_>` is not satisfied",
        "fix_code": "Handler 函数签名与路由期望不匹配：\n1. Actix-web: 参数必须是实现 FromRequest 的类型（web::Json, web::Path, web::Data 等），不能有额外参数\n2. Axum: 参数必须是实现 FromRequestParts 或 FromRequest 的类型（State, Json, Path, Query）\n3. 返回类型必须实现 Responder / IntoResponse\n4. 检查参数顺序：State 通常放第一位\n5. 确保所有参数类型都实现了对应的 extractor trait\n6. async fn 的 Future 必须 Send + 'static（检查是否引用了非 Send 类型）",
        "occurrence_count": 3,
    },
]