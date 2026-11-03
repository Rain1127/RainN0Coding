#!/usr/bin/python3 -I
"""Unprivileged worker for a dedicated rootless Docker daemon."""
from dataclasses import asdict, replace
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent))
from execution import CHECKS, ExecutionRequest, ExecutionResult, NPM_INSTALL, node_command, process_result

DOCKER = ['/usr/bin/docker']
CONFIG = Path(__file__).with_name('worker.json')
RUNTIME = Path('/run/harness-rootless-docker/jobs')
ENV = {'PATH': '/usr/bin:/bin'}


def job_name(value):
    if not isinstance(value, str) or UUID(value).hex != value:
        raise ValueError('Invalid job identifier')
    return 'rain-harness-' + value


def docker(*args, timeout=6):
    return subprocess.run([*DOCKER, *args], env=ENV, capture_output=True, text=True, timeout=timeout, check=False)


def remove(name):
    result = docker('rm', '-f', name)
    return result.returncode == 0 or 'No such container' in result.stderr


def validate_workspace(path, allowed_roots):
    root = Path(path).resolve(strict=True)
    if str(root) != path or not root.is_dir() or not re.fullmatch(r'[0-9a-f]{32}\.candidate', root.name):
        raise ValueError('Invalid candidate workspace')
    if root.parent.parent not in allowed_roots or not re.fullmatch(r'\.[\w.-]+\.versions', root.parent.name):
        raise ValueError('Workspace is outside configured output roots')
    return root


def check_tree(root, *, dependencies=False):
    size = count = 0
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Expected a regular output directory')
    for directory, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(directory) / name
            attributes = path.lstat()
            if stat.S_ISLNK(attributes.st_mode):
                resolved = path.resolve()
                if not dependencies or Path(os.readlink(path)).is_absolute() or not resolved.is_relative_to(root):
                    raise ValueError('Unsafe symbolic link in workspace')
            elif stat.S_ISREG(attributes.st_mode) and attributes.st_nlink == 1:
                size += attributes.st_size
            elif not stat.S_ISDIR(attributes.st_mode):
                raise ValueError('Unsafe special file or hard link in workspace')
            count += 1
            if size > 300 * 1024 ** 2 or count > 30_000:
                raise OverflowError('Workspace exceeds the file or byte limit')


def prepare_node(source, sandbox, install):
    for entry in source.iterdir():
        if entry.name in ('.git', '.venv', 'dist', 'build', 'node_modules') or entry.name.startswith('.env'):
            continue
        if entry.is_symlink():
            raise ValueError('Unsafe symbolic link in candidate')
        if entry.is_dir():
            check_tree(entry)
            shutil.copytree(entry, sandbox / entry.name)
        elif entry.is_file() and entry.stat().st_nlink == 1 and entry.stat().st_size <= 64 * 1024 ** 2:
            shutil.copy2(entry, sandbox / entry.name)
        else:
            raise ValueError('Unsafe file in candidate')
    dependencies = source / 'node_modules'
    if not install and dependencies.exists():
        check_tree(dependencies, dependencies=True)
        shutil.copytree(dependencies, sandbox / 'node_modules', symlinks=True)


def transfer_node(source, sandbox, profile):
    install = profile in NPM_INSTALL
    names = ('node_modules',) if install else ('dist', 'build') if profile in ('npm-build', 'vite-build') else ()
    for name in names:
        path = sandbox / name
        if path.exists() or path.is_symlink():
            check_tree(path, dependencies=install)
    for name in names:
        path = sandbox / name
        destination = source / name
        if path.exists():
            if destination.is_symlink():
                raise ValueError('Unsafe output destination')
            if destination.exists():
                shutil.rmtree(destination)
            path.rename(destination)
    if profile == 'npm-install' and (sandbox / 'package-lock.json').is_file():
        node_command(ExecutionRequest('', str(sandbox), profile, 1), isolated=True)
        lock = sandbox / 'package-lock.json'
        if lock.is_symlink() or lock.stat().st_nlink != 1:
            raise ValueError('Unsafe package lock output')
        lock.replace(source / lock.name)


