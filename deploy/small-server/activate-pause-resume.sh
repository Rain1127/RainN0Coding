#!/bin/bash
set -euo pipefail
release_id=20260910-pause-resume
release=/opt/rainn0coding/releases/$release_id
upload=/home/ubuntu/rainn0coding-pause-resume-upload
test ! -e "$release"
test -s "$upload/RainN0Coding-0.0.1-SNAPSHOT.jar"
test -s "$upload/python-agent.tar.gz"
# Do not interrupt another user's active generation during activation.
curl -fsS http://127.0.0.1:8000/metrics | grep -Eq '^ai_code_gen_active_requests 0(\.0)?$'
previous=$(readlink -f /opt/rainn0coding/current)
sudo install -d -m 755 "$release"
sudo cp "$upload/RainN0Coding-0.0.1-SNAPSHOT.jar" "$release/app.jar"
sudo tar -xzf "$upload/python-agent.tar.gz" -C "$release"
sudo install -d -o rainn0coding -g rainn0coding -m 750 /opt/rainn0coding/shared/checkpoints
sudo cp /etc/systemd/system/rainn0coding-python.service /etc/systemd/system/rainn0coding-python.service.before-pause-resume
sudo install -m 644 "$upload/rainn0coding-python.service" /etc/systemd/system/rainn0coding-python.service
sudo ln -sfn "$previous" /opt/rainn0coding/previous
sudo ln -s "$release" /opt/rainn0coding/current.pause-resume
sudo mv -Tf /opt/rainn0coding/current.pause-resume /opt/rainn0coding/current
sudo systemctl daemon-reload
sudo systemctl restart rainn0coding-python rainn0coding-java
for attempt in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && curl -fsS http://127.0.0.1:8123/api/actuator/health >/dev/null 2>&1; then
    echo "RELEASE_READY=$release_id"
    echo "ROLLBACK_RELEASE=$previous"
    exit 0
  fi
  sleep 2
done
# Restore the application pointer if startup fails, preserving all persistent data.
sudo ln -sfn "$previous" /opt/rainn0coding/current
sudo cp /etc/systemd/system/rainn0coding-python.service.before-pause-resume /etc/systemd/system/rainn0coding-python.service
sudo systemctl daemon-reload
sudo systemctl restart rainn0coding-python rainn0coding-java
echo 'Activation failed; previous application restored' >&2
exit 1
