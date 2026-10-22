#!/usr/bin/env bash
# Збір виводів команд ЛР2 у evidence/*.txt (для звіту)
cd "$(dirname "$0")"
E=evidence; mkdir -p $E
PY=.venv/bin/python
SSH="ssh -i .state/client_key -p 2222 -o UserKnownHostsFile=.state/known_hosts -o StrictHostKeyChecking=yes lab@127.0.0.1"
# запис команди та її виводу у файл
run() { local f="$E/$1.txt"; shift; { echo "\$ $*"; eval "$@" 2>&1; echo "[exit code: $?]"; } > "$f"; }

# проєкт ЛР1 має бути запущений
(cd ../LR1 && docker compose up -d --wait >/dev/null 2>&1)
rm -f inventory.json report.csv monitoring.csv

run 01-versions "$PY --version; $PY -m pip list 2>/dev/null | grep -iE '^(paramiko|docker|requests) '; docker version --format 'Docker Engine {{.Server.Version}}'; docker compose version"
run 02-ssh-manual "$SSH 'hostname; docker info --format \"Docker Engine {{.ServerVersion}}\"; docker compose ls'"
run 03-curl "curl -s http://127.0.0.1:8080/; curl -s http://127.0.0.1:8080/"
run 04-inventory "$PY netmon.py inventory"
run 05-inventory-json "head -c 1500 inventory.json; echo; echo ...; $PY -c \"import json;d=json.load(open('inventory.json'));print({k:len(v['containers']) for k,v in d.items()})\""
run 06-report-csv "cat report.csv"

# негативні сценарії
run 07-err-unreachable "$PY netmon.py inventory --ssh-port 2299"
run 08-err-hostkey "echo '[127.0.0.1]:2222 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqemGtaNeverSeenBeforeKeyAAAAAAAAAAAAAAAA' > .state/bad_known_hosts; $PY netmon.py inventory --known-hosts .state/bad_known_hosts"
run 09-err-command "$PY -c \"
import netmon
a = netmon.parse.__globals__['argparse'].Namespace(ssh_host='127.0.0.1', ssh_port=2222, user='lab', key=netmon.Path('.state/client_key'), known_hosts=netmon.Path('.state/known_hosts'))
ssh = netmon.ssh_connect(a)
try:
    netmon.run_ssh(ssh, 'docker inspect no-such-container')
except RuntimeError as e:
    print('RuntimeError:', e)
\""
# порушення: сторонній контейнер проєкту публікує порт
$SSH 'docker run -d --name lab1-extra --label com.docker.compose.project=lab1 --label com.docker.compose.service=extra -p 9999:80 nginx:1.27-alpine' >/dev/null 2>&1
run 10-violation "$PY netmon.py inventory --report report_violation.csv --inventory inventory_violation.json"
$SSH 'docker rm -f lab1-extra' >/dev/null 2>&1
rm -f report_violation.csv inventory_violation.json

# моніторинг: нормальна робота -> зупинка БД -> відновлення
rm -f monitoring.csv
( sleep 8; docker stop db >/dev/null; sleep 12; docker start db >/dev/null ) &
run 11-monitor "$PY netmon.py monitor --interval 3 --count 14"
wait
run 12-monitoring-csv "cat monitoring.csv"
echo done
