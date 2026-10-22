#!/usr/bin/env bash
# Підготовка: ключі SSH, known_hosts, venv та SSH-хост (імітація Linux VM)
set -euo pipefail
cd "$(dirname "$0")"
umask 077
mkdir -p .state evidence
# ключ клієнта та ключ сервера (приватні ключі не потрапляють у git)
[[ -f .state/client_key ]] || ssh-keygen -q -t ed25519 -N '' -C 'lab2-client' -f .state/client_key
[[ -f .state/host_key ]] || ssh-keygen -q -t ed25519 -N '' -C 'lab2-host' -f .state/host_key
chmod 0644 .state/client_key.pub .state/host_key.pub
# known_hosts будується з локального публічного ключа сервера
read -r alg mat _ < .state/host_key.pub
printf '[127.0.0.1]:2222 %s %s\n' "$alg" "$mat" > .state/known_hosts
[[ -x .venv/bin/python ]] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
docker compose up -d --build --wait
