from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmark.redaction import redact_error


SAFE_ENV_KEYS = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP")
MAX_LOG_CHARACTERS = 4000
MAX_TIMEOUT_SECONDS = 600
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9


def _relative_generated_path(raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"unsafe generated path: {raw_path!r}")
    relative = Path(raw_path)
    if (
        not relative.parts
        or relative.is_absolute()
        or bool(relative.drive)
        or any(part in {"", ".", ".."} for part in relative.parts)
        or any(part.rstrip(" .") != part for part in relative.parts)
        or relative.is_reserved()
    ):
        raise ValueError(f"unsafe generated path: {raw_path}")
    return relative


def validate_generated_files(files: object) -> list[tuple[Path, str]]:
    if not isinstance(files, list):
        raise ValueError("generated files must be a list")

    validated: list[tuple[Path, str]] = []
    logical_paths: set[str] = set()
    for item in files:
        if not isinstance(item, Mapping) or set(item) != {"path", "content"}:
            raise ValueError("generated file must contain exactly path and content strings")
        if not isinstance(item["path"], str):
            raise ValueError("generated file must contain exactly path and content strings")
        relative = _relative_generated_path(item["path"])
        content = item["content"]
        if not isinstance(content, str):
            raise ValueError("generated file must contain exactly path and content strings")
        logical = os.path.normcase(str(relative))
        if logical in logical_paths:
            raise ValueError(f"generated path collision: {relative}")
        for prior in logical_paths:
            if logical.startswith(prior + os.sep) or prior.startswith(logical + os.sep):
                raise ValueError(f"generated path collision: {relative}")
        logical_paths.add(logical)
        validated.append((relative, content))
    return validated


def _confined(path: Path, root: Path, relative: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"unsafe generated path: {relative}") from exc
    return resolved


def materialize_files(files: list[dict[str, Any]], project_dir: str | Path) -> list[Path]:
    validated = validate_generated_files(files)
    root_path = Path(project_dir)
    root_path.mkdir(parents=True, exist_ok=True)
    root = root_path.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("project_dir must be a directory")

    targets: list[tuple[Path, Path, str]] = []
    canonical_targets: set[str] = set()
    for relative, content in validated:
        target = _confined(root / relative, root, relative)
        canonical = os.path.normcase(str(target))
        if canonical in canonical_targets:
            raise ValueError(f"generated path collision: {relative}")
        for prior in canonical_targets:
            if canonical.startswith(prior + os.sep) or prior.startswith(canonical + os.sep):
                raise ValueError(f"generated path collision: {relative}")
        canonical_targets.add(canonical)
        targets.append((relative, target, content))

    written: list[Path] = []
    for relative, target, content in targets:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except (FileExistsError, NotADirectoryError) as exc:
            raise ValueError(f"generated path collision: {relative}") from exc
        _confined(target.parent, root, relative)
        target = _confined(target, root, relative)
        if target.exists() or target.is_symlink():
            raise ValueError(f"generated path collision: {relative}")
        try:
            with target.open("x", encoding="utf-8") as stream:
                stream.write(content)
        except FileExistsError as exc:
            raise ValueError(f"generated path collision: {relative}") from exc
        _confined(target, root, relative)
        written.append(target)
    return written


def _create_windows_kill_job(process: subprocess.Popen[str]) -> int | None:
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    information = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    information.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    configured = kernel32.SetInformationJobObject(
        job,
        _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(information),
        ctypes.sizeof(information),
    )
    assigned = configured and kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle)))
    if not assigned:
        kernel32.CloseHandle(job)
        return None
    return int(job)


def _close_windows_job(job: int | None, *, terminate: bool = False) -> None:
    if os.name != "nt" or job is None:
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    if terminate:
        kernel32.TerminateJobObject(wintypes.HANDLE(job), 1)
    kernel32.CloseHandle(wintypes.HANDLE(job))


def _kill_windows_process_tree(
    process: subprocess.Popen[str], environment: dict[str, str], job: int | None
) -> None:
    if job is not None:
        _close_windows_job(job, terminate=True)
        return
    helper: subprocess.Popen[str] | None = None
    try:
        helper = subprocess.Popen(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env=environment,
        )
        try:
            helper.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            helper.kill()
            helper.communicate(timeout=1)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        if helper is not None and helper.poll() is None:
            helper.kill()
    finally:
        if process.poll() is None:
            process.kill()


def _terminate_process_tree(
    process: subprocess.Popen[str], environment: dict[str, str], windows_job: int | None
) -> None:
    if os.name == "nt":
        _kill_windows_process_tree(process, environment, windows_job)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        if process.poll() is None:
            process.kill()


def _communicate_after_termination(process: subprocess.Popen[str]) -> tuple[str, str]:
    try:
        return process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            process.kill()
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        return "", ""


def _validate_execution(command: object, timeout_seconds: object) -> tuple[list[str], int]:
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(item, str) and item.strip() for item in command)
    ):
        raise ValueError("execution command must be a non-empty string list")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, int)
        or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS
    ):
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    return list(command), timeout_seconds


def evaluate_code(
    files: list[dict[str, Any]],
    project_dir: str | Path,
    command: list[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    safe_command, safe_timeout = _validate_execution(command, timeout_seconds)
    materialize_files(files, project_dir)
    environment = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    environment.update({"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    windows_job: int | None = None
    windows_job_closed = False
    try:
        options: dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        process = subprocess.Popen(
            safe_command,
            cwd=Path(project_dir).resolve(),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            **options,
        )
        windows_job = _create_windows_kill_job(process)
        stdout, stderr = process.communicate(timeout=safe_timeout)
    except FileNotFoundError:
        return {
            "passed": False,
            "metric": "build_failed",
            "log": "",
            "infrastructure_error": "code execution tool was not found",
        }
    except subprocess.TimeoutExpired:
        _terminate_process_tree(process, environment, windows_job)
        windows_job_closed = windows_job is not None
        _communicate_after_termination(process)
        return {
            "passed": False,
            "metric": "build_failed",
            "log": "",
            "infrastructure_error": f"code execution timed out after {safe_timeout} seconds",
        }
    except OSError as exc:
        return {
            "passed": False,
            "metric": "build_failed",
            "log": "",
            "infrastructure_error": redact_error(f"code execution OS error {exc.errno or 'unknown'}"),
        }
    finally:
        if not windows_job_closed:
            _close_windows_job(windows_job)

    combined = "\n".join(part for part in (stdout, stderr) if part)
    redacted_log = redact_error(combined)
    if len(redacted_log) > MAX_LOG_CHARACTERS:
        half = MAX_LOG_CHARACTERS // 2
        log = redacted_log[:half] + redacted_log[-half:]
    else:
        log = redacted_log
    passed = process.returncode == 0
    return {
        "passed": passed,
        "metric": "build_success" if passed else "build_failed",
        "log": log,
        "infrastructure_error": None,
    }
