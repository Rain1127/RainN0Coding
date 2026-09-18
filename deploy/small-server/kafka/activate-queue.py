"""Root-only additive queue release. Credentials remain in existing protected files.

Usage: sudo python3 activate-queue.py RELEASE_ID COMMIT_SHA
Upload app.jar, python-agent.tar.gz, SHA256SUMS and generation-queue.sql first.
Does not delete old releases, checkpoints, databases or Kafka volumes.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request

UPLOAD = Path('/home/ubuntu/rainn0coding-kafka-upload')
ROOT = Path('/opt/rainn0coding')
ENV = Path('/etc/rainn0coding/java.env')


def command(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def python_idle():
    with urllib.request.urlopen('http://127.0.0.1:8000/metrics', timeout=10) as response:
        match = re.search(r'^ai_code_gen_active_requests\s+([0-9.eE+\-]+)$', response.read().decode(), re.M)
    return bool(match) and float(match.group(1)) == 0


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run as root')
    release_id, commit = sys.argv[1:3]
    if not re.fullmatch(r'[A-Za-z0-9._-]+', release_id) or not re.fullmatch(r'[0-9a-f]{7,40}', commit):
        raise SystemExit('Invalid release or commit')
    release = ROOT / 'releases' / release_id
    if release.exists():
        raise SystemExit('Release already exists')
    for name in ('app.jar', 'python-agent.tar.gz', 'generation-queue.sql', 'SHA256SUMS'):
        if not (UPLOAD / name).is_file():
            raise SystemExit('Upload incomplete: ' + name)
    command(['sha256sum', '-c', 'SHA256SUMS'], cwd=UPLOAD)
    previous = (ROOT / 'current').resolve(strict=True)
    if not previous.is_relative_to(ROOT / 'releases'):
        raise SystemExit('Unexpected current release')
    mysql = subprocess.check_output(['docker', 'ps', '--filter', 'label=com.docker.compose.service=mysql', '--format', '{{.Names}}'], text=True).splitlines()
    if len(mysql) != 1:
        raise SystemExit('Expected one existing MySQL container')

    def sql(text, output=False):
        result = command(['docker', 'exec', '-i', mysql[0], 'sh', '-c',
                          'exec mysql -N -B -uroot -p"$MYSQL_ROOT_PASSWORD" rainn0coding'],
                         input=text.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode().strip() if output else None

    queue_exists = sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='rainn0coding' AND table_name='generation_queue_lock';", True) == '1'
    if not queue_exists and not python_idle():
        raise SystemExit('Active generation exists; wait before first queue deployment')

    backup = Path('/home/ubuntu/rainn0coding-backups') / (release_id + '-before-queue')
    backup.mkdir(mode=0o700, parents=True, exist_ok=False)
    shutil.copy2(ENV, backup / 'java.env')
    os.chmod(backup / 'java.env', 0o600)
    with (backup / 'database.sql').open('wb') as destination:
        command(['docker', 'exec', mysql[0], 'sh', '-c',
                 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --events rainn0coding'],
                stdout=destination, stderr=subprocess.PIPE)
    os.chmod(backup / 'database.sql', 0o600)

    stopped = False
    switched = False
    try:
        if queue_exists:
            sql('UPDATE generation_queue_lock SET paused=1 WHERE id=1;')
            deadline = time.monotonic() + 1900
            while sql("SELECT COUNT(*) FROM generation_task WHERE status IN ('RUNNING','PAUSING');", True) != '0':
                if time.monotonic() > deadline:
                    raise RuntimeError('Drain timed out; application has not been restarted')
                time.sleep(3)
        # Stop incoming generation first; Python's detached source finishes/checkpoints.
        command(['systemctl', 'stop', 'rainn0coding-java'])
        stopped = True
        deadline = time.monotonic() + 1900
        while not python_idle():
            if time.monotonic() > deadline:
                raise RuntimeError('Python drain timed out')
            time.sleep(3)
        command(['systemctl', 'stop', 'rainn0coding-python'])
        # Services are stopped: preserve SQLite WAL and generated output consistently.
        command(['tar', '-czf', str(backup / 'shared.tar.gz'), '-C', str(ROOT), 'shared'])
        os.chmod(backup / 'shared.tar.gz', 0o600)
        sql((UPLOAD / 'generation-queue.sql').read_text())
        sql('UPDATE generation_queue_lock SET paused=1 WHERE id=1;')
        release.mkdir(mode=0o755)
        shutil.copy2(UPLOAD / 'app.jar', release / 'app.jar')
        os.chmod(release / 'app.jar', 0o644)
        command(['tar', '-xzf', str(UPLOAD / 'python-agent.tar.gz'), '-C', str(release)])
        # EnvFile is extended only by queue keys; all existing values remain untouched.
        updates = {
            'APP_GENERATION_QUEUE_ENABLED': 'true',
            'APP_GENERATION_QUEUE_BOOTSTRAP_SERVERS': '127.0.0.1:9092',
            'APP_GENERATION_QUEUE_TOPIC': 'rain-code-generation-v1',
            'APP_GENERATION_QUEUE_GROUP_ID': 'rain-code-generation-workers-v1',
        }
        lines = [line for line in ENV.read_text().splitlines() if line.partition('=')[0] not in updates]
        staging = ENV.with_suffix('.env.queue-new')
        staging.write_text('\n'.join(lines + [k + '=' + v for k, v in updates.items()]) + '\n')
        os.chmod(staging, ENV.stat().st_mode & 0o777)
        os.chown(staging, ENV.stat().st_uid, ENV.stat().st_gid)
        staging.replace(ENV)
        manifest = {'release': release_id, 'commit': commit, 'previous': str(previous),
                    'app_sha256': hashlib.sha256((release / 'app.jar').read_bytes()).hexdigest(),
                    'backup': str(backup), 'queue_enabled': True}
        (release / 'release-manifest.json').write_text(json.dumps(manifest, indent=2))
        command(['ln', '-sfn', str(previous), str(ROOT / 'previous')])
        link = ROOT / 'current.queue-new'
        if link.exists() or link.is_symlink():
            raise RuntimeError('Unexpected staging symlink exists')
        link.symlink_to(release)
        link.replace(ROOT / 'current')
        switched = True
        command(['systemctl', 'start', 'rainn0coding-python', 'rainn0coding-java'])
        for _ in range(90):
            try:
                for url in ('http://127.0.0.1:8000/api/health', 'http://127.0.0.1:8123/api/actuator/health'):
                    with urllib.request.urlopen(url, timeout=5) as response:
                        if response.status != 200:
                            raise RuntimeError('Health failed')
                break
            except Exception:
                time.sleep(2)
        else:
            raise RuntimeError('New application health checks failed')
        sql('UPDATE generation_queue_lock SET paused=0 WHERE id=1;')
        print(json.dumps({'release_ready': release_id, 'previous': str(previous), 'backup': str(backup)}))
    except BaseException:
        # No user queue jobs are admitted before health passes, so restoring the
        # previous code/config does not abandon newly accepted queue work.
        if switched:
            command(['systemctl', 'stop', 'rainn0coding-java', 'rainn0coding-python'])
            command(['ln', '-sfn', str(previous), str(ROOT / 'current')])
        shutil.copy2(backup / 'java.env', ENV)
        if queue_exists:
            sql('UPDATE generation_queue_lock SET paused=0 WHERE id=1;')
        if stopped:
            command(['systemctl', 'start', 'rainn0coding-python', 'rainn0coding-java'])
        raise


if __name__ == '__main__':
    main()
