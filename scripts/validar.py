#!/usr/bin/env python3
"""Validación integral del sistema (Entrega 4).
Uso:  python3 scripts/validar.py          -> pruebas no destructivas
      python3 scripts/validar.py --falla  -> además simula caída de Odoo y mide
                                             el tiempo de detección y recuperación
Genera un informe Markdown en docs/evidencias/entrega4/."""
import json, os, subprocess, sys, time, urllib.request
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from deploy import Zabbix, load_env, ROOT

OUT = ROOT / "docs/evidencias/entrega4"; OUT.mkdir(parents=True, exist_ok=True)
REP = OUT / f"validacion_{datetime.now():%Y%m%d_%H%M%S}.md"
rows = []

def sh(cmd): return subprocess.run(cmd, shell=True, text=True, capture_output=True).stdout.strip()
def check(n, name, ok, detail):
    rows.append((n, name, "OK" if ok else "FALLA", detail))
    print(f"[{'OK' if ok else 'FALLA':5}] {n}. {name} -> {detail}", flush=True)
def http(url):
    t = time.time()
    try: return urllib.request.urlopen(url, timeout=10).status, round(time.time() - t, 3)
    except Exception as e: return str(e), None

env = load_env()
z = Zabbix(f"http://localhost:{env.get('ZBX_WEB_PORT','8080')}/api_jsonrpc.php")
z.token = z.call("user.login", {"username": env.get("ZBX_API_USER", "Admin"), "password": env.get("ZBX_API_PASSWORD", "zabbix")})

# 1. Contenedores
ps = [json.loads(l) for l in sh("docker compose ps --format json").splitlines() if l.startswith("{")]
estados = {c["Service"]: c["State"] + (f"/{c['Health']}" if c.get("Health") else "") for c in ps}
check(1, "Contenedores en ejecución", len(ps) >= 6 and all(c["State"] == "running" for c in ps), str(estados))
# 2. Odoo HTTP
code, t = http(f"http://localhost:{env.get('ODOO_PORT','8069')}/web/login")
check(2, "Odoo responde", code == 200, f"HTTP {code} en {t}s")
# 3. Zabbix web
code, t = http(f"http://localhost:{env.get('ZBX_WEB_PORT','8080')}/")
check(3, "Zabbix web responde", code == 200, f"HTTP {code} en {t}s")
# 4. Host y agente
h = z.call("host.get", {"filter": {"host": ["odoo-vm"]}, "selectInterfaces": ["available"],
                        "selectParentTemplates": ["host"], "output": ["hostid"]})
if h:
    hid = h[0]["hostid"]; av = h[0]["interfaces"][0]["available"]
    check(4, "Agente Zabbix disponible", av == "1", f"available={av} (1=verde)")
    check(5, "Plantillas vinculadas", len(h[0]["parentTemplates"]) >= 3, ", ".join(t["host"] for t in h[0]["parentTemplates"]))
    items = z.call("item.get", {"hostids": hid, "countOutput": True, "monitored": True})
    check(6, "Ítems monitoreados", int(items) > 50, f"{items} ítems activos")
    wf = z.call("item.get", {"hostids": hid, "search": {"key_": "web.test.fail[OdooWeb]"}, "output": ["lastvalue"]})
    check(7, "Escenario web OdooWeb", bool(wf) and wf[0]["lastvalue"] == "0", f"web.test.fail={wf[0]['lastvalue'] if wf else 'sin dato'}")
    pr = z.call("problem.get", {"hostids": hid, "output": ["name", "severity"]})
    check(8, "Problemas activos", True, f"{len(pr)}: " + "; ".join(p["name"] for p in pr) if pr else "0 problemas")
else:
    check(4, "Host odoo-vm en Zabbix", False, "No existe: ejecute deploy.py")
# 9. Persistencia
db = sh(f"docker compose exec -T db psql -U {env['ODOO_DB_USER']} -d postgres -tAc \"select datname from pg_database where datname not in ('postgres','template0','template1')\"")
check(9, "Base del CRM persistente", bool(db), db.replace("\n", ", ") or "ninguna")
# 10. Aislamiento de PostgreSQL
pub = sh("docker compose port db 5432")
check(10, "PostgreSQL no publicado", pub == "", "sin puerto publicado" if not pub else pub)

# 11. Simulación de falla
if "--falla" in sys.argv and h:
    def problema():
        return z.call("problem.get", {"hostids": hid, "search": {"name": "Odoo CRM no disponible"}, "output": ["eventid"]})
    print("Deteniendo Odoo para simular la caída...", flush=True)
    t0 = time.time(); sh("docker compose stop odoo")
    while not problema() and time.time() - t0 < 420: time.sleep(10)
    det = round(time.time() - t0)
    ok = bool(problema())
    check(11, "Detección de caída", ok, f"alerta Disaster en {det}s" if ok else "no detectada en 7 min")
    t1 = time.time(); sh("docker compose start odoo")
    while problema() and time.time() - t1 < 600: time.sleep(10)
    rec = round(time.time() - t1)
    check(12, "Recuperación (RESOLVED)", not problema(), f"resuelta en {rec}s")

with REP.open("w", encoding="utf-8") as f:
    f.write(f"# Validación integral – {datetime.now():%Y-%m-%d %H:%M}\n\n| # | Prueba | Resultado | Detalle |\n|---|---|---|---|\n")
    for r in rows: f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |\n")
ok = sum(r[2] == "OK" for r in rows)
print(f"\n{ok}/{len(rows)} pruebas OK. Informe: {REP.relative_to(ROOT)}")
