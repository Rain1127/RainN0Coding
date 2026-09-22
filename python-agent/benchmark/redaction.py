from __future__ import annotations
import re
from typing import Any
_SENSITIVE_KEY = re.compile(r"(?:apikey|accesstoken|password|secret|authorization|cookie|token|refreshtoken|authtoken|privatekey)$", re.I)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")
_CREDENTIAL_VALUE = re.compile(r"(?i)\b(password|token|apikey|api_key|privatekey|private_key|secret|authorization)\s*([=:])\s*(?:Basic\s+)?[^\s,;]+")
_BASIC = re.compile(r"(?i)\bBasic\s+[^\s,;]+")
def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "***REDACTED***" if _SENSITIVE_KEY.search(re.sub(r"[_\-\s]", "", str(key))) else redact(item) for key, item in value.items()}
    if isinstance(value, list): return [redact(item) for item in value]
    if isinstance(value, tuple): return tuple(redact(item) for item in value)
    if isinstance(value, str): return _SECRET.sub("***REDACTED***", _BEARER.sub("Bearer ***REDACTED***", value))
    return value


def redact_error(error: BaseException | str) -> str:
    """Return a safe, human-readable exception message for reports and the CLI."""
    message = str(error)
    message = str(redact(message))
    message = _BASIC.sub("Basic ***REDACTED***", message)
    return _CREDENTIAL_VALUE.sub(lambda match: f"{match.group(1)}{match.group(2)}***REDACTED***", message)
