#!/usr/bin/env python3
"""Despliegue automatizado: Odoo CRM + PostgreSQL + Zabbix.
1) Verifica requisitos  2) Prepara .env  3) Construye y levanta contenedores
4) Valida salud  5) Configura el monitoreo en Zabbix por API (host, plantillas,
escenario web y disparador). Deja log en docs/evidencias/."""
import json, os, shutil, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
LOG = ROOT / "docs/evidencias" / f"deploy_{datetime.now():%Y%m%d_%H%M%S}.log"

def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line); LOG.open("a", encoding="utf-8").write(line + "\n")

def run(cmd):
    log(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    LOG.open("a", encoding="utf-8").write(r.stdout + r.stderr)
    if r.returncode: log(f"ERROR ({r.returncode})"); sys.exit(r.returncode)
    return r.stdout

def load_env():
    if not Path(".env").exists(): shutil.copy(".env.example", ".env"); log(".env creado desde plantilla")
    env = {}
    for l in Path(".env").read_text().splitlines():
        if l.strip() and not l.startswith("#"): k, v = l.split("=", 1); env[k] = v
    return env

def wait_http(url, name, tries=40):
    for i in range(tries):
        try:
            if urllib.request.urlopen(url, timeout=5).status == 200: log(f"{name} OK"); return
        except Exception: pass
        log(f"Esperando {name}... ({i+1})"); time.sleep(10)
    log(f"{name} no respondió"); sys.exit(1)

class Zabbix:
    def __init__(self, url): self.url, self.token, self.id = url, None, 0
    def call(self, method, params):
        self.id += 1
        req = urllib.request.Request(self.url, json.dumps({"jsonrpc": "2.0", "method": method,
              "params": params, "id": self.id}).encode(), {"Content-Type": "application/json-rpc"})
        if self.token: req.add_header("Authorization", f"Bearer {self.token}")
        res = json.load(urllib.request.urlopen(req, timeout=15))
        if "error" in res: raise RuntimeError(f"{method}: {res['error']}")
        return res["result"]

def configure_zabbix(env):
    z = Zabbix(f"http://localhost:{env['ZBX_WEB_PORT']}/api_jsonrpc.php")
    z.token = z.call("user.login", {"username": env["ZBX_API_USER"], "password": env["ZBX_API_PASSWORD"]})
    group = z.call("hostgroup.get", {"filter": {"name": ["Linux servers"]}})[0]["groupid"]
    names = ["Linux by Zabbix agent", "Docker by Zabbix agent 2", "PostgreSQL by Zabbix agent 2"]
    tpls = [{"templateid": t["templateid"]} for t in z.call("template.get", {"filter": {"host": names}})]
    if z.call("host.get", {"filter": {"host": ["odoo-vm"]}}):
        log("Host odoo-vm ya existe en Zabbix (idempotente)"); return
    hostid = z.call("host.create", {
        "host": "odoo-vm", "groups": [{"groupid": group}], "templates": tpls,
        "interfaces": [{"type": 1, "main": 1, "useip": 0, "ip": "", "dns": "zabbix-agent", "port": "10050"}],
        "macros": [{"macro": "{$PG.URI}", "value": "tcp://db:5432"},
                   {"macro": "{$PG.USER}", "value": env["ODOO_DB_USER"]},
                   {"macro": "{$PG.PASSWORD}", "value": env["ODOO_DB_PASSWORD"], "type": 1},
                   {"macro": "{$PG.DATABASE}", "value": "postgres"}]})["hostids"][0]
    log(f"Host odoo-vm creado ({len(tpls)} plantillas)")
    z.call("httptest.create", {"name": "Odoo disponible", "hostid": hostid, "delay": "1m",
        "steps": [{"name": "Login", "url": "http://odoo:8069/web/login", "status_codes": "200", "no": 1}]})
    z.call("trigger.create", [
        {"description": "Odoo CRM no disponible", "priority": 5,
         "expression": "last(/odoo-vm/web.test.fail[Odoo disponible])<>0"},
        {"description": "Odoo CRM responde lento (>3 s)", "priority": 2,
         "expression": "avg(/odoo-vm/web.test.time[Odoo disponible,Login,resp],5m)>3"}])
    log("Escenario web y disparadores creados")

def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log("== [1/5] Verificando requisitos")
    if not shutil.which("docker"): run("curl -fsSL https://get.docker.com | sh")
    run("docker compose version")
    log("== [2/5] Preparando variables"); env = load_env()
    log("== [3/5] Construyendo y levantando servicios"); run("docker compose build"); run("docker compose up -d")
    log("== [4/5] Validando salud")
    wait_http(f"http://localhost:{env['ODOO_PORT']}/web/database/selector", "Odoo")
    wait_http(f"http://localhost:{env['ZBX_WEB_PORT']}/", "Zabbix web")
    log("== [5/5] Configurando monitoreo por API"); time.sleep(20); configure_zabbix(env)
    log(run("docker compose ps"))
    log(f"Odoo: http://localhost:{env['ODOO_PORT']} | Zabbix: http://localhost:{env['ZBX_WEB_PORT']} (Admin/zabbix)")

if __name__ == "__main__": main()
