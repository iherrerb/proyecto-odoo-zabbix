#!/usr/bin/env python3
"""Despliegue automatizado: Odoo CRM + PostgreSQL + Zabbix 7.0 (Entrega 3).
Pasos: 1) requisitos  2) .env  3) descarga de imágenes con reintentos
4) build + up  5) validación de salud  6) configuración de Zabbix por API.
Es idempotente: puede ejecutarse varias veces sin duplicar configuración.
Uso: python3 scripts/deploy.py"""
import json, os, shutil, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
LOG = ROOT / "docs/evidencias/entrega3" / f"deploy_{datetime.now():%Y%m%d_%H%M%S}.log"
IMAGES = ["postgres:16", "odoo:17.0",
          "zabbix/zabbix-server-pgsql:alpine-7.0-latest",
          "zabbix/zabbix-web-nginx-pgsql:alpine-7.0-latest",
          "zabbix/zabbix-agent2:alpine-7.0-latest"]
SCENARIO = "OdooWeb"

def log(msg):
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f: f.write(line + "\n")

def run(cmd, check=True):
    log(f"$ {cmd}")
    r = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    with LOG.open("a", encoding="utf-8") as f: f.write(r.stdout + r.stderr)
    if check and r.returncode:
        log(f"ERROR ({r.returncode}): {r.stderr.strip()[-300:]}"); sys.exit(r.returncode)
    return r

def load_env():
    if not Path(".env").exists():
        shutil.copy(".env.example", ".env"); log(".env creado desde .env.example")
    env = {}
    for l in Path(".env").read_text().splitlines():
        if l.strip() and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1); env[k.strip()] = v.strip()
    return env

def pull_images():
    for img in IMAGES:
        for i in range(1, 6):
            if run(f"docker pull -q {img}", check=False).returncode == 0:
                log(f"Imagen lista: {img}"); break
            log(f"Reintento {i}/5 de {img} en 10 s"); time.sleep(10)
        else:
            log(f"No se pudo descargar {img}. Revise la red/DNS."); sys.exit(1)

def wait_http(url, name, tries=40):
    for i in range(tries):
        try:
            if urllib.request.urlopen(url, timeout=5).status == 200:
                log(f"{name} OK ({url})"); return
        except Exception:
            pass
        log(f"Esperando {name}... ({i+1}/{tries})"); time.sleep(10)
    log(f"{name} no respondió"); sys.exit(1)

class Zabbix:
    def __init__(self, url): self.url, self.token, self.id = url, None, 0
    def call(self, method, params):
        self.id += 1
        body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params, "id": self.id}).encode()
        req = urllib.request.Request(self.url, body, {"Content-Type": "application/json-rpc"})
        if self.token: req.add_header("Authorization", f"Bearer {self.token}")
        res = json.load(urllib.request.urlopen(req, timeout=20))
        if "error" in res: raise RuntimeError(f"{method}: {res['error'].get('data')}")
        return res["result"]
    def login(self, user, pwd, tries=12):
        for i in range(tries):
            try:
                self.token = self.call("user.login", {"username": user, "password": pwd}); return
            except Exception as e:
                log(f"API de Zabbix aún no disponible ({e}); reintento {i+1}/{tries}"); time.sleep(10)
        log("No fue posible autenticarse en la API de Zabbix"); sys.exit(1)

