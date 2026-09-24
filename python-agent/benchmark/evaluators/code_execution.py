from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmark.redaction import redact_error


SAFE_ENV_KEYS = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "TEMP", "TMP")
MAX_LOG_CHARACTERS = 4000
MAX_TIMEOUT_SECONDS = 600
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_CREATE_SUSPENDED = 0x00000004
_WINDOWS_FORBIDDEN_CHARACTERS = frozenset('<>:"|?*')
_WINDOWS_RESERVED_BASENAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)


def normalize_generated_path(raw_path: object) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"unsafe generated path: {raw_path!r}")
    components = raw_path.replace("\\", "/").split("/")
    for component in components:
        basename = component.split(".", 1)[0].rstrip(" .").upper()
        if (
            component in {"", ".", ".."}
            or component.rstrip(" .") != component
            or any(ord(character) < 32 for character in component)
            or any(character in _WINDOWS_FORBIDDEN_CHARACTERS for character in component)
            or basename in _WINDOWS_RESERVED_BASENAMES
        ):
            raise ValueError(f"unsafe generated path: {raw_path}")
    return Path(*components)


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
        relative = normalize_generated_path(item["path"])
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


def _windows_process_entries() -> dict[int, int]:
    if os.name != "nt":
        return {}
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if not snapshot or int(snapshot) == ctypes.c_void_p(-1).value:
        return {}
    entries: dict[int, int] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        available = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while available:
            entries[int(entry.th32ProcessID)] = int(entry.th32ParentProcessID)
            available = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return entries


def _resume_windows_process(pid: int) -> bool:
    if os.name != "nt":
        return True
    import ctypes
    from ctypes import wintypes

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = (wintypes.HANDLE, ctypes.POINTER(THREADENTRY32))
    kernel32.Thread32First.restype = wintypes.BOOL
    kernel32.Thread32Next.argtypes = (wintypes.HANDLE, ctypes.POINTER(THREADENTRY32))
    kernel32.Thread32Next.restype = wintypes.BOOL
    kernel32.OpenThread.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenThread.restype = wintypes.HANDLE
    kernel32.ResumeThread.argtypes = (wintypes.HANDLE,)
    kernel32.ResumeThread.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
    if not snapshot or int(snapshot) == ctypes.c_void_p(-1).value:
        return False
    resumed = False
    try:
        entry = THREADENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        available = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while available:
            if int(entry.th32OwnerProcessID) == pid:
                thread = kernel32.OpenThread(0x0002, False, entry.th32ThreadID)
                if thread:
                    try:
                        resumed = kernel32.ResumeThread(thread) != 0xFFFFFFFF or resumed
                    finally:
                        kernel32.CloseHandle(thread)
            available = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return resumed


def _open_windows_process_handle(pid: int) -> int | None:
    if os.name != "nt" or pid == os.getpid():
        return None
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(0x0001 | 0x00100000, False, pid)
    return int(handle) if handle else None


def _track_windows_descendants(
    root_pid: int,
    stop: threading.Event,
    handles: dict[int, int],
    lock: threading.Lock,
) -> None:
    known = {root_pid}
    while not stop.is_set():
        entries = _windows_process_entries()
        changed = True
        while changed:
            changed = False
            for pid, parent_pid in entries.items():
                if pid not in known and pid != os.getpid() and parent_pid in known:
                    known.add(pid)
                    handle = _open_windows_process_handle(pid)
                    if handle is not None:
                        with lock:
                            handles.setdefault(pid, handle)
                    changed = True
        stop.wait(0.005)


def _terminate_tracked_windows_processes(handles: dict[int, int], lock: threading.Lock) -> None:
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    with lock:
        tracked = list(handles.values())
        handles.clear()
    for raw_handle in reversed(tracked):
        handle = wintypes.HANDLE(raw_handle)
        kernel32.TerminateProcess(handle, 1)
        kernel32.WaitForSingleObject(handle, 1000)
        kernel32.CloseHandle(handle)


def _terminate_windows_pid(pid: int) -> None:
    if os.name != "nt" or pid == os.getpid():
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.TerminateProcess.restype = wintypes.BOOL
    kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(0x0001 | 0x00100000, False, pid)
    if not handle:
        return
    try:
        kernel32.TerminateProcess(handle, 1)
        kernel32.WaitForSingleObject(handle, 1000)
    finally:
        kernel32.CloseHandle(handle)


