from __future__ import annotations

import re
from typing import Any


_REDACTED = "***REDACTED***"
_REDACTED_USER_PATH = "***REDACTED_USER_PATH***"
_SENSITIVE_KEY_SUFFIX = re.compile(
    r"(?:^|[_.-])(?:password|token|api[_-]?key|private[_-]?key|"
    r"authorization|secret|cookie|access[_-]?token|refresh[_-]?token|"
    r"auth[_-]?token|apikey|privatekey|accesstoken|refreshtoken|authtoken)$",
    re.IGNORECASE,
)
_BEARER = re.compile(r"\bBearer\s+[^\s,;\"']+", re.IGNORECASE)
_BASIC = re.compile(r"\bBasic\s+[^\s,;\"']+", re.IGNORECASE)
_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}")
_CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?P<prefix>\b(?P<key>[A-Za-z][A-Za-z0-9_.-]*)[\"']?\s*[:=]\s*)"
    r"(?:(?:Bearer|Basic)\s+[^\s,;\"']+|(?P<double>\"[^\"\r\n]*\")|"
    r"(?P<single>'[^'\r\n]*')|[^\s,;\"')\]}]+)",
    re.IGNORECASE,
)
_CONNECTION_URI = re.compile(
    r"\b(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*://)[^@/\s\"']+@",
)
_WINDOWS_USER_PATH = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]+Users[\\/]+[^\"'\r\n,;)\]}]+",
    re.IGNORECASE,
)
_UNIX_USER_PATH = re.compile(
    r"(?<![A-Za-z0-9_])/(?:home|Users)/[^\"'\r\n,;)\]}]+",
)


def _is_sensitive_key(value: str) -> bool:
    segmented = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value.strip("\"'"))
    segmented = re.sub(r"\s+", "_", segmented)
    return _SENSITIVE_KEY_SUFFIX.search(segmented) is not None


def _redact_text(value: str) -> str:
    redacted = _CONNECTION_URI.sub(
        lambda match: f"{match.group('scheme')}{_REDACTED}:{_REDACTED}@",
        value,
    )

    def replace_assignment(match: re.Match[str]) -> str:
        if not _is_sensitive_key(match.group("key")):
            return match.group(0)
        quoted = match.group("double") or match.group("single")
        replacement = f"{quoted[0]}{_REDACTED}{quoted[-1]}" if quoted else _REDACTED
        return f"{match.group('prefix')}{replacement}"

    redacted = _CREDENTIAL_ASSIGNMENT.sub(replace_assignment, redacted)
    redacted = _BEARER.sub(f"Bearer {_REDACTED}", redacted)
    redacted = _BASIC.sub(f"Basic {_REDACTED}", redacted)
    redacted = _SECRET.sub(_REDACTED, redacted)
    redacted = _WINDOWS_USER_PATH.sub(_REDACTED_USER_PATH, redacted)
    return _UNIX_USER_PATH.sub(_REDACTED_USER_PATH, redacted)


def redact(value: Any) -> Any:
    """Recursively redact secrets and user-specific absolute paths."""
    if isinstance(value, dict):
        return {
            key: (
                _REDACTED
                if _is_sensitive_key(str(key))
                else redact(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def redact_error(error: BaseException | str) -> str:
    """Return a redacted, human-readable exception message."""
    return _redact_text(str(error))
