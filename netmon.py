#!/usr/bin/env python3
"""ЛР2: інвентаризація та моніторинг проєкту ЛР1 через SSH, Docker CLI та Docker Engine API."""
import argparse
import csv
import json
import logging
import re
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import docker
import paramiko
import requests
from docker.transport.sshconn import SSHHTTPAdapter

COMMAND_TIMEOUT = 10


# ---------- підключення ----------

def ssh_connect(args):
    """SSH-клієнт зі строгою перевіркою ключа сервера (без TOFU)."""
    client = paramiko.SSHClient()
    client.load_host_keys(str(args.known_hosts))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(args.ssh_host, port=args.ssh_port, username=args.user,
                   key_filename=str(args.key), allow_agent=False, look_for_keys=False,
                   timeout=5, banner_timeout=5, auth_timeout=5)
    return client


class StrictSSHAdapter(SSHHTTPAdapter):
    """Адаптер Docker SDK із суворою перевіркою ключа сервера та ключем з аргументів."""
    settings = None

    def _create_paramiko_client(self, base_url):
        self.ssh_client = paramiko.SSHClient()
        s = StrictSSHAdapter.settings
        self.ssh_params = {"hostname": s.ssh_host, "port": s.ssh_port, "username": s.user,
                           "key_filename": str(s.key), "allow_agent": False, "look_for_keys": False, "timeout": 5}
        self.ssh_client.load_host_keys(str(s.known_hosts))
        self.ssh_client.set_missing_host_key_policy(paramiko.RejectPolicy())


def docker_api(args, ssh_client=None):
    """Docker Engine API поверх SSH (docker system dial-stdio)."""
    StrictSSHAdapter.settings = args
    # підміна адаптера, який створює APIClient
    docker.api.client.SSHHTTPAdapter = StrictSSHAdapter
    return docker.DockerClient(base_url=f"ssh://{args.user}@{args.ssh_host}:{args.ssh_port}",
                               use_ssh_client=False, timeout=10)


# ---------- збір через Docker CLI ----------

def run_ssh(ssh, command):
    """Виконує команду через SSH, при ненульовому коді викидає помилку."""
    _, out, err = ssh.exec_command(command, timeout=COMMAND_TIMEOUT)
    text = out.read().decode().strip()
    code = out.channel.recv_exit_status()
    if code != 0:
        raise RuntimeError(f"команда завершилась з кодом {code}: {command}: {err.read().decode().strip()}")
    return text


def collect_cli(ssh, project):
    containers = []
    ps = run_ssh(ssh, f"docker ps -a --no-trunc --filter label=com.docker.compose.project={project} "
                      "--format '{{.ID}} {{.Image}} {{.State}}'")
    for line in ps.splitlines():
        cid, image, state = line.split()
        service, started = run_ssh(
            ssh, "docker inspect --format "
                 "'{{index .Config.Labels \"com.docker.compose.service\"}} {{.State.StartedAt}}' " + cid).split()
        nets_raw = run_ssh(
            ssh, "docker inspect --format "
                 "'{{range $name, $network := .NetworkSettings.Networks}}"
                 "{{println $name $network.IPAddress}}{{end}}' " + cid)
        networks = {}
        for ln in nets_raw.splitlines():
            parts = ln.split()
            if parts:
                networks[parts[0]] = parts[1] if len(parts) > 1 else ""
        # docker port не повертає помилку для контейнера без портів
        ports_raw = run_ssh(ssh, f"docker port {cid}")
        ports = []
        for ln in ports_raw.splitlines():
            m = re.match(r"(\d+)/(\w+) -> (.+):(\d+)$", ln.strip())
            if m:
                ports.append((m.group(1), m.group(2), m.group(3).strip("[]"), m.group(4)))
        containers.append({"service": service, "id": cid, "image": image, "state": state,
                           "started_at": started, "networks": networks, "ports": ports})
    return containers


# ---------- збір через Docker Engine API ----------

def collect_api(client, project):
    containers = []
    for c in client.containers.list(all=True, filters={"label": f"com.docker.compose.project={project}"}):
        c.reload()
        a = c.attrs
        networks = {n: d["IPAddress"] for n, d in a["NetworkSettings"]["Networks"].items()}
        ports = []
        for key, binds in (a["NetworkSettings"]["Ports"] or {}).items():
            port, proto = key.split("/")
            for b in binds or []:
                ports.append((port, proto, b["HostIp"], b["HostPort"]))
        containers.append({"service": c.labels["com.docker.compose.service"], "id": c.id,
                           "image": a["Config"]["Image"], "state": a["State"]["Status"],
                           "started_at": a["State"]["StartedAt"], "networks": networks, "ports": ports})
    return containers


