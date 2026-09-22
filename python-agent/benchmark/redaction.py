from __future__ import annotations
import re
from typing import Any
_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|access[_-]?token|password|secret|authorization|cookie)$", re.I)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")
def redact(value: Any) -> Any:
    if isinstance(value, dict): return {key: "***REDACTED***" if _SENSITIVE_KEY.search(str(key)) else redact(item) for key, item in value.items()}
    if isinstance(value, list): return [redact(item) for item in value]
    if isinstance(value, tuple): return tuple(redact(item) for item in value)
    if isinstance(value, str): return _SECRET.sub("***REDACTED***", _BEARER.sub("Bearer ***REDACTED***", value))
    return value