def configure_zabbix(env):
    z = Zabbix(f"http://localhost:{env.get('ZBX_WEB_PORT','8080')}/api_jsonrpc.php")
    z.login(env.get("ZBX_API_USER", "Admin"), env.get("ZBX_API_PASSWORD", "zabbix"))
    log("API de Zabbix autenticada")

    # El host por defecto "Zabbix server" apunta a 127.0.0.1 y quedaría en rojo: se deshabilita
    for h in z.call("host.get", {"filter": {"host": ["Zabbix server"]}, "output": ["hostid", "status"]}):
        if h["status"] == "0":
            z.call("host.update", {"hostid": h["hostid"], "status": 1}); log("Host 'Zabbix server' deshabilitado")

    if z.call("host.get", {"filter": {"host": ["odoo-vm"]}}):
        log("Host odoo-vm ya existe (ejecución idempotente, no se duplica)"); return

    group = z.call("hostgroup.get", {"filter": {"name": ["Linux servers"]}})[0]["groupid"]
    names = ["Linux by Zabbix agent", "Docker by Zabbix agent 2", "PostgreSQL by Zabbix agent 2"]
    found = z.call("template.get", {"filter": {"host": names}, "output": ["host"]})
    missing = set(names) - {t["host"] for t in found}
    if missing: log(f"ADVERTENCIA: plantillas no encontradas {missing}")
    pg_uri = "tcp://db:5432"
    hostid = z.call("host.create", {
        "host": "odoo-vm", "groups": [{"groupid": group}],
        "templates": [{"templateid": t["templateid"]} for t in found],
        "interfaces": [{"type": 1, "main": 1, "useip": 0, "ip": "", "dns": "zabbix-agent", "port": "10050"}],
        "macros": [{"macro": "{$PG.URI}", "value": pg_uri},
                   {"macro": "{$PG.CONNSTRING.AGENT2}", "value": pg_uri},
                   {"macro": "{$PG.USER}", "value": env["ODOO_DB_USER"]},
                   {"macro": "{$PG.PASSWORD}", "value": env["ODOO_DB_PASSWORD"], "type": 1},
                   {"macro": "{$PG.DATABASE}", "value": "postgres"}]})["hostids"][0]
    log(f"Host odoo-vm creado con {len(found)} plantillas")

    z.call("httptest.create", {"name": SCENARIO, "hostid": hostid, "delay": "1m", "retries": 1,
        "steps": [{"name": "Login", "no": 1, "url": "http://odoo:8069/web/login",
                   "status_codes": "200", "required": "", "timeout": "15s"}]})
    log("Escenario web OdooWeb creado (GET /web/login cada 1 min)")

    z.call("trigger.create", [
        {"description": "Odoo CRM no disponible", "priority": 5,
         "expression": f"last(/odoo-vm/web.test.fail[{SCENARIO}])<>0"},
        {"description": "Odoo CRM responde lento (>3 s)", "priority": 2,
         "expression": f"avg(/odoo-vm/web.test.time[{SCENARIO},Login,resp],5m)>3"}])
    log("Disparadores creados: 'Odoo CRM no disponible' (Disaster) y 'responde lento' (Warning)")

    try:
        if not z.call("dashboard.get", {"filter": {"name": ["Proyecto Odoo"]}}):
            z.call("dashboard.create", {"name": "Proyecto Odoo", "display_period": 30, "auto_start": 1,
                "pages": [{"widgets": [
                    {"type": "problems", "name": "Problemas activos", "x": 0, "y": 0, "width": 36, "height": 5},
                    {"type": "hostavail", "name": "Disponibilidad", "x": 36, "y": 0, "width": 36, "height": 5}]}]})
            log("Dashboard 'Proyecto Odoo' creado (agregar gráficos desde la interfaz)")
    except Exception as e:
        log(f"Dashboard no creado automáticamente: {e}")

def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log("== [1/6] Verificando requisitos")
    if not shutil.which("docker"): run("curl -fsSL https://get.docker.com | sh")
    run("docker compose version")
    log("== [2/6] Preparando variables"); env = load_env()
    log("== [3/6] Descargando imágenes (con reintentos)"); pull_images()
    log("== [4/6] Construyendo y levantando servicios")
    run("docker compose build odoo"); run("docker compose up -d")
    log("== [5/6] Validando salud")
    wait_http(f"http://localhost:{env.get('ODOO_PORT','8069')}/web/login", "Odoo")
    wait_http(f"http://localhost:{env.get('ZBX_WEB_PORT','8080')}/", "Zabbix web")
    log("== [6/6] Configurando monitoreo por API"); configure_zabbix(env)
    log(run("docker compose ps").stdout)
    log(f"Odoo: http://IP_VM:{env.get('ODOO_PORT','8069')} | Zabbix: http://IP_VM:{env.get('ZBX_WEB_PORT','8080')} (Admin/zabbix)")
    log(f"Log guardado en {LOG.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