def execute(payload, config):
    name = job_name(payload.pop('job_id'))
    request = ExecutionRequest(**payload)
    if not isinstance(request.timeout, (int, float)) or not math.isfinite(request.timeout) or not 0 < request.timeout <= 180:
        raise ValueError('Invalid deadline')
    browser = request.profile == 'browser'
    syntax_commands = {
        'python-syntax': ['python3', '-I', '-X', 'pycache_prefix=/tmp/pycache', '-m', 'compileall', '-q', '.'],
        'java-syntax': ['/bin/sh', '-c', 'mkdir /tmp/classes && find . -type f -name "*.java" -print0 | xargs -0 javac -proc:none -d /tmp/classes'],
        'go-syntax': ['go', 'vet', './...'],
        'rust-syntax': ['cargo', 'check', '--offline', '--target-dir', '/tmp/target'],
    }
    syntax = request.profile in syntax_commands
    image_key = 'browser_image' if browser else request.profile.removesuffix('-syntax') + '_image' if syntax else 'node_image'
    image = config.get(image_key)
    if not image or not re.fullmatch(r'(?:[a-z0-9./_-]+@)?sha256:[0-9a-f]{64}', image):
        return ExecutionResult('unverified', 'environment', None, f'{image_key} is unavailable', 0, 'docker')
    input_text = None
    report_dir = None
    mounts = []
    root = validate_workspace(request.workspace, {Path(path) for path in config['workspace_roots']})
    if browser:
        parameters = request.browser or {}
        browser_root, feature = request.target, parameters.get('feature', '')
        if browser_root not in ('.', 'src', 'dist') or not re.fullmatch(r'[a-zA-Z0-9_-]{0,64}', feature):
            raise ValueError('Invalid browser workspace or feature')
        if not (root / browser_root).resolve().is_relative_to(root):
            raise ValueError('Browser root is outside the candidate')
        report_dir = root.parent / (root.stem + '.acceptance') / feature
        if report_dir.resolve() != report_dir:
            raise ValueError('Invalid acceptance report directory')
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / 'runtime.json').unlink(missing_ok=True)
        input_text = json.dumps([browser_root, parameters['contract']], ensure_ascii=False)
        command = ['python3', '/trusted/browser_entry.py']
        mounts += ['--interactive', '--shm-size=192m', '--env', 'HARNESS_BROWSER_OFFLINE=true',
                   '--env', 'PYTHONPATH=/trusted/site-packages',
                   '--mount', f'type=bind,source={CONFIG.parent}/browser,target=/trusted,readonly',
                   '--mount', f'type=bind,source={report_dir},target=/report']
    elif syntax:
        command = syntax_commands[request.profile]
        mounts += ['--env', 'GOCACHE=/tmp/go-build', '--env', 'GOMODCACHE=/tmp/go-mod',
                   '--env', 'GOPROXY=off', '--env', 'CARGO_HOME=/tmp/cargo']
    network = 'bridge' if request.profile in NPM_INSTALL else 'none'
    failure = 'dependency' if request.profile in NPM_INSTALL else 'code'
    cache = config.get('npm_cache')
    install_mounts = []
    cache_args = []
    if cache:
        cache_path = Path(cache).resolve(strict=True)
        if str(cache_path) != cache or not cache_path.is_dir() or cache_path.stat().st_uid != os.geteuid():
            raise ValueError('Expected a private registry cache owned by the service account')
        install_mounts = ['--mount', f'type=bind,source={cache_path},target=/registry-cache']
        cache_args = ['--cache=/registry-cache']
    if request.profile in NPM_INSTALL:
        mounts += install_mounts
    with (RUNTIME / 'slot').open('a') as slot:
        try:
            fcntl.flock(slot, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return ExecutionResult('failed', 'resource', None, 'Isolated executor is busy', 0, 'docker')
        cancel = RUNTIME / (name + '.cancel')

        class Cancellation:
            def is_set(self):
                return cancel.exists()

        with TemporaryDirectory(prefix='.executor-', dir=root.parent) as scratch:
            workspace = root
            if not (browser or syntax):
                workspace = Path(scratch)
                prepare_node(root, workspace, request.profile in NPM_INSTALL)
                command = node_command(ExecutionRequest(request.run_id, str(workspace), request.profile,
                                                        request.timeout, request.target), isolated=True)
                if request.profile in NPM_INSTALL:
                    command += cache_args
            if cancel.exists():
                return ExecutionResult('cancelled', 'cancelled', None, '', 0, 'docker')
            cancellation = Cancellation()
            if request.profile in CHECKS and not (workspace / 'node_modules').is_dir():
                package = json.loads((workspace / 'package.json').read_text())
                if any(package.get(kind) for kind in ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies')):
                    install = 'npm-install-locked' if (workspace / 'package-lock.json').is_file() else 'npm-install-preserve'
                    prepared = replace(request, workspace=str(workspace), profile=install, target=None, timeout=min(25, request.timeout))
                    started = time.monotonic()
                    result = run_container(prepared, name, image, 'bridge', workspace, install_mounts, False,
                                           node_command(prepared, isolated=True) + cache_args,
                                           None, 'dependency', cancellation, None)
                    if result.status != 'succeeded':
                        return result
                    remaining = request.timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        return ExecutionResult('failed', 'timeout', None, 'Check dependency setup used the deadline',
                                               round((time.monotonic() - started) * 1000), 'docker')
                    request = replace(request, timeout=remaining)
            result = run_container(request, name, image, network, workspace, mounts, browser or syntax,
                                   command, input_text, failure, cancellation, report_dir)
            if result.status == 'succeeded' and workspace != root:
                transfer_node(root, workspace, request.profile)
            return result


def run_container(request, name, image, network, workspace, mounts, readonly, command, input_text,
                  failure, cancel, report_dir):
    try:
        created = docker('create', '--pull=never', '--name', name, '--label', 'rain.harness.executor=1', '--init',
                         '--network', network, '--cap-drop=ALL', '--security-opt=no-new-privileges',
                         # Namespace UID 0 maps to the unprivileged service UID on the host.
                         '--user=0:0', '--read-only',
                         '--memory=512m', '--memory-swap=512m', '--cpus=1', '--pids-limit=128',
                         '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m,mode=1777',
                         '--ulimit', 'fsize=67108864:67108864', '--log-driver=none',
                         '--mount', f'type=bind,source={workspace},target=/workspace' + (',readonly' if readonly else ''),
                         *mounts,
                         '--workdir', '/workspace', '--env', 'HOME=/tmp', '--env', 'NPM_CONFIG_CACHE=/tmp/npm',
                         '--env', 'CI=true', '--entrypoint', '/usr/bin/timeout', image,
                         '--kill-after=2s', str(request.timeout), *command)
        if cancel.is_set():
            return ExecutionResult('cancelled', 'cancelled', None, '', 0, 'docker')
        if created.returncode:
            return ExecutionResult('unverified', 'environment', created.returncode, created.stderr[-2000:], 0, 'docker')
        result = process_result([*DOCKER, 'start', '-ai' if input_text else '-a', name], cwd='/', env=ENV,
                                timeout=request.timeout + 3, backend='docker', failure=failure, input_text=input_text, cancel=cancel)
        if cancel.is_set():
            return ExecutionResult('cancelled', 'cancelled', result.exit_code, result.log, result.elapsed_ms, 'docker')
        inspected = docker('inspect', '--format', '{{json .State}}', name)
        if inspected.returncode:
            return ExecutionResult('failed', 'environment', None, inspected.stderr[-2000:], result.elapsed_ms, 'docker')
        status = json.loads(inspected.stdout)
        if status.get('OOMKilled'):
            return ExecutionResult('failed', 'resource', status['ExitCode'], result.log, result.elapsed_ms, 'docker')
        if result.failure_kind == 'timeout' or status['ExitCode'] in (124, 137):
            return ExecutionResult('failed', 'timeout', status['ExitCode'], result.log, result.elapsed_ms, 'docker')
        if status.get('Error') or status['Status'] not in ('exited', 'dead') or status['ExitCode'] in (126, 127):
            return ExecutionResult('unverified', 'environment', status['ExitCode'], result.log, result.elapsed_ms, 'docker')
        if report_dir and result.status == 'succeeded':
            evidence = json.loads((report_dir / 'runtime.json').read_text())
            if evidence.get('screenshot') == '/report/failure.png':
                evidence['screenshot'] = str(report_dir / 'failure.png')
            return ExecutionResult(evidence['status'], evidence.get('failure_kind'), result.exit_code,
                                   evidence.get('log', ''), result.elapsed_ms, 'docker', evidence)
        return result
    finally:
        if not remove(name):
            raise RuntimeError('Could not confirm container cleanup')


def main():
    global RUNTIME
    config = json.loads(CONFIG.read_text())
    socket = Path(config['docker_socket']).resolve(strict=True)
    if os.geteuid() == 0 or socket.stat().st_uid != os.geteuid() or not socket.is_socket():
        raise PermissionError('Expected a private socket owned by the unprivileged service account')
    DOCKER.extend(['--host', 'unix://' + str(socket)])
    info = docker('info', '--format', '{{json .SecurityOptions}}')
    if info.returncode or 'name=rootless' not in json.loads(info.stdout):
        raise RuntimeError('The cloud executor requires rootless Docker')
    RUNTIME = socket.parent / 'jobs'
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    max_payload = 2 * 1024 * 1024
    raw = sys.stdin.buffer.read(max_payload + 1)
    if len(raw) > max_payload:
        raise ValueError('Execution request too large')
    payload = json.loads(raw)
    if set(payload) == {'cancel_job'}:
        name = job_name(payload['cancel_job'])
        (RUNTIME / (name + '.cancel')).touch()
        print('{}')
        return
    for marker in RUNTIME.glob('rain-harness-*.cancel'):
        if marker.stat().st_mtime < time.time() - 600:
            marker.unlink(missing_ok=True)
    try:
        result = execute(payload, config)
    except (ValueError, TypeError) as exc:
        kind = 'dependency' if payload.get('profile') in NPM_INSTALL else 'code'
        result = ExecutionResult('failed', kind, None, str(exc), 0, 'docker')
    except OverflowError as exc:
        result = ExecutionResult('failed', 'resource', None, str(exc), 0, 'docker')
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result = ExecutionResult('unverified', 'environment', None, str(exc), 0, 'docker')
    print(json.dumps(asdict(result), ensure_ascii=False))


if __name__ == '__main__':
    main()