# ---------- нормалізація та порівняння ----------

def norm_time(value):
    """Приводить час до ISO 8601 UTC з точністю до секунд."""
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)", value)
    return m.group(1) + "Z" if m else value


def normalize(containers):
    out = []
    for c in containers:
        out.append({
            "service": c["service"],
            "id": c["id"],
            "image": c["image"],
            "state": c["state"].lower(),
            "started_at": norm_time(c["started_at"]),
            "networks": sorted(f"{n}={ip}" for n, ip in c["networks"].items()),
            "ports": sorted(f"{h}:{hp}->{p}/{proto}" for p, proto, h, hp in c["ports"]),
        })
    return sorted(out, key=lambda x: x["id"])


def snapshot(source, containers, args):
    return {"host": args.hostname, "project": args.project, "source": source,
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "containers": normalize(containers)}


def compare(cli, api):
    """Порівняння за повним ID: склад, стан, мережі, порти (без урахування порядку)."""
    diffs = []
    a = {c["id"]: c for c in cli["containers"]}
    b = {c["id"]: c for c in api["containers"]}
    for cid in sorted(set(a) - set(b)):
        diffs.append(f"контейнер {a[cid]['service']} ({cid[:12]}) є лише в CLI")
    for cid in sorted(set(b) - set(a)):
        diffs.append(f"контейнер {b[cid]['service']} ({cid[:12]}) є лише в API")
    for cid in sorted(set(a) & set(b)):
        for field in ("service", "image", "state", "started_at"):
            if a[cid][field] != b[cid][field]:
                diffs.append(f"{a[cid]['service']}: {field}: CLI={a[cid][field]} API={b[cid][field]}")
        for field in ("networks", "ports"):
            if set(a[cid][field]) != set(b[cid][field]):
                diffs.append(f"{a[cid]['service']}: {field}: CLI={a[cid][field]} API={b[cid][field]}")
    return diffs


# ---------- перевірка мережевої конфігурації ----------

def network_table(snap):
    table = {}
    for c in snap["containers"]:
        for net in c["networks"]:
            name = net.split("=")[0]
            table.setdefault(name, []).append(c["service"])
    return {k: sorted(v) for k, v in table.items()}


def check_ports(snap, proxy_service):
    """Лише веб-проксі може мати прив'язку порту до хоста."""
    violations = []
    for c in snap["containers"]:
        if c["service"] != proxy_service and c["ports"]:
            violations.append(f"{c['service']} ({c['id'][:12]}): {', '.join(c['ports'])}")
    return violations


# ---------- HTTP-перевірка ----------

def http_check(url):
    """Два послідовні запити, повертає список результатів."""
    results = []
    for _ in range(2):
        try:
            r = requests.get(url, timeout=5)
            try:
                hits = r.json().get("hits")
            except ValueError:
                hits = None
            results.append({"status": r.status_code, "time_ms": round(r.elapsed.total_seconds() * 1000, 1), "hits": hits})
        except requests.RequestException as exc:
            results.append({"status": None, "time_ms": None, "hits": None, "error": type(exc).__name__})
    return results


# ---------- режими роботи ----------

