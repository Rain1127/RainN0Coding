"""Bounded execution of server-registered project checks and build profiles."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
from threading import Event, Thread
import time
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True)
class ExecutionRequest:
    run_id: str
    workspace: str
    profile: str
    timeout: float
    target: str | None = None
    browser: dict | None = None


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    failure_kind: str | None
    exit_code: int | None
    log: str
    elapsed_ms: int
    backend: str
    report: dict | None = None


class ExecutionBackend(Protocol):
    def run(self, request: ExecutionRequest, cancel: Event | None = None) -> ExecutionResult: ...


NPM_INSTALL = {'npm-install', 'npm-install-locked', 'npm-install-preserve'}
CHECKS = {'typecheck', 'lint', 'test'}
NODE_PROFILES = NPM_INSTALL | CHECKS | {'npm-build', 'vite-build'}
PACKAGE_REF = re.compile(r'[0-9A-Za-z*.^~<>=| +_-]{1,120}')


def validate_install(root: Path):
    # The installer runs without lifecycle scripts. Reject project-controlled
    # npm settings and package sources that could bypass the registry.
    if (root / '.npmrc').exists() or (root / 'npm-shrinkwrap.json').exists():
        raise ValueError('Custom npm configuration is disabled for isolated installs')
    package = json.loads((root / 'package.json').read_text(encoding='utf-8'))
    if package.get('workspaces') or package.get('overrides'):
        raise ValueError('Workspaces and dependency overrides are unavailable in isolated installs')
    for kind in ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies'):
        if any(not isinstance(value, str) or not PACKAGE_REF.fullmatch(value)
               for value in package.get(kind, {}).values()):
            raise ValueError('Only version ranges and tags from the approved npm registry are allowed')
    lock = root / 'package-lock.json'
    if lock.is_file():
        from urllib.parse import urlsplit
        data = json.loads(lock.read_text(encoding='utf-8'))
        if not isinstance(data.get('packages'), dict) or data.get('lockfileVersion') not in (2, 3):
            raise ValueError('The isolated installer requires npm lockfile version 2 or 3')
        for entry in data['packages'].values():
            if entry.get('link'):
                raise ValueError('Linked dependencies are unavailable in isolated installs')
            if entry.get('resolved'):
                url = urlsplit(entry['resolved'])
                if url.scheme != 'https' or url.netloc != 'registry.npmjs.org':
                    raise ValueError('Lockfile dependency URL is outside the approved registry')


def node_command(request: ExecutionRequest, *, isolated: bool) -> list[str]:
    root = Path(request.workspace)
    profile = request.profile
    if profile in NPM_INSTALL:
        args = ['npm', 'ci' if profile == 'npm-install-locked' else 'install']
        if profile == 'npm-install-preserve':
            args.append('--package-lock=false')
        if isolated:
            validate_install(root)
            args += ['--registry=https://registry.npmjs.org', '--userconfig=/tmp/npm-user.conf',
                     '--globalconfig=/tmp/npm-global.conf', '--ignore-scripts', '--no-audit', '--no-fund',
                     '--fetch-retries=0']
        elif profile != 'npm-install':
            args.append('--ignore-scripts')
        return args
    if profile in ('npm-build', 'vite-build'):
        return ['npm', 'run', 'build'] + (['--', '--base=./'] if profile == 'vite-build' else [])
    if profile not in CHECKS:
        raise ValueError('Unknown execution profile')
    scripts = json.loads((root / 'package.json').read_text(encoding='utf-8')).get('scripts', {})
    if profile not in scripts:
        raise FileNotFoundError(f'package.json does not register {profile}')
    command = ['npm', '--ignore-scripts', 'run', profile]
    if profile == 'test':
        if scripts[profile].strip() not in ('node --test', 'vitest run', 'jest', 'jest --runInBand'):
            raise ValueError('Targeted tests require a registered node --test, vitest run or jest script')
        target = request.target or ''
        if not re.fullmatch(r'[\w./-]+\.(?:test|spec)\.[cm]?[jt]sx?', target, flags=re.ASCII) or target.startswith(('-', '/')):
            raise ValueError('Provide a project-relative test/spec file')
        path = (root / target).resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file() or '..' in Path(target).parts:
            raise ValueError('Test target is outside the candidate')
        command += ['--', './' + target]
    elif request.target is not None:
        raise ValueError('This check does not accept a target')
    return command


def stop_tree(process: subprocess.Popen):
    if os.name == 'nt':
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
            if process.poll() is None:
                process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def process_result(command, *, cwd, timeout, cancel=None, env=None, backend='local', failure='code',
                   input_text=None, log_limit=16_000) -> ExecutionResult:
    started = time.monotonic()
    output = bytearray()

    def result(status, kind=None, code=None, message=None):
        return ExecutionResult(status, kind, code, message if message is not None else output.decode('utf-8', errors='replace'),
                               round((time.monotonic() - started) * 1000), backend)

    if cancel and cancel.is_set():
        return result('cancelled', 'cancelled')
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE if input_text else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=os.name != 'nt')
    except OSError as exc:
        return result('unverified', 'environment', message=str(exc))

    def collect():
        with process.stdout as stream:
            while chunk := stream.read1(8192):
                output.extend(chunk)
                del output[:-log_limit]

    reader = Thread(target=collect, daemon=True)
    reader.start()
    status = None
    try:
        if input_text:
            try:
                with process.stdin:
                    process.stdin.write(input_text.encode())
            except BrokenPipeError:
                pass
        while process.poll() is None:
            if cancel and cancel.is_set():
                status = 'cancelled'
                break
            if time.monotonic() - started >= timeout:
                status = 'timeout'
                break
            time.sleep(0.05)
    finally:
        stop_tree(process)
        process.wait()
        reader.join(timeout=2)
    if status:
        return result('cancelled' if status == 'cancelled' else 'failed', status, process.returncode)
    if process.returncode == 0:
        return result('succeeded', code=0)
    return result('failed', failure, process.returncode)


class LocalBackend:
    def run(self, request, cancel=None):
        try:
            command = node_command(request, isolated=False)
        except FileNotFoundError as exc:
            return ExecutionResult('unverified', 'environment', None, str(exc), 0, 'local')
        except ValueError as exc:
            return ExecutionResult('failed', 'dependency' if request.profile in NPM_INSTALL else 'code', None, str(exc), 0, 'local')
        executable = shutil.which(command[0])
        if executable:
            command[0] = executable
        return process_result(command, cwd=request.workspace, timeout=request.timeout, cancel=cancel,
                              failure='dependency' if request.profile in NPM_INSTALL else 'code')


class DockerBackend:
    def __init__(self, worker: str):
        self.worker = worker

    def run(self, request, cancel=None):
        job_id = uuid4().hex
        command = [self.worker]
        invocation = json.dumps({'job_id': job_id, **asdict(request)}, ensure_ascii=False)
        if cancel and cancel.is_set():
            return ExecutionResult('cancelled', 'cancelled', None, '', 0, 'docker')
        results = []

        def run_worker():
            results.append(process_result(command, cwd='/', timeout=request.timeout + 40, backend='docker',
                                          input_text=invocation, log_limit=2 * 1024 * 1024))

        worker = Thread(target=run_worker, daemon=True)
        worker.start()
        notified = False
        while worker.is_alive():
            if cancel and cancel.is_set() and not notified:
                # Ask the worker to stop cooperatively. It must finish any in-flight
                # Docker create before reporting that the named job was removed.
                process_result(command, cwd='/', timeout=8, backend='docker',
                               input_text=json.dumps({'cancel_job': job_id}))
                notified = True
            worker.join(timeout=0.05)
        if not results:
            return ExecutionResult('unverified', 'environment', None, 'Worker terminated without a result', 0, 'docker')
        raw = results[0]
        if raw.failure_kind == 'timeout':
            return ExecutionResult('unverified', 'environment', raw.exit_code, 'Worker deadline exceeded; cleanup unconfirmed',
                                   raw.elapsed_ms, 'docker')
        try:
            return ExecutionResult(**json.loads(raw.log))
        except (TypeError, ValueError):
            return ExecutionResult('unverified', 'environment', raw.exit_code, raw.log[-1000:], raw.elapsed_ms, 'docker')


def execution_request(state, profile, timeout, *, target=None, browser=None):
    from workflow.budget import active_budget
    budget = active_budget.get()
    if budget:
        budget.check()
        timeout = min(timeout, budget.remaining_seconds())
    return ExecutionRequest(str(state.get('request_id') or state.get('artifact_run_id') or 'standalone'),
                            str(Path(state['project_dir']).resolve()), profile, timeout, target, browser)


def executor(state):
    from workflow.harness_policy import enabled
    if enabled(state, 'executor'):
        worker = os.getenv('HARNESS_DOCKER_WORKER', '')
        if worker:
            return DockerBackend(worker)
        # An explicitly isolated run cannot silently fall back to host execution.
        return DockerBackend('/opt/rainn0coding/harness-executor/worker.py')
    return LocalBackend()
