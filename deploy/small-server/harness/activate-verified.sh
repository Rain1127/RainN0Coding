#!/bin/bash
set -euo pipefail
umask 077

stage=/opt/rainn0coding/harness-20261102
root=/opt/rainn0coding
version=${1:?Pass the verified release identifier}
evidence=${2:?Pass the verified smoke report filename}
[[ "$version" =~ ^[0-9]{8}-harness-[a-f0-9]{7,12}$ ]]
[[ "$evidence" =~ ^live-e2e-[a-z0-9-]+\.json$ ]]
test "$(id -u)" = 0
release="$root/releases/$version"
backup="/var/backups/rainn0coding/$version"
previous="$(readlink -f "$root/current")"
test -s "$previous/app.jar"
test ! -e "$release"
test ! -e "$backup"
python3 - "$stage/reports/$evidence" <<'PY'
import json, sys
with open(sys.argv[1]) as handle:
    report = json.load(handle)
assert report["status"] == "passed" and report["queue_status"] == "SUCCEEDED"
assert report["vue_receipt_and_next_run_draft"] and report["candidate_published_with_all_three_requirements"]
PY

db() {
    docker exec -i rainn0coding-mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N rainn0coding'
}
test "$(printf '%s\n' 'SELECT paused FROM generation_queue_lock WHERE id=1;' | db)" = 0
test "$(printf '%s\n' 'SELECT COUNT(*) FROM generation_task WHERE active_app_id IS NOT NULL;' | db)" = 0
install -d -m 700 "$backup"
printf '%s\n' "$previous" > "$backup/previous-release"
install -m 600 /etc/rainn0coding/python.env "$backup/python.env"
install -m 600 /etc/rainn0coding/java.env "$backup/java.env"

locked=0
switched=0
rollback() {
    local status=$?
    trap - EXIT
    if ((status != 0 && switched)); then
        install -m 600 "$backup/python.env" /etc/rainn0coding/python.env
        ln -sfn "$previous" "$root/current.rollback"
        mv -Tf "$root/current.rollback" "$root/current"
        systemctl restart rainn0coding-python rainn0coding-java || true
        printf 'RESTORED_RELEASE=%s\n' "$previous"
    fi
    if ((locked)); then
        printf '%s\n' 'UPDATE generation_queue_lock SET paused=0 WHERE id=1;' | db >/dev/null || true
    fi
    exit "$status"
}
trap rollback EXIT

changed="$(printf '%s\n' 'UPDATE generation_queue_lock SET paused=1 WHERE id=1 AND paused=0; SELECT ROW_COUNT();' | db)"
test "$changed" = 1
locked=1
test "$(printf '%s\n' 'SELECT COUNT(*) FROM generation_task WHERE active_app_id IS NOT NULL;' | db)" = 0

docker exec rainn0coding-mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --no-tablespaces --set-gtid-purged=OFF --databases rainn0coding' > "$backup/mysql.sql"
test -s "$backup/mysql.sql"
tar -C "$root/shared" --exclude=node_modules --exclude=__pycache__ -czf "$backup/artifacts.tar.gz" tmp/code_output tmp/code_deploy
python3 - "$root/shared/checkpoints/generation.db" "$backup" <<'PY'
from pathlib import Path
import sqlite3, sys
source, backup = map(Path, sys.argv[1:])
for path in (source, source.with_suffix(".harness-private.db")):
    if path.is_file():
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db, sqlite3.connect(backup / path.name) as copy:
            db.backup(copy)
            assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
PY
(cd "$backup"; sha256sum mysql.sql artifacts.tar.gz python.env java.env > SHA256SUMS; sha256sum -c SHA256SUMS)

install -d -m 755 "$release"
install -m 644 "$stage/candidate/target/RainN0Coding-0.0.1-SNAPSHOT.jar" "$release/app.jar"
python3 - "$stage/release-source.zip" "$release" <<'PY'
from pathlib import Path
from zipfile import ZipFile
import sys
archive, dest = map(Path, sys.argv[1:])
with ZipFile(archive) as source:
    for entry in source.infolist():
        target = (dest / entry.filename).resolve()
        if entry.filename.startswith("python-agent/") and target.is_relative_to(dest / "python-agent"):
            source.extract(entry, dest)
PY
chmod -R a+rX "$release/python-agent"
sha256sum "$release/app.jar" "$stage/release-source.zip" > "$release/ARTIFACTS.sha256"

test -x "$root/harness-executor/worker.py"
systemctl is-active --quiet "rainn0coding-harness-executor@$(id -u rainn0coding).service"
db < "$stage/candidate/src/main/resources/sql/generation-queue-reliability.sql"
switched=1
python3 - /etc/rainn0coding/python.env <<'PY'
from pathlib import Path
import os, sys
path = Path(sys.argv[1])
flags = {
    "HARNESS_ACCEPTANCE_ENABLED": "true", "HARNESS_CONTEXT_ENABLED": "false", "HARNESS_EDITING_ENABLED": "true",
    "HARNESS_EVENTS_ENABLED": "true", "HARNESS_EXECUTOR_ENABLED": "true", "HARNESS_INSTRUCTIONS_ENABLED": "true",
    "HARNESS_DOCKER_WORKER": "/opt/rainn0coding/harness-executor/worker.py",
}
lines = [line for line in path.read_text().splitlines() if line.split("=", 1)[0].strip() not in flags]
replacement = path.with_name(path.name + ".harness-new")
replacement.write_text("\n".join(lines + [f'{key}="{value}"' for key, value in flags.items()]) + "\n")
os.chmod(replacement, path.stat().st_mode & 0o777)
os.chown(replacement, path.stat().st_uid, path.stat().st_gid)
os.replace(replacement, path)
PY
ln -sfn "$previous" "$root/previous"
ln -s "$release" "$root/current.harness-new"
mv -Tf "$root/current.harness-new" "$root/current"
systemctl restart rainn0coding-python
systemctl restart rainn0coding-java
healthy=0
for attempt in {1..45}; do
    if curl -fsS --max-time 2 http://127.0.0.1:8000/api/health >/dev/null &&
       curl -fsS --max-time 2 http://127.0.0.1:8123/api/health/ >/dev/null &&
       curl -fsS --max-time 2 http://127.0.0.1/api/ >/dev/null; then
        healthy=1
        break
    fi
    sleep 2
done
test "$healthy" = 1
printf '%s\n' 'UPDATE generation_queue_lock SET paused=0 WHERE id=1;' | db >/dev/null
locked=0
switched=0
printf 'ACTIVE_RELEASE=%s\nBACKUP=%s\n' "$release" "$backup"
