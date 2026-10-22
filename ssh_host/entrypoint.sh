#!/usr/bin/env bash
set -euo pipefail
# публічний ключ клієнта
install -d -m 0700 -o lab -g lab /home/lab/.ssh
install -m 0600 -o lab -g lab /run/lab2-authorized-key /home/lab/.ssh/authorized_keys
# доступ користувача lab до docker.sock за GID сокета
GID=$(stat -c %g /var/run/docker.sock)
getent group "$GID" >/dev/null || addgroup -g "$GID" dockersock
usermod -aG "$(getent group "$GID" | cut -d: -f1)" lab
exec /usr/sbin/sshd -D -e
