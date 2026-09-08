#!/bin/bash
set -euo pipefail
umask 077
backup="$HOME/rainn0coding-backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup"
cp "$HOME/rainn0coding-cloud/compose.yml" "$backup/compose.yml"
cp "$HOME/rainn0coding-cloud/.env" "$backup/data.env"
docker exec rainn0coding-mysql sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysqldump -uroot --single-transaction --routines --events --triggers --no-tablespaces --databases rainn0coding' > "$backup/mysql.sql"
test -s "$backup/mysql.sql"
docker exec rainn0coding-redis redis-cli SAVE
docker cp rainn0coding-redis:/data/dump.rdb "$backup/redis.rdb"
python3 - "$backup" <<'PY'
import json, pathlib, sys, urllib.request
base = 'http://127.0.0.1:6333'
out = pathlib.Path(sys.argv[1])
with urllib.request.urlopen(base + '/collections') as response:
    collections = json.load(response)['result']['collections']
for collection in collections:
    name = collection['name']
    request = urllib.request.Request(f'{base}/collections/{name}/snapshots', method='POST')
    with urllib.request.urlopen(request, timeout=120) as response:
        snapshot = json.load(response)['result']['name']
    urllib.request.urlretrieve(f'{base}/collections/{name}/snapshots/{snapshot}', out / snapshot)
print('Qdrant collections snapshotted:', len(collections))
PY
find "$backup" -type f ! -name SHA256SUMS -exec sha256sum {} + > "$backup/SHA256SUMS"
sha256sum --check "$backup/SHA256SUMS"
printf 'BACKUP_READY=%s\n' "$backup"
