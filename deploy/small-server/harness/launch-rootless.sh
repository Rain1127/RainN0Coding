#!/bin/sh
set -eu
# The systemd unit runs this launcher in a private mount namespace. Some hosts
# have extra mounts below /proc that prevent a nested rootless procfs mount.
mount -t proc -o nosuid,nodev,noexec proc /proc
service_uid="$(id -u rainn0coding)"
service_gid="$(id -g rainn0coding)"
test "$service_uid" != 0
test "$XDG_RUNTIME_DIR" = "/run/user/$service_uid"
exec setpriv --reuid="$service_uid" --regid="$service_gid" --clear-groups \
    /usr/bin/dockerd-rootless.sh --host="unix://$XDG_RUNTIME_DIR/harness-docker.sock" \
    --data-root="$HARNESS_DOCKER_DATA" --exec-root="$XDG_RUNTIME_DIR/harness-exec" \
    --pidfile="$XDG_RUNTIME_DIR/harness-dockerd.pid" --storage-driver=overlay2
