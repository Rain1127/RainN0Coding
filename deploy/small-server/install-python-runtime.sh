#!/bin/bash
set -euo pipefail
cd /opt/rainn0coding
export UV_PYTHON_INSTALL_DIR=/opt/rainn0coding/tools/python
export UV_CACHE_DIR=/opt/rainn0coding/cache/uv
uv=/opt/rainn0coding/tools/uv
if [ ! -x /opt/rainn0coding/venv/bin/python ]; then
  sudo -u rainn0coding env UV_PYTHON_INSTALL_DIR="$UV_PYTHON_INSTALL_DIR" "$uv" venv --python 3.12 /opt/rainn0coding/venv
fi
sudo install -m 644 /opt/rainn0coding/deployment/requirements.in /opt/rainn0coding/requirements.in
sudo chown rainn0coding:rainn0coding /opt/rainn0coding/requirements.in
if [ -s /opt/rainn0coding/deployment/requirements.lock ] && [ "${REGENERATE_LOCK:-0}" != 1 ]; then
  sudo install -o rainn0coding -g rainn0coding -m 644 /opt/rainn0coding/deployment/requirements.lock /opt/rainn0coding/requirements.lock
else
  sudo -u rainn0coding env UV_PYTHON_INSTALL_DIR="$UV_PYTHON_INSTALL_DIR" UV_CACHE_DIR="$UV_CACHE_DIR" "$uv" pip compile \
    --python /opt/rainn0coding/venv/bin/python \
    --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --output-file /opt/rainn0coding/requirements.lock /opt/rainn0coding/requirements.in
fi
sudo -u rainn0coding env UV_CACHE_DIR="$UV_CACHE_DIR" "$uv" pip sync \
  --python /opt/rainn0coding/venv/bin/python \
  --index-url https://pypi.tuna.tsinghua.edu.cn/simple /opt/rainn0coding/requirements.lock
sudo -u rainn0coding /opt/rainn0coding/venv/bin/python -c 'import torch, fastapi, redis, qdrant_client; print("PYTHON_RUNTIME_READY", torch.__version__, "CUDA", torch.version.cuda)'
