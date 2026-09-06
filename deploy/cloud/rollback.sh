#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <release>" >&2
  exit 2
fi

release="$1"
[[ "$release" =~ ^[A-Za-z0-9._-]+$ ]] || {
  echo "Release contains unsupported characters." >&2
  exit 2
}

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

for image in \
  "rain/frontend:${release}" \
  "rain/java-api:${release}" \
  "rain/python-agent:${release}"; do
  docker image inspect "$image" >/dev/null 2>&1 || {
    echo "Rollback image is missing: ${image}" >&2
    exit 1
  }
done

"${script_dir}/start-app-services.sh" \
  --applications-only \
  --release "$release"
"${script_dir}/health-check.sh"

echo "Rollback to ${release} passed health checks."
echo "Update APP_RELEASE in runtime.env to make this release the declared target."
