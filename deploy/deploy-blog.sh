#!/bin/bash
# ============================================================
# 服务器端一键部署 / 更新脚本
#
# 首次使用：
#   chmod +x ~/deploy-blog.sh
#   ~/deploy-blog.sh init
#
# 日常更新代码后：
#   ~/deploy-blog.sh update
#
# 注意：本文件必须是 LF 换行，否则报 /bin/bash^M: bad interpreter
# ============================================================
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$HOME/blog_api}"
FRONTEND_DIST="${FRONTEND_DIST:-$HOME/blog_dist}"
WEB_ROOT="/var/www/blog"

log()  { echo -e "\n\033[1;34m==> $*\033[0m"; }
ok()   { echo -e "\033[0;32m    ✓ $*\033[0m"; }
die()  { echo -e "\033[0;31m    ✗ $*\033[0m" >&2; exit 1; }

need_root() {
  if [ "$(id -u)" -eq 0 ]; then
    die "这个脚本不要用 root 跑，用普通用户跑，内部按需 sudo"
  fi
}

preflight() {
  log "环境预检"
  command -v docker >/dev/null || die "没装 docker"
  docker compose version >/dev/null 2>&1 || die "没装 docker compose 插件"
  ok "docker $(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"

  [ -f "$PROJECT_DIR/docker-compose.yml" ] || die "找不到 $PROJECT_DIR/docker-compose.yml"
  [ -f "$PROJECT_DIR/.env.prod" ] || die "找不到 $PROJECT_DIR/.env.prod，先 cp .env.prod.example .env.prod 并填值"

  if grep -q "CHANGE_ME" "$PROJECT_DIR/.env.prod"; then
    die ".env.prod 里还有 CHANGE_ME 占位符没改，改完再跑"
  fi
  ok "配置文件就绪"

  # 端口冲突检查：本机已装 MySQL/Redis 会抢占端口
  for p in 3306 6379 8000; do
    if ss -lntp 2>/dev/null | grep -q ":$p "; then
      echo "    ! 宿主机 $p 端口已被占用，若启动失败请先停掉本机服务"
    fi
  done
}

deploy_backend() {
  log "构建并启动后端容器"
  cd "$PROJECT_DIR"
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    --env-file .env.prod up -d --build
  ok "容器已启动"

  log "等待 web 健康检查通过（最多 90 秒）"
  for i in $(seq 1 45); do
    status=$(docker inspect -f '{{.State.Health.Status}}' blog_api_web 2>/dev/null || echo "missing")
    case "$status" in
      healthy) ok "web 健康"; return 0 ;;
      unhealthy) docker compose logs --tail 50 web; die "web 不健康，看上面的日志" ;;
    esac
    sleep 2
  done
  docker compose logs --tail 50 web
  die "90 秒内未变健康，日志已输出"
}

deploy_frontend() {
  log "发布前端静态文件"
  [ -d "$FRONTEND_DIST" ] || die "找不到前端产物目录 $FRONTEND_DIST"

  sudo mkdir -p "$WEB_ROOT"
  # --delete：清掉旧版本残留的 hash 文件名，避免目录越堆越大
  # 注意源路径结尾的 / 不能省，否则会把 dist 整个目录塞进 web root
  sudo rsync -a --delete "$FRONTEND_DIST/" "$WEB_ROOT/"
  sudo chown -R www-data:www-data "$WEB_ROOT"
  ok "已同步到 $WEB_ROOT（$(find "$WEB_ROOT" -type f | wc -l) 个文件）"
}

reload_nginx() {
  log "校验并重载 Nginx"
  sudo nginx -t || die "Nginx 配置有语法错误，上面是详情"
  sudo systemctl reload nginx
  ok "Nginx 已重载"
}

health_check() {
  log "端到端验证"
  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/healthz || true)
  [ "$code" = "200" ] && ok "后端 /healthz 200" || die "后端不可用（$code）"

  code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/api/articles?page_num=1\&page_size=1 || true)
  [ "$code" = "200" ] && ok "经 Nginx 访问 /api 200" || die "Nginx 反代不通（$code）"

  echo
  echo "  现在从外网打开你的域名试试，重点验证："
  echo "    1. 首页能列出文章"
  echo "    2. 登录 alice / 你的生产密码"
  echo "    3. 直接刷新 /article/xxx 详情页不 404"
}

case "${1:-}" in
  init)
    need_root
    preflight
    deploy_backend
    deploy_frontend
    reload_nginx
    health_check
    ;;
  update)
    need_root
    preflight
    deploy_backend
    deploy_frontend
    reload_nginx
    health_check
    ;;
  logs)
    cd "$PROJECT_DIR" && docker compose logs -f --tail 100 ${2:-}
    ;;
  status)
    cd "$PROJECT_DIR" && docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
    echo && du -sh "$WEB_ROOT" 2>/dev/null
    ;;
  *)
    echo "用法: $0 {init|update|logs|status}"
    echo "  init    首次部署：构建后端 + 发布前端 + 重载 Nginx + 验证"
    echo "  update  代码更新后重新部署（流程同上）"
    echo "  logs    跟踪容器日志，可加服务名：$0 logs web"
    echo "  status  查看容器与静态文件状态"
    exit 1
    ;;
esac
