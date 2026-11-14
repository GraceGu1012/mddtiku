#!/bin/bash
set -euo pipefail
# Run once on the explicitly authorized host, after uploading the migration snapshot.
BASE=/opt/mdd-knowledge
if ! id mddknowledge >/dev/null 2>&1; then useradd --system --home-dir "$BASE" --shell /sbin/nologin mddknowledge; fi
if [ "$(runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='mdd_knowledge'")" = 1 ]; then
 echo 'Target database already exists; refusing to overwrite.'; exit 1
fi
tar -xzf /opt/mdd-knowledge-import/application.tar.gz -C "$BASE"
python3 -m venv "$BASE/venv"
"$BASE/venv/bin/pip" install --disable-pip-version-check -r "$BASE/apps/knowledge-agent/web/requirements.txt" > /opt/mdd-knowledge-import/install.log 2>&1
runuser -u postgres -- createuser mddknowledge
runuser -u postgres -- createdb --owner=mddknowledge --template=template0 --encoding=UTF8 --lc-collate=C --lc-ctype=C mdd_knowledge
{ printf 'SET ROLE mddknowledge;\n'; cat /opt/mdd-knowledge-import/database.sql; } | runuser -u postgres -- psql --set=ON_ERROR_STOP=1 --dbname=mdd_knowledge > /opt/mdd-knowledge-import/restore.log
runuser -u postgres -- psql --set=ON_ERROR_STOP=1 --dbname=mdd_knowledge -c "UPDATE materials SET path='/opt/mdd-knowledge/apps/knowledge-agent/runtime/materials/' || regexp_replace(path,'^.*/','');"
chown -R mddknowledge:mddknowledge "$BASE/apps/knowledge-agent/runtime"
chmod 700 "$BASE/apps/knowledge-agent/runtime"
chmod 755 /etc/mdd-knowledge
chown mddknowledge:mddknowledge /etc/mdd-knowledge/master.key
chmod 600 /etc/mdd-knowledge/master.key
cat > /etc/mdd-knowledge/service.env <<'ENV'
KNOWLEDGE_PORT=14312
KNOWLEDGE_PUBLIC_ORIGIN=https://8.130.110.58:4312
KNOWLEDGE_DATABASE_URL="dbname=mdd_knowledge host=/var/run/postgresql user=mddknowledge"
KNOWLEDGE_STORAGE_DIR=/opt/mdd-knowledge/apps/knowledge-agent/runtime/materials
KNOWLEDGE_MASTER_KEY_FILE=/etc/mdd-knowledge/master.key
KNOWLEDGE_WORKER=1
ENV
chmod 600 /etc/mdd-knowledge/service.env
openssl req -x509 -newkey rsa:3072 -nodes -keyout /etc/mdd-knowledge/tls.key -out /etc/mdd-knowledge/tls.crt -days 365 -subj '/CN=8.130.110.58' -addext 'subjectAltName=IP:8.130.110.58' 2>/dev/null
chmod 600 /etc/mdd-knowledge/tls.key
cp "$BASE/apps/knowledge-agent/web/deploy/mdd-knowledge.service" /etc/systemd/system/
cp "$BASE/apps/knowledge-agent/web/deploy/nginx-4312.conf" /etc/nginx/conf.d/mdd-knowledge-4312.conf
nginx -t
systemctl daemon-reload
systemctl enable --now mdd-knowledge
systemctl reload nginx
systemctl is-active mdd-knowledge
