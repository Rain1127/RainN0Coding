#!/bin/bash
set -euo pipefail
release_id=${1:?Pass a release identifier}
[[ "$release_id" =~ ^[A-Za-z0-9._-]+$ ]] || exit 2
release="/opt/rainn0coding/releases/$release_id"
upload=/home/ubuntu/rainn0coding-release-upload
test -s "$upload/RainN0Coding-0.0.1-SNAPSHOT.jar"
test -s "$upload/python-agent.tar.gz"
test ! -e "$release"
sudo install -d -m 755 "$release"
sudo cp "$upload/RainN0Coding-0.0.1-SNAPSHOT.jar" "$release/app.jar"
sudo tar -xzf "$upload/python-agent.tar.gz" -C "$release"
sudo install -d -o rainn0coding -g rainn0coding /opt/rainn0coding/shared/{tmp,tmp/code_output,tmp/code_deploy,rag_data,verified_code}
if [ -L /opt/rainn0coding/current ]; then
  previous=$(readlink -f /opt/rainn0coding/current)
  sudo ln -sfn "$previous" /opt/rainn0coding/previous
fi
sudo ln -s "$release" /opt/rainn0coding/current.new
sudo mv -Tf /opt/rainn0coding/current.new /opt/rainn0coding/current
sudo cp /opt/rainn0coding/deployment/rainn0coding-{java,python}.service /etc/systemd/system/
sudo find /opt/rainn0coding/deployment -type d -exec chmod 755 {} +
sudo install -m 644 /opt/rainn0coding/deployment/nginx.conf /etc/nginx/sites-available/rainn0coding
sudo ln -sfn /etc/nginx/sites-available/rainn0coding /etc/nginx/sites-enabled/rainn0coding
# The preflight established a fresh Nginx install; remove only its stock symlink.
if [ -L /etc/nginx/sites-enabled/default ] && [ "$(readlink /etc/nginx/sites-enabled/default)" = /etc/nginx/sites-available/default ]; then
  sudo unlink /etc/nginx/sites-enabled/default
fi
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable rainn0coding-java rainn0coding-python nginx
if [ -x /opt/rainn0coding/venv/bin/python ]; then
  sudo systemctl restart rainn0coding-python
fi
sudo systemctl restart rainn0coding-java
sudo systemctl reload nginx
printf 'RELEASE_ACTIVATED=%s\n' "$release_id"
printf 'Check both service health endpoints before accepting this release.\n'
