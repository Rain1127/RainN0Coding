#!/bin/bash
set -euo pipefail
sudo -n true
sudo apt-get update -qq
sudo env DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a apt-get install -y --no-install-recommends openjdk-21-jre-headless nginx curl ca-certificates xz-utils libgomp1 fonts-liberation
if ! id rainn0coding >/dev/null 2>&1; then
  sudo useradd --system --create-home --home-dir /opt/rainn0coding --shell /usr/sbin/nologin rainn0coding
fi
sudo install -d -o rainn0coding -g rainn0coding /opt/rainn0coding/{releases,shared,tools,cache}
sudo chmod 755 /opt/rainn0coding
sudo install -d -m 700 /etc/rainn0coding
cd /opt/rainn0coding
stage=$(mktemp -d)
trap 'rm -f "$stage/uv-install.sh"' EXIT
curl -fsSL --retry 3 --connect-timeout 10 --max-time 180 https://astral.sh/uv/install.sh -o "$stage/uv-install.sh"
chmod 755 "$stage" "$stage/uv-install.sh"
sudo -u rainn0coding env UV_INSTALL_DIR=/opt/rainn0coding/tools sh "$stage/uv-install.sh"
sudo -u rainn0coding env UV_PYTHON_INSTALL_DIR=/opt/rainn0coding/tools/python /opt/rainn0coding/tools/uv python install 3.12
curl -fsSL --retry 3 --connect-timeout 10 --max-time 180 https://nodejs.org/dist/latest-v22.x/SHASUMS256.txt -o "$stage/SHASUMS256.txt"
node_archive=$(awk '/ node-v.*-linux-x64.tar.xz$/ {print $2}' "$stage/SHASUMS256.txt")
test -n "$node_archive"
curl -fsSL --retry 3 --connect-timeout 10 --max-time 300 "https://nodejs.org/dist/latest-v22.x/$node_archive" -o "$stage/$node_archive"
(cd "$stage" && grep " $node_archive\$" SHASUMS256.txt | sha256sum --check)
sudo install -d /opt/rainn0coding/tools/node
sudo tar -xJf "$stage/$node_archive" --strip-components=1 -C /opt/rainn0coding/tools/node
sudo ln -sfn /opt/rainn0coding/tools/node/bin/node /usr/local/bin/node
sudo ln -sfn /opt/rainn0coding/tools/node/bin/npm /usr/local/bin/npm
sudo ln -sfn /opt/rainn0coding/tools/node/bin/npx /usr/local/bin/npx
java -version
node --version
/opt/rainn0coding/tools/uv --version
printf 'PROVISION_READY\n'
