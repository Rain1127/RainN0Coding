import importlib


PROTECTED_FILE_NAMES = frozenset(
    {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pyproject.toml",
        "pom.xml",
        "vite.config.js",
        "vite.config.ts",
        "main.ts",
        "main.js",
        "App.vue",
    }
)

SENSITIVE_FILE_MARKERS = frozenset(
    {
        ".env",
        ".pem",
        ".key",
        ".p12",
        "id_rsa",
        "id_ed25519",
        ".ssh",
    }
)

ALLOWED_WRITE_EXTENSIONS = frozenset(
    {
        ".vue",
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".json",
        ".css",
        ".scss",
        ".md",
        ".html",
        ".py",
        ".java",
        ".go",
        ".rs",
        ".yaml",
        ".yml",
    }
)

ELEVATED_SCRIPT_EXTENSIONS = frozenset({".sh", ".bat", ".cmd", ".ps1"})

HIGH_RISK_PROMPT_PATTERNS = (
    r"(?i)\bread\s+\.env\b",
    r"(?i)\bread\s+.*env(ironment)?\s*var(iable)?s?\s*file\b",
    r"(?i)\bread\s+.*ssh\s+key\b",
    r"(?i)\bdelete\s+all\s+files\b",
    r"(?i)\bwipe\s+project\b",
    r"(?i)\brm\s+-rf\b",
    r"(?i)\bwrite\s+outside\s+project\b",
    r"读取\s*\.env",
    r"读取.*环境变量文件",
    r"读取.*ssh.*key",
    r"删除全部文件",
    r"清空项目",
    r"写入项目外部",
)

MEDIUM_RISK_PROMPT_PATTERNS = (
    r"(?i)\boverwrite\s+package\.json\b",
    r"(?i)\boverwrite\s+pyproject\.toml\b",
    r"(?i)\bcreate\s+powershell\s+script\b",
    r"(?i)\bcreate\s+shell\s+script\b",
    r"覆盖\s*package\.json",
    r"覆盖\s*pyproject\.toml",
    r"创建\s*PowerShell\s*脚本",
    r"创建\s*shell\s*脚本",
)


def max_prompt_chars() -> int:
    return _current_config().GUARDRAILS_MAX_PROMPT_CHARS


def max_file_write_bytes() -> int:
    return _current_config().GUARDRAILS_MAX_FILE_WRITE_BYTES


def max_modify_replacement_bytes() -> int:
    return _current_config().GUARDRAILS_MAX_MODIFY_REPLACEMENT_BYTES


def max_list_files_depth() -> int:
    return _current_config().GUARDRAILS_MAX_LIST_FILES_DEPTH


def _current_config():
    return importlib.import_module("config").config
