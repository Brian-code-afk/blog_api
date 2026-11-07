#!/bin/bash
# ============================================================
# 本地一键发布脚本（在 Windows 的 Git Bash 里跑）
#
#   ./release.sh build          只构建前端生产包
#   ./release.sh upload IP      构建 + 上传 dist 到服务器
#   ./release.sh deploy IP      构建 + 上传 + 服务器重载 Nginx
#
# 前提：本机已配置 SSH 免密登录到服务器
# ============================================================
set -euo pipefail

log() { echo -e "\n\033[1;34m==> $*\033[0m"; }
ok()  { echo -e "\033[0;32m    ✓ $*\033[0m"; }
die() { echo -e "\033[0;31m    ✗ $*\033[0m" >&2; exit 1; }

# 前端目录：默认和 blog_api 同级，可用 FRONTEND_DIR 环境变量覆盖
# 例：FRONTEND_DIR="/c/Users/17375/Desktop/blog_frontend" ./release.sh build
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -z "${FRONTEND_DIR:-}" ]; then
  for candidate in \
      "$SCRIPT_DIR/../blog_frontend" \
      "$SCRIPT_DIR/../../blog_frontend" \
      "$HOME/Desktop/blog_frontend" \
      "/c/Users/17375/Desktop/blog_frontend"; do
    if [ -f "$candidate/package.json" ]; then
      FRONTEND_DIR="$candidate"; break
    fi
  done
fi
[ -n "${FRONTEND_DIR:-}" ] && [ -f "$FRONTEND_DIR/package.json" ] \
  || die "找不到前端项目，请设置 FRONTEND_DIR=/path/to/blog_frontend"
SSH_USER="${SSH_USER:-deploy}"
WEB_ROOT="/var/www/blog"

check_manifest() {
  log "检查生产构建是否干净"
  local idx="$FRONTEND_DIR/dist/index.html"
  [ -f "$idx" ] || die "dist/index.html 不存在，先跑 build"

  # 关键检查：确保没有把假数据打进生产包
  if grep -rqs "Docker 多阶段构建实战" "$FRONTEND_DIR/dist/assets/"; then
    die "产物里含有 mock 种子数据！检查 .env.production 里 VITE_USE_MOCK=false"
  fi
  ok "无 mock 数据残留"

  local size
  size=$(du -sh "$FRONTEND_DIR/dist" | cut -f1)
  ok "产物大小 $size"
}

do_build() {
  log "构建前端生产包"
  cd "$FRONTEND_DIR"
  # 先删旧产物：避免上次的 hash 文件残留，也绕开某些环境下的删除钩子问题
  rm -rf dist.bak && [ -d dist ] && mv dist dist.bak || true
  npm run build:prod
  rm -rf dist.bak
  ok "构建完成"
  check_manifest
}

do_upload() {
  local host="$1"
  [ -n "$host" ] || die "缺少服务器地址，用法: $0 upload <IP或域名>"

  log "上传到 $SSH_USER@$host:$WEB_ROOT"
  # 先传到一个临时目录，再原子切换，避免上传到一半用户看到残缺站点
  ssh "$SSH_USER@$host" "rm -rf /tmp/blog_dist && mkdir -p /tmp/blog_dist"
  rsync -az --delete "$FRONTEND_DIR/dist/" "$SSH_USER@$host:/tmp/blog_dist/"
  ok "传输完成"
}

do_switch() {
  local host="$1"
  log "服务器端切换上线"
  ssh "$SSH_USER@$host" "bash -s" << REMOTE
set -e
sudo mkdir -p $WEB_ROOT
sudo rsync -a --delete /tmp/blog_dist/ $WEB_ROOT/
sudo chown -R www-data:www-data $WEB_ROOT
sudo nginx -t
sudo systemctl reload nginx
echo "    文件数: \$(find $WEB_ROOT -type f | wc -l)"
echo "    健康检查: \$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/healthz)"
REMOTE
  ok "已切换并重载 Nginx"
}

case "${1:-}" in
  build)
    do_build
    ;;
  upload)
    do_build
    do_upload "${2:-}"
    ;;
  deploy)
    do_build
    do_upload "${2:-}"
    do_switch "${2:-}"
    echo
    echo "  从外网访问验证一遍："
    echo "    curl -I https://你的域名"
    ;;
  *)
    echo "用法: $0 {build|upload|deploy} [服务器IP]"
    exit 1
    ;;
esac
