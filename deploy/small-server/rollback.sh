#!/bin/bash
set -euo pipefail
previous=$(readlink -f /opt/rainn0coding/previous)
case "$previous" in /opt/rainn0coding/releases/*) ;; *) echo 'No valid previous release'; exit 1;; esac
test -f "$previous/app.jar"
test -d "$previous/python-agent"
sudo ln -s "$previous" /opt/rainn0coding/current.rollback
sudo mv -Tf /opt/rainn0coding/current.rollback /opt/rainn0coding/current
sudo systemctl restart rainn0coding-python rainn0coding-java
printf 'Application rollback activated; re-run health and functional checks.\n'
printf 'Database volumes and credentials were not changed.\n'
