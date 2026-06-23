#!/usr/bin/env bash
# 一条命令在「本机」装好数据库：装 Postgres + pgvector、建库建角色、启用扩展、把 dsn 写进 micall.env。
# 之后后端开机会自动建表（PgRepository 自带 schema 自举），无需再跑任何脚本。
#
#   sudo bash deploy/setup_db_server.sh
#
# 幂等：可反复跑。仅适用于「服务器自建 Postgres」（Ubuntu/Debian）。用阿里云 RDS 看 deploy/database.md。
# 自定义：DB_NAME / DB_USER / DB_PASS 可用环境变量覆盖（不给 DB_PASS 则自动生成强密码）。
set -euo pipefail

DB_NAME="${DB_NAME:-micall}"
DB_USER="${DB_USER:-micall}"
DB_PASS="${DB_PASS:-$(openssl rand -hex 16)}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/backend/config/micall.env"

if [[ $EUID -ne 0 ]]; then echo "✗ 需要 root：请用 sudo 运行" >&2; exit 1; fi
if ! command -v apt-get >/dev/null; then
  echo "✗ 非 Debian/Ubuntu。请按 deploy/database.md 手动装 Postgres+pgvector，或用 deploy/docker-compose.db.yml" >&2; exit 1
fi

echo "[1/5] 安装 Postgres + pgvector …"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq postgresql postgresql-contrib openssl >/dev/null
PGVER="$(ls /usr/lib/postgresql/ 2>/dev/null | sort -n | tail -1)"
if [[ -z "$PGVER" ]]; then echo "✗ 没找到 Postgres 安装目录" >&2; exit 1; fi
apt-get install -y -qq "postgresql-${PGVER}-pgvector" >/dev/null \
  || { echo "✗ 装 postgresql-${PGVER}-pgvector 失败（该 PG 版本暂无 pgvector 包，换用 Docker 方案）" >&2; exit 1; }
systemctl enable --now postgresql >/dev/null 2>&1 || true

echo "[2/5] 建角色 $DB_USER …"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1 \
  && sudo -u postgres psql -qc "ALTER ROLE $DB_USER LOGIN PASSWORD '$DB_PASS'" \
  || sudo -u postgres psql -qc "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS'"

echo "[3/5] 建库 $DB_NAME …"
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 \
  || sudo -u postgres psql -qc "CREATE DATABASE $DB_NAME OWNER $DB_USER"

echo "[4/5] 启用 pgvector 扩展 + 授权 …"
sudo -u postgres psql -d "$DB_NAME" -qc "CREATE EXTENSION IF NOT EXISTS vector"
sudo -u postgres psql -d "$DB_NAME" -qc "GRANT ALL ON SCHEMA public TO $DB_USER"

echo "[5/5] 写连接串到 $ENV_FILE …"
DSN="postgresql://$DB_USER:$DB_PASS@127.0.0.1:5432/$DB_NAME"
mkdir -p "$(dirname "$ENV_FILE")"; touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
# 替换或追加 MICALL_DATABASE_DSN 行
if grep -q '^MICALL_DATABASE_DSN=' "$ENV_FILE"; then
  sed -i "s#^MICALL_DATABASE_DSN=.*#MICALL_DATABASE_DSN=$DSN#" "$ENV_FILE"
else
  echo "MICALL_DATABASE_DSN=$DSN" >> "$ENV_FILE"
fi

echo
echo "✓ 数据库就绪。连接串已写入 micall.env（库已建，表会在后端开机时自动建好）。"
echo "  下一步：重启后端 →  sudo systemctl restart micall-backend"
echo "  验证：journalctl -u micall-backend -n 10 | grep '持久化已启用'"