def mode_inventory(args):
    try:
        ssh = ssh_connect(args)
    except (paramiko.SSHException, OSError) as exc:
        print(f"ПОМИЛКА: вузол недоступний або автентифікація не вдалася: {exc}")
        return 2
    print("SSH:", run_ssh(ssh, "hostname"), "| Docker:", run_ssh(ssh, "docker info --format '{{.ServerVersion}}'"))
    print(run_ssh(ssh, f"docker compose ls --filter name={args.project}"))
    cli = snapshot("cli", collect_cli(ssh, args.project), args)
    client = docker_api(args, ssh)
    api = snapshot("api", collect_api(client, args.project), args)

    rows = []
    print(f"\n[CLI] контейнерів: {len(cli['containers'])}, [API] контейнерів: {len(api['containers'])}")
    for c in api["containers"]:
        print(f"  {c['service']:<6} {c['id'][:12]} {c['image']:<18} {c['state']:<8} {c['networks']} {c['ports']}")

    table = network_table(api)
    print("\nМережа -> контейнери:")
    for net, svc in table.items():
        print(f"  {net}: {', '.join(svc)}")
        rows.append(["network_map", net, "info", ", ".join(svc)])

    violations = check_ports(api, args.proxy_service)
    if violations:
        verdict = "порушення: " + "; ".join(violations)
    else:
        verdict = "відповідає вимогам"
    print("\nПеревірка публікації портів:", verdict)
    rows.append(["ports_check", "лише проксі публікує порт", "FAIL" if violations else "PASS", verdict])

    http = http_check(args.proxy_url)
    for i, h in enumerate(http, 1):
        print(f"HTTP #{i}: status={h['status']} time={h['time_ms']} ms hits={h['hits']}")
        rows.append(["http", f"запит {i}", "PASS" if h["status"] == 200 else "FAIL",
                     f"status={h['status']} time_ms={h['time_ms']} hits={h['hits']}"])
    counter_ok = all(h["hits"] is not None for h in http) and http[1]["hits"] == http[0]["hits"] + 1
    print("Лічильник зріс на 1 (proxy -> app -> db):", counter_ok)
    rows.append(["http", "лічильник +1", "PASS" if counter_ok else "FAIL", f"{[h['hits'] for h in http]}"])

    diffs = compare(cli, api)
    print("\nПорівняння CLI та API:", "відмінностей немає" if not diffs else "")
    for d in diffs:
        print("  -", d)
    rows.append(["compare_cli_api", "склад, стани, мережі, порти", "PASS" if not diffs else "FAIL",
                 "відмінностей немає" if not diffs else " | ".join(diffs)])

    Path(args.inventory).write_text(json.dumps({"cli": cli, "api": api}, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(args.report, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["category", "item", "result", "details"])
        w.writerows(rows)
    print(f"\nЗбережено: {args.inventory}, {args.report}")
    ssh.close()
    return 0 if not violations and not diffs and counter_ok else 1


def mode_monitor(args):
    ssh = ssh_connect(args)
    client = docker_api(args, ssh)
    path = Path(args.monitoring)
    new = not path.exists()
    n = 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["timestamp", "services", "http_status", "http_time_ms"])
        try:
            while args.count == 0 or n < args.count:
                ts = datetime.now().isoformat(timespec="seconds")
                try:
                    states = {}
                    for c in client.containers.list(all=True, filters={"label": f"com.docker.compose.project={args.project}"}):
                        c.reload()
                        states[c.labels["com.docker.compose.service"]] = c.attrs["State"]["Status"]
                    services = ";".join(f"{k}={v}" for k, v in sorted(states.items()))
                except Exception as exc:
                    services = f"api_error:{type(exc).__name__}"
                try:
                    r = requests.get(args.proxy_url, timeout=5)
                    status, ms = r.status_code, round(r.elapsed.total_seconds() * 1000, 1)
                except requests.RequestException as exc:
                    status, ms = type(exc).__name__, ""
                w.writerow([ts, services, status, ms])
                f.flush()
                print(ts, services, status, ms, flush=True)
                n += 1
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pass
    ssh.close()
    return 0


def parse():
    p = argparse.ArgumentParser(description="Інвентаризація та моніторинг проєкту ЛР1 через SSH")
    p.add_argument("mode", choices=["inventory", "monitor"], nargs="?", default="inventory")
    p.add_argument("--ssh-host", default="127.0.0.1")
    p.add_argument("--ssh-port", type=int, default=2222)
    p.add_argument("--user", default="lab")
    p.add_argument("--key", type=Path, default=Path(".state/client_key"))
    p.add_argument("--known-hosts", type=Path, default=Path(".state/known_hosts"))
    p.add_argument("--project", default="lab1")
    p.add_argument("--proxy-service", default="proxy")
    p.add_argument("--proxy-url", default="http://127.0.0.1:8080/")
    p.add_argument("--hostname", default=None)
    p.add_argument("--inventory", default="inventory.json")
    p.add_argument("--report", default="report.csv")
    p.add_argument("--monitoring", default="monitoring.csv")
    p.add_argument("--interval", type=float, default=10, help="інтервал опитування, с")
    p.add_argument("--count", type=int, default=0, help="кількість ітерацій (0 = безкінечно)")
    a = p.parse_args()
    a.hostname = a.hostname or socket.gethostname()
    return a


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    args = parse()
    sys.exit(mode_inventory(args) if args.mode == "inventory" else mode_monitor(args))
