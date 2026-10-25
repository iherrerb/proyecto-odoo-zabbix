# Proyecto final – Odoo CRM contenedorizado, automatizado con Python y monitoreado con Zabbix
Requisitos: VM Ubuntu Server 24.04 (2 vCPU, 6 GB RAM, 30 GB disco), Python 3, Docker + Compose v2.
```bash
git clone <URL_REPO> && cd <repo>
cp .env.example .env        # ajustar contraseñas
python3 scripts/deploy.py   # despliega todo y configura Zabbix por API
```
| Servicio | URL |
|---|---|
| Odoo CRM | http://IP:8069 (crear base de datos y activar app CRM) |
| Zabbix | http://IP:8080 (Admin / zabbix – cambiar tras primer ingreso) |

Otros scripts: `destroy.py [--volumes]`, `backup.py`, `prueba_alerta.py [odoo|db]`.