def _terminate_windows_descendants(root_pid: int) -> None:
    if os.name != "nt" or root_pid == os.getpid():
        return
    known = {root_pid}
    for _attempt in range(4):
        entries = _windows_process_entries()
        descendants: list[int] = []
        changed = True
        while changed:
            changed = False
            for pid, parent_pid in entries.items():
                if pid not in known and pid != os.getpid() and parent_pid in known:
                    known.add(pid)
                    descendants.append(pid)
                    changed = True
        if not descendants:
            break
        for pid in reversed(descendants):
            _terminate_windows_pid(pid)


def _kill_windows_process_tree(
    process: subprocess.Popen[str],
    environment: dict[str, str],
    job: int | None,
    tracked_handles: dict[int, int],
    tracked_lock: threading.Lock,
) -> None:
    _terminate_tracked_windows_processes(tracked_handles, tracked_lock)
    _terminate_windows_descendants(process.pid)
    if job is not None:
        _close_windows_job(job, terminate=True)
        _terminate_windows_descendants(process.pid)
        if process.poll() is None:
            process.kill()
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
        _terminate_windows_descendants(process.pid)
        if process.poll() is None:
            process.kill()


def _terminate_process_tree(
    process: subprocess.Popen[str],
    environment: dict[str, str],
    windows_job: int | None,
    tracked_handles: dict[int, int],
    tracked_lock: threading.Lock,
) -> None:
    if os.name == "nt":
        _kill_windows_process_tree(process, environment, windows_job, tracked_handles, tracked_lock)
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError:
        if process.poll() is None:
            process.kill()


def _cleanup_process_tree(
    process: subprocess.Popen[str] | None,
    windows_job: int | None,
    *,
    windows_job_closed: bool,
    tracker_stop: threading.Event,
    tracker: threading.Thread | None,
    tracked_handles: dict[int, int],
    tracked_lock: threading.Lock,
) -> None:
    tracker_stop.set()
    if tracker is not None:
        tracker.join(timeout=1)
    if process is None:
        return
    if os.name == "nt":
        _terminate_tracked_windows_processes(tracked_handles, tracked_lock)
        _terminate_windows_descendants(process.pid)
        if not windows_job_closed:
            _close_windows_job(windows_job)
        _terminate_windows_descendants(process.pid)
        if process.poll() is None:
            process.kill()
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
    process: subprocess.Popen[str] | None = None
    windows_job: int | None = None
    windows_job_closed = False
    tracker_stop = threading.Event()
    tracker: threading.Thread | None = None
    tracked_handles: dict[int, int] = {}
    tracked_lock = threading.Lock()
    try:
        options: dict[str, Any] = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | _CREATE_SUSPENDED
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
        if os.name == "nt":
            windows_job = _create_windows_kill_job(process)
            if windows_job is None:
                process.kill()
                _communicate_after_termination(process)
                return {
                    "passed": False,
                    "metric": "build_failed",
                    "log": "",
                    "infrastructure_error": "Windows process isolation could not be established",
                }
            tracker = threading.Thread(
                target=_track_windows_descendants,
                args=(process.pid, tracker_stop, tracked_handles, tracked_lock),
                name=f"benchmark-process-tracker-{process.pid}",
                daemon=True,
            )
            tracker.start()
            if not _resume_windows_process(process.pid):
                raise OSError("failed to resume benchmark process")
        stdout, stderr = process.communicate(timeout=safe_timeout)
    except FileNotFoundError:
        return {
            "passed": False,
            "metric": "build_failed",
            "log": "",
            "infrastructure_error": "code execution tool was not found",
        }
    except subprocess.TimeoutExpired:
        _terminate_process_tree(
            process,
            environment,
            windows_job,
            tracked_handles,
            tracked_lock,
        )
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
        _cleanup_process_tree(
            process,
            windows_job,
            windows_job_closed=windows_job_closed,
            tracker_stop=tracker_stop,
            tracker=tracker,
            tracked_handles=tracked_handles,
            tracked_lock=tracked_lock,
        )

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
