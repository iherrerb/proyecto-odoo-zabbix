#!/usr/bin/env bash
# Recolecta evidencias de la Entrega 3 en docs/evidencias/entrega3/
set -uo pipefail
cd "$(dirname "$0")/.."
OUT="docs/evidencias/entrega3"; mkdir -p "$OUT"; F="$OUT/evidencias_$(date +%Y%m%d_%H%M%S).txt"
sec(){ echo -e "\n==================== $1 ====================" | tee -a "$F"; }
run(){ echo "\$ $*" | tee -a "$F"; eval "$@" 2>&1 | tee -a "$F"; }
sec "1. Contenedores del stack";  run "docker compose ps"
sec "2. Imágenes";                run "docker images | grep -E 'odoo|postgres|zabbix'"
sec "3. Redes";                   run "docker network ls | grep proyecto"
sec "4. Agente Zabbix";           run "docker compose exec -T zabbix-agent zabbix_agent2 -t agent.ping"
run "docker compose exec -T zabbix-agent zabbix_agent2 -t docker.ping"
sec "5. Logs del servidor Zabbix"; run "docker compose logs --no-color --tail=40 zabbix-server"
sec "6. Recursos";                run "docker stats --no-stream"
echo -e "\nEvidencias en $OUT/" | tee -a "$F"
