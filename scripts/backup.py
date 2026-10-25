#!/usr/bin/env python3
"""Respaldo de todas las bases de Odoo con pg_dumpall."""
import subprocess, os
from datetime import datetime
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
env = dict(l.split("=", 1) for l in open(".env").read().splitlines() if l and not l.startswith("#"))
os.makedirs("backups", exist_ok=True)
out = f"backups/odoo_{datetime.now():%Y%m%d_%H%M}.sql"
with open(out, "w") as f:
    subprocess.run(["docker", "compose", "exec", "-T", "db", "pg_dumpall", "-U", env["ODOO_DB_USER"]], stdout=f, check=True)
print("Backup generado:", out)
