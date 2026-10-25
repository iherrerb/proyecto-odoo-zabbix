FROM odoo:17.0
LABEL proyecto="servidores-virtualizacion" servicio="odoo-crm"
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY config/odoo.conf /etc/odoo/odoo.conf
USER odoo
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fs http://localhost:8069/web/login || exit 1
