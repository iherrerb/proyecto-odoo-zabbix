#!/usr/bin/env python3
"""Simula caída de Odoo o de la BD para evidenciar alertas en Zabbix.
Uso: python3 scripts/prueba_alerta.py [odoo|db]"""
import subprocess, sys, os
os.chdir(os.path.join(os.path.dirname(__file__), ".."))
svc = sys.argv[1] if len(sys.argv) > 1 else "odoo"
subprocess.run(["docker", "compose", "stop", svc], check=True)
input(f"{svc} detenido. Espere 2-3 min, revise Monitoring > Problems en Zabbix y presione Enter para restaurar...")
subprocess.run(["docker", "compose", "start", svc], check=True)
print("Servicio restaurado. Verifique que el problema pase a RESOLVED.")
