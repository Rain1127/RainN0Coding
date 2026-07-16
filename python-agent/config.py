"""全局配置 —— 所有模块通过 Config 单例读取环境变量"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ===== DeepSeek API =====
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    CHAT_MODEL: str = os.getenv("CHAT_MODEL", "deepseek-chat")  # 结构化输出用（v4-pro 不支持 json_mode）
    REASONING_MODEL: str = os.getenv("REASONING_MODEL", "deepseek-v4-pro")

    # ===== GLM 备用模型 =====
    ZHIPU_API_KEY: str = os.getenv("ZHIPU_API_KEY", "")
    ZHIPU_BASE_URL: str = os.getenv("ZHIPU_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    ZHIPU_FLASH_MODEL: str = os.getenv("ZHIPU_FLASH_MODEL", "glm-4.7-flash")

    # ===== LLM 通用参数 =====
    LLM_TEMPERATURE: float = 0.1          # 代码生成需要低温度
    LLM_TEMPERATURE_STRUCTURED: float = 0.0  # 结构化输出用 0 温度
    LLM_MAX_TOKENS: int = 8192
    LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "120"))     # LLM 调用超时（秒）
    LLM_FALLBACK_TIMEOUT: int = int(os.getenv("LLM_FALLBACK_TIMEOUT", "60"))  # fallback 模型超时

    # ===== LangSmith 监控 =====
    LANGSMITH_TRACING: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    LANGSMITH_API_KEY: str = os.getenv("LANGSMITH_API_KEY", "")
    LANGSMITH_ENDPOINT: str = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    LANGSMITH_PROJECT: str = os.getenv("LANGSMITH_PROJECT", "RainN0Coding")

    # ===== 熔断器 =====
    CB_FAILURE_THRESHOLD: int = 3         # 连续失败 N 次后熔断
    CB_COOLDOWN_SECONDS: int = 30         # 熔断后冷却时间（秒）

    # ===== Milvus =====
    MILVUS_HOST: str = os.getenv("MILVUS_HOST", "localhost")
    MILVUS_PORT: int = int(os.getenv("MILVUS_PORT", "19530"))

    # ===== Embedding =====
    LOCAL_EMBEDDING_ENABLED: bool = os.getenv("LOCAL_EMBEDDING_ENABLED", "false").lower() == "true"
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

    # ===== 重试 =====
    MAX_RETRIES: int = 3
    AUTO_GEN_MAX_ROUNDS: int = 8

    # ===== 服务 =====
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    JAVA_BASE_URL: str = os.getenv("JAVA_BASE_URL", "http://localhost:8123").rstrip("/")
    APP_ENV: str = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
    INTERNAL_API_TOKEN: str = os.getenv("INTERNAL_API_TOKEN", "")
    INTERNAL_API_ALLOW_MISSING_TOKEN: bool = os.getenv(
        "INTERNAL_API_ALLOW_MISSING_TOKEN",
        "true" if APP_ENV in {"dev", "development", "local", "test"} else "false",
    ).lower() == "true"
    AGENT_MAX_CONCURRENT_REQUESTS: int = int(os.getenv("AGENT_MAX_CONCURRENT_REQUESTS", "4"))
    AGENT_OVERLOAD_STATUS_CODE: int = int(os.getenv("AGENT_OVERLOAD_STATUS_CODE", "429"))
    AGENT_RESILIENCE_ENABLED: bool = os.getenv("AGENT_RESILIENCE_ENABLED", "true").lower() == "true"
    AGENT_PHASE_TIMEOUT_SHORT_SECONDS: int = int(os.getenv("AGENT_PHASE_TIMEOUT_SHORT_SECONDS", "30"))
    AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS: int = int(os.getenv("AGENT_PHASE_TIMEOUT_MEDIUM_SECONDS", "90"))
    AGENT_PHASE_TIMEOUT_LONG_SECONDS: int = int(os.getenv("AGENT_PHASE_TIMEOUT_LONG_SECONDS", "240"))

    # ===== Guardrails =====
    GUARDRAILS_ENABLED: bool = os.getenv("GUARDRAILS_ENABLED", "true").lower() == "true"
    GUARDRAILS_AUDIT_LOW_RISK: bool = os.getenv("GUARDRAILS_AUDIT_LOW_RISK", "false").lower() == "true"
    GUARDRAILS_MAX_PROMPT_CHARS: int = int(os.getenv("GUARDRAILS_MAX_PROMPT_CHARS", "12000"))
    GUARDRAILS_MAX_FILE_WRITE_BYTES: int = int(os.getenv("GUARDRAILS_MAX_FILE_WRITE_BYTES", "200000"))
    GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES: int = int(
        os.getenv("GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES", "120000")
    )
    GUARDRAILS_MAX_LIST_FILES_DEPTH: int = int(os.getenv("GUARDRAILS_MAX_LIST_FILES_DEPTH", "6"))

    # ===== RAGAS 离线评估 =====
    RAGAS_JUDGE_MODEL: str = os.getenv("RAGAS_JUDGE_MODEL", DEEPSEEK_MODEL)  # Judge LLM 模型名，默认用 DEEPSEEK_MODEL
    RAGAS_JUDGE_TEMPERATURE: float = 0.0  # Judge 使用 0 温度确保确定性

    # ===== RAG 检索引擎 =====
    MILVUS_MODE: str = os.getenv("MILVUS_MODE", "lite")  # "lite" | "standalone"
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "8"))    # 重排序后保留的最大结果数
    RAG_SEMANTIC_DEDUP_THRESHOLD: float = float(os.getenv("RAG_DEDUP_THRESHOLD", "0.95"))
    RAG_PARALLEL_WORKERS: int = int(os.getenv("RAG_PARALLEL_WORKERS", "5"))  # 并行检索线程数

    # ===== Hybrid grep+RAG 引擎 =====
    SQLITE_DB_PATH: str = os.getenv("SQLITE_DB_PATH", "rag_data/exact_search.db")
    CODE_STORE_DIR: str = os.getenv("CODE_STORE_DIR", "verified_code")
    USE_HYBRID_ENGINE: bool = os.getenv("USE_HYBRID_ENGINE", "true").lower() == "true"  # False 回退原引擎

    # ===== RAG 缓存 =====
    RAG_CACHE_TTL_COLD: int = int(os.getenv("RAG_CACHE_TTL_COLD", "1800"))    # 冷查询缓存 TTL，默认 30 分钟
    RAG_CACHE_TTL_HOT: int = int(os.getenv("RAG_CACHE_TTL_HOT", "7200"))      # 热查询缓存 TTL，默认 2 小时
    RAG_HOT_QUERY_WINDOW: int = int(os.getenv("RAG_HOT_QUERY_WINDOW", "600"))   # 热度统计窗口，默认 10 分钟
    RAG_HOT_QUERY_THRESHOLD: int = int(os.getenv("RAG_HOT_QUERY_THRESHOLD", "10"))  # 窗口内达到此次数标记为热查询

    # ===== Redis =====
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))

    # ===== 会话记忆 =====
    MEMORY_WINDOW_SIZE: int = int(os.getenv("MEMORY_WINDOW_SIZE", "10"))        # 滑动窗口大小
    MEMORY_SUMMARY_TRIGGER: int = int(os.getenv("MEMORY_SUMMARY_TRIGGER", "15"))  # 触发摘要的消息数阈值
    MEMORY_REDIS_TTL_SECONDS: int = int(os.getenv("MEMORY_REDIS_TTL_SECONDS", "2592000"))  # Redis 会话过期时间，默认 30 天

    # ===== 质量门禁 (Quality Gates) =====
    QUALITY_SCORE_THRESHOLD: int = int(os.getenv("QUALITY_SCORE_THRESHOLD", "80"))           # Review 最低分阈值
    QUALITY_MIN_AGE_DAYS: int = int(os.getenv("QUALITY_MIN_AGE_DAYS", "30"))                 # 清理最小存活天数
    QUALITY_CLEANUP_INTERVAL_HOURS: int = int(os.getenv("QUALITY_CLEANUP_INTERVAL_HOURS", "24"))  # 清理周期间隔
    QUALITY_INITIAL_SCORE: float = float(os.getenv("QUALITY_INITIAL_SCORE", "70.0"))          # 新入库初始质量分
    QUALITY_BOOST_ON_SUCCESS: float = float(os.getenv("QUALITY_BOOST_ON_SUCCESS", "5.0"))     # 构建成功加分
    QUALITY_PENALTY_ON_FAILURE: float = float(os.getenv("QUALITY_PENALTY_ON_FAILURE", "10.0"))  # 构建失败扣分

    # ===== 项目目录 =====
    CODE_OUTPUT_DIR: str = "/tmp/ai-code-project"


# ===== 多语言技术栈注册表 =====
# 每个 code_gen_type 对应的技术栈规范，供 Agent 动态生成提示词。
LANGUAGE_CONFIGS: dict[str, dict] = {
    "vue_project": {
        "label": "Vue 3 前端",
        "role": "前端程序员",
        "arch_role": "前端架构师",
        "review_role": "前端代码审查专家",
        "framework": "Vue 3 Composition API + <script setup lang=\"ts\">",
        "lang": "TypeScript 严格模式",
        "css": "Tailwind CSS v3 (utility-first)",
        "state": "Pinia",
        "router": "Vue Router 4",
        "build_tool": "Vite",
        "pkg_manager": "npm",
        "file_ext": ".vue",
        "entry": "src/main.ts",
        "test": "Vitest",
        "is_frontend": True,
        "needs_npm_build": True,
        "code_style_rules": [
            "每个 .vue 文件必须包含三个块：<template> + <script setup lang=\"ts\"> + <style scoped>",
            "Props 用 defineProps<T>() 泛型写法",
            "Emits 用 defineEmits<T>() 泛型写法",
            "ref 和 reactive 带泛型参数：ref<Type>(initialValue)",
            "路由配置使用懒加载：component: () => import('@/views/...')",
            "跨组件共享状态放在 Pinia store 中",
            "import 路径以 @/ 或 ./ 开头",
        ],
    },
    "html": {
        "label": "原生 HTML",
        "role": "前端程序员",
        "arch_role": "前端架构师",
        "review_role": "前端代码审查专家",
        "framework": "原生 HTML5 + 内联 CSS + JavaScript",
        "lang": "JavaScript (ES6+)",
        "file_ext": ".html",
        "is_frontend": True,
        "needs_npm_build": False,
        "code_style_rules": [
            "单个 HTML 文件，内联 <style> 和 <script>",
            "语义化 HTML5 标签",
            "CSS 使用 Flexbox/Grid 布局",
        ],
    },
    "multi_file": {
        "label": "原生多文件",
        "role": "前端程序员",
        "arch_role": "前端架构师",
        "review_role": "前端代码审查专家",
        "framework": "原生 HTML5 + CSS3 + JavaScript (ES6+)",
        "lang": "JavaScript (ES6+)",
        "file_ext": ".html/.css/.js",
        "is_frontend": True,
        "needs_npm_build": False,
        "code_style_rules": [
            "分离 index.html、style.css、script.js",
            "CSS 使用 Flexbox/Grid 布局",
            "JavaScript 使用 ES6+ 模块化写法",
        ],
    },
    "python": {
        "label": "Python 后端",
        "role": "Python 后端开发工程师",
        "arch_role": "Python 系统架构师",
        "review_role": "Python 代码审查专家",
        "framework": "FastAPI / Flask",
        "lang": "Python 3.12+ with type hints",
        "build_tool": "uv / pip",
        "pkg_manager": "uv / pip",
        "file_ext": ".py",
        "entry": "main.py",
        "test": "pytest",
        "is_frontend": False,
        "needs_npm_build": False,
        "needs_syntax_check": True,
        "syntax_check_cmd": 'python -m py_compile "{file}"',
        "syntax_check_file_glob": "*.py",
        "syntax_check_per_file": True,
        "syntax_check_timeout": 60,
        "code_style_rules": [
            "所有函数参数和返回值必须有类型注解",
            "用 Pydantic 定义数据模型",
            "用 async/await 处理异步 I/O",
            "遵循 PEP 8 代码风格",
            "用 pytest 编写测试",
            "requirements.txt 或 pyproject.toml 声明依赖",
        ],
    },
    "java": {
        "label": "Java 后端",
        "role": "Java 后端开发工程师",
        "arch_role": "Java 系统架构师",
        "review_role": "Java 代码审查专家",
        "framework": "Spring Boot 3.x (Maven/Gradle)",
        "lang": "Java 21",
        "build_tool": "Maven / Gradle",
        "pkg_manager": "Maven / Gradle",
        "file_ext": ".java",
        "entry": "src/main/java/.../Application.java",
        "test": "JUnit 5 + Mockito",
        "is_frontend": False,
        "needs_npm_build": False,
        "needs_syntax_check": True,
        "syntax_check_cmd": 'javac -d "{tmpdir}" {files}',
        "syntax_check_file_glob": "*.java",
        "syntax_check_per_file": False,
        "syntax_check_timeout": 120,
        "code_style_rules": [
            "使用 Lombok 简化 POJO (@Data, @Builder)",
            "Controller → Service → Repository 分层",
            "用 @Valid / @Validated 校验参数",
            "异常统一用 @RestControllerAdvice 处理",
            "用 JUnit 5 + MockMvc 编写测试",
            "Maven pom.xml 或 Gradle build.gradle 声明依赖",
        ],
    },
    "go": {
        "label": "Go 后端",
        "role": "Go 后端开发工程师",
        "arch_role": "Go 系统架构师",
        "review_role": "Go 代码审查专家",
        "framework": "Gin / 标准库 net/http",
        "lang": "Go 1.22+",
        "build_tool": "go build",
        "pkg_manager": "go mod",
        "file_ext": ".go",
        "entry": "main.go",
        "test": "testing + testify",
        "is_frontend": False,
        "needs_npm_build": False,
        "needs_syntax_check": True,
        "syntax_check_cmd": 'go vet ./...',
        "syntax_check_file_glob": None,
        "syntax_check_per_file": False,
        "syntax_check_timeout": 120,
        "code_style_rules": [
            "遵循 Effective Go 和 Go Code Review Comments",
            "错误处理：if err != nil { return ... }",
            "用 context.Context 传递请求上下文",
            "包名简洁（小写，单数）",
            "go.mod 声明模块路径和依赖",
            "小写开头 = 包内可见，大写开头 = 公开",
        ],
    },
    "rust": {
        "label": "Rust 后端",
        "role": "Rust 后端开发工程师",
        "arch_role": "Rust 系统架构师",
        "review_role": "Rust 代码审查专家",
        "framework": "Actix-web / Axum",
        "lang": "Rust 2021 edition",
        "build_tool": "Cargo",
        "pkg_manager": "cargo",
        "file_ext": ".rs",
        "entry": "src/main.rs",
        "test": "cargo test",
        "is_frontend": False,
        "needs_npm_build": False,
        "needs_syntax_check": True,
        "syntax_check_cmd": 'cargo check 2>&1',
        "syntax_check_file_glob": None,
        "syntax_check_per_file": False,
        "syntax_check_timeout": 120,
        "code_style_rules": [
            "遵循 Rust API Guidelines 和 std::prelude",
            "用 Result<T, E> 和 ? 运算符处理错误",
            "用 serde 做序列化/反序列化",
            "Cargo.toml 声明依赖和版本",
            "#[derive(Debug, Clone, Serialize, Deserialize)] 常用",
            "注意所有权和借用规则",
        ],
    },
    "nodejs": {
        "label": "Node.js 后端",
        "role": "Node.js 后端开发工程师",
        "arch_role": "Node.js 系统架构师",
        "review_role": "Node.js 代码审查专家",
        "framework": "Express / NestJS",
        "lang": "TypeScript 严格模式",
        "build_tool": "tsc / ts-node",
        "pkg_manager": "npm / yarn / pnpm",
        "file_ext": ".ts",
        "entry": "src/index.ts",
        "test": "Jest + Supertest",
        "is_frontend": False,
        "needs_npm_build": True,
        "code_style_rules": [
            "所有变量、函数参数、返回值必须有类型注解",
            "用 async/await 处理异步操作",
            "用 ESLint + Prettier 统一代码风格",
            "package.json 声明依赖和脚本",
            "用 Jest + Supertest 编写集成测试",
        ],
    },
    "generic": {
        "label": "通用",
        "role": "全栈工程师",
        "arch_role": "系统架构师",
        "review_role": "代码审查专家",
        "framework": "根据需求自行判断最佳技术栈",
        "lang": "根据需求自行选择",
        "is_frontend": False,
        "needs_npm_build": False,
        "code_style_rules": [],
    },
}


def get_lang_config(code_gen_type: str | None) -> dict:
    """根据 code_gen_type 获取语言配置，默认返回 generic。"""
    if not code_gen_type:
        return LANGUAGE_CONFIGS["generic"]
    return LANGUAGE_CONFIGS.get(code_gen_type, LANGUAGE_CONFIGS["generic"])


config = Config()
