#!/bin/sh
set -eu
umask 077
cd "$(dirname "$0")"
: "${KNOWLEDGE_DATABASE_URL:=dbname=knowledge_agent host=/tmp}"
backup_dir="../runtime/backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
pg_dump --dbname="$KNOWLEDGE_DATABASE_URL" --format=custom --file="$backup_dir/database.dump"
tar -czf "$backup_dir/materials.tar.gz" -C ../runtime materials
if command -v sha256sum >/dev/null 2>&1; then
  sha256sum "$backup_dir/database.dump" "$backup_dir/materials.tar.gz" > "$backup_dir/SHA256SUMS"
else
  shasum -a 256 "$backup_dir/database.dump" "$backup_dir/materials.tar.gz" > "$backup_dir/SHA256SUMS"
fi
printf '备份已保存：%s\n' "$backup_dir"
printf '备份不包含模型Key的加密主密钥，请按服务运行配置单独安全保管主密钥文件或KNOWLEDGE_ENCRYPTION_KEY。\n'
