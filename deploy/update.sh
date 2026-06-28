#!/usr/bin/env bash
# 例行更新（一条命令）：拉代码 → 重建两个前端并发布 → 重启后端 → 看跨通记忆诊断。
# 在服务器仓库里跑：  bash deploy/update.sh            （别加 sudo，脚本内部按需 sudo；npm 要以普通用户跑）
# 可选参数： --backend-only（只拉代码+重启后端） --no-admin（不重建后台） --no-pull（跳过 git pull）
# 路径/服务名默认对齐线上，可用环境变量覆盖：WEB_USER、WEB_ADMIN、SERVICE、BRANCH。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WEB_USER="${WEB_USER:-/var/www/micall}"
WEB_ADMIN="${WEB_ADMIN:-/var/www/micall-admin}"
SERVICE="${SERVICE:-micall-backend}"
BRANCH="${BRANCH:-main}"
DO_PULL=1; DO_FRONTEND=1; DO_ADMIN=1
for a in "$@"; do case "$a" in
  --backend-only) DO_FRONTEND=0; DO_ADMIN=0 ;;
  --no-admin)     DO_ADMIN=0 ;;
  --no-pull)      DO_PULL=0 ;;
  -h|--help)      grep '^#' "$0" | sed 's/^# \?//'; exit 0 ;;
  *) echo "未知参数：$a（用 --help 看用法）"; exit 2 ;;
esac; done

echo "▶ 仓库：$REPO  | 后端服务：$SERVICE"
cd "$REPO"
[ "$DO_PULL" = 1 ] && { echo "▶ 拉代码（origin/$BRANCH）…"; git pull origin "$BRANCH"; }

publish() {  # $1=子项目目录 $2=web根 $3=名字
  local dir="$REPO/$1" web="$2" name="$3"
  echo "▶ 构建 $name（$dir）…"
  cd "$dir"
  if [ -f package-lock.json ]; then npm ci; else npm install; fi
  npm run build
  echo "▶ 发布 $name → $web"
  sudo mkdir -p "$web"
  sudo rm -rf "${web:?}/"*          # ${web:?} 防止 web 变量为空时误删 /*
  sudo cp -r dist/* "$web/"
}

if [ "$DO_FRONTEND" = 1 ]; then
  [ -f "$REPO/frontend/.env.production" ] || \
    echo "⚠️ frontend/.env.production 不存在——构建出的前端可能缺 WS/ICE 配置（RTC 失效）。见 deploy/README.md。"
  publish frontend "$WEB_USER" "用户端"
fi
[ "$DO_ADMIN" = 1 ] && publish admin "$WEB_ADMIN" "后台"

echo "▶ 重启后端 $SERVICE…"
sudo systemctl restart "$SERVICE"
sleep 1
systemctl is-active "$SERVICE" >/dev/null 2>&1 && echo "  后端：active ✅" || { echo "  后端未 active ❌，看日志："; sudo journalctl -u "$SERVICE" -n 30 --no-pager; exit 1; }

echo "▶ 跨通记忆诊断（持久化 / 慢脑 / 语义记忆）："
sleep 1
sudo journalctl -u "$SERVICE" -n 200 --no-pager 2>/dev/null | grep 🧠 | tail -1 || echo "  （还没抓到 🧠，过几秒手动跑： sudo journalctl -u $SERVICE -n 200 | grep 🧠 ）"
echo "✅ 完成。"
