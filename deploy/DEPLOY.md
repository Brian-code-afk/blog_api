# 博客全栈部署上线手册

> 目标：把 FastAPI + MySQL + Redis + Vue3 这套项目，部署到一台云服务器上，
> 通过域名 + HTTPS 对外访问。
>
> 参考环境：Ubuntu 22.04 / 2 核 2G / 云服务器（阿里云、腾讯云、华为云均可）

---

## 零、在开始之前，先理解三件事

### 1. 前端不是"跑一个 Node 服务"

`npm run build` 之后，Vue 代码会被编译成纯静态文件（HTML + JS + CSS），
浏览器的活全在客户端完成，**服务器上不需要装 Node**。

所以前端部署 = 把 `dist/` 目录里的文件放到 Nginx 的网站根目录。

### 2. Nginx 同时干两件事

```nginx
location /      { try_files $uri $uri/ /index.html; }   # 静态文件
location /api/  { proxy_pass http://127.0.0.1:8000; }   # 转发给 FastAPI
```

对浏览器来说，前端和接口是**同一个域名**，所以根本不存在跨域问题。
这比配 `CORS_ORIGINS` 干净得多 —— 生产环境可以按需把 CORS 关掉。

### 3. 只有 80/443 对外开放

| 端口 | 谁在听 | 是否对外开放 |
| --- | --- | --- |
| 80 / 443 | Nginx | ✅ 必须开 |
| 8000 | FastAPI 容器 | ❌ 只绑 `127.0.0.1` |
| 3306 | MySQL 容器 | ❌ 完全不映射 |
| 6379 | Redis 容器 | ❌ 完全不映射 |
| 22 | SSH | ✅ 建议限 IP |

**数据库端口暴露到公网 = 几小时内就会被自动化脚本扫到并尝试撞库。**
这类事故在云服务器上极其常见，`docker-compose.prod.yml` 里已经按这个原则配置好了。

---

## 一、买服务器（约 10 分钟）

### 选配置

| 项目 | 推荐 | 说明 |
| --- | --- | --- |
| 系统 | Ubuntu 22.04 LTS | 生态最好，命令和你的 WSL2 经验通用 |
| CPU / 内存 | 2 核 2G 起 | MySQL 单独就要 400MB+，1G 内存会 OOM |
| 磁盘 | 40G 系统盘 | Docker 镜像 + 数据，够用很久 |
| 带宽 | 3M 起 | 博客够用；图片多建议配 OSS |

新用户通常有首年优惠（几十到一百多），学生认证更便宜。

### 安全组 / 防火墙

在云控制台的安全组里，**只放行这三个端口**：

```
22   (SSH)     来源：你的固定 IP，或 0.0.0.0/0（不推荐）
80   (HTTP)    来源：0.0.0.0/0
443  (HTTPS)   来源：0.0.0.0/0
```

⚠️ 不要图省事"放行全部端口"。3306/6379 一旦对外开放，被扫到只是时间问题。

### 域名（可选但强烈建议）

1. 在域名商买域名，完成**实名认证**（国内必须）
2. 添加一条 A 记录：`blog.你的域名.com` → 服务器公网 IP
3. 国内服务器的域名需要 **ICP 备案**，没备案的话 80/443 会被拦
   - 不想备案就用香港/境外服务器，或者干脆先用 IP 访问测试

用 `ping blog.你的域名.com` 确认解析生效后再继续。

---

## 二、初始化服务器（约 15 分钟）

### 2.1 登录并创建用户

```bash
ssh root@你的服务器IP
```

```bash
# 建一个日常使用的普通用户（别一直用 root 跑应用）
adduser deploy
usermod -aG sudo deploy

# 把本机的公钥拷过去，之后免密登录
# 在【你自己的电脑】上执行：
#   ssh-copy-id deploy@你的服务器IP
```

之后都用 `ssh deploy@你的服务器IP` 登录。

### 2.2 基础系统配置

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git rsync nginx ufw

# 时区设置成中国时区，否则日志时间对不上
sudo timedatectl set-timezone Asia/Shanghai

# 防火墙（和云安全组是两层，都要配）
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw enable
sudo ufw status
```

> UFW 和云安全组是**两层独立防线**，两层都放行才通。排查"连不上"时两边都要看。

### 2.3 安装 Docker

用官方脚本最省事：

```bash
curl -fsSL https://get.docker.com | sudo sh

# 让 deploy 用户不用 sudo 就能跑 docker（必须重新登录才生效）
sudo usermod -aG docker deploy
exit
# 重新 ssh 进来
ssh deploy@你的服务器IP
docker --version
docker compose version
```

**国内服务器拉镜像慢**，先配加速器：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1ms.run"
  ],
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
sudo systemctl daemon-reload
sudo systemctl restart docker
docker info | grep -A 3 "Registry Mirrors"
```

> 公共加速器稳定性一般，拉不动就删掉 `registry-mirrors` 用官方源。
> ⚠️ 云厂商自己的镜像服务（如阿里云容器镜像服务）更稳，需要登录控制台获取专属地址。

### 2.4 加 Swap（2G 内存必做）

内存只有 2G 时，构建镜像很容易被 OOM 杀掉。加 2G swap 兜底：

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h    # 确认 Swap 那行有值
```

---

## 三、上传代码

有两种方式，选一种即可。

### 方式 A：Git（推荐，后续更新最省事）

本机先推到 GitHub / Gitee（**注意 `.env` 不能提交**，`.gitignore` 已排除）：

```bash
cd E:\blog_api
git add .
git commit -m "chore: 准备生产部署"
git push
```

服务器上：

```bash
git clone 你的仓库地址 ~/blog_api
```

### 方式 B：直接传文件（U 盘里的代码，没有远程仓库时用）

在 **Windows PowerShell** 里执行（把 IP 换成你的）：

```powershell
# 用 scp 直接传，排除掉不需要的东西
scp -r E:\blog_api deploy@你的服务器IP:~/blog_api_temp

# 更推荐用 rsync（Windows 可装 Git Bash 后使用）：
# rsync -av --exclude .venv --exclude .git --exclude __pycache__ --exclude .idea --exclude .env \
#   /e/blog_api/ deploy@你的服务器IP:~/blog_api/
```

⚠️ **`.env` 不要传**。生产环境用独立的 `.env.prod`，密钥完全不同。

---

## 四、配置生产环境变量（关键步骤）

在服务器上：

```bash
cd ~/blog_api

# 从模板生成实际配置
cp .env.prod.example .env.prod
chmod 600 .env.prod        # 只有自己能读

# 生成强随机密钥
openssl rand -hex 32
```

编辑 `.env.prod`：

```bash
nano .env.prod
```

必须改的四处：

| 变量 | 改成什么 | 为什么 |
| --- | --- | --- |
| `JWT_SECRET` | 上面 `openssl rand -hex 32` 生成的值 | 开发密钥泄露 = 别人能伪造任意用户登录 |
| `MYSQL_ROOT_PASSWORD` | 强密码，**纯 ASCII** | 含中文会报 `latin-1 codec can't encode` |
| `DATABASE_URL` | 里的密码要和上一行**完全一致** | 不一致就连不上库 |
| `ENV` / `DB_ECHO` | `prod` / `false` | dev 会打印每条 SQL，日志暴涨 |

密码要避开 `@ # % / :` 这些字符 —— 它们在 URL 格式里有特殊含义，会解析错。

---

## 五、部署后端

```bash
cd ~/blog_api

# 两个 compose 文件叠加：基础配置 + 生产覆盖
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.prod up -d --build
```

首次构建要下基础镜像和依赖，**十几到二十分钟很正常**，别中途 Ctrl+C。

看状态：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
```

期望输出：

```
NAME              STATUS
blog_api_db       Up (healthy)
blog_api_redis    Up (healthy)
blog_api_web      Up (healthy)      ← 可能要等 40 秒才变 healthy
blog_api_worker   Up
```

验证后端：

```bash
curl http://127.0.0.1:8000/healthz
# {"code":0,"message":"ok","data":{"env":"prod"}}   ← env 应该是 prod
```

> 如果 `env` 还是 `dev`，说明 `.env.prod` 没被读到，检查 `--env-file` 参数。

---

## 六、构建并发布前端

### 6.1 在服务器上构建（推荐）

```bash
# 用官方 Node 镜像构建，避免在服务器上装 Node
docker run --rm -v ~/blog_frontend:/app -w /app node:22-alpine \
  sh -c "npm ci && npm run build:prod"
```

产物会出现在 `~/blog_frontend/dist`。

> 也可以在本机构建好再 `scp` 上去：`scp -r dist deploy@IP:~/blog_dist`。
> 两种都行，服务器上构建的好处是环境一致、可复现。

### 6.2 发布到 Nginx 目录

```bash
sudo mkdir -p /var/www/blog
sudo rsync -a --delete ~/blog_frontend/dist/ /var/www/blog/
sudo chown -R www-data:www-data /var/www/blog
ls /var/www/blog    # 应该看到 index.html 和 assets/
```

> `rsync` 源路径结尾的 `/` 不能省 —— 少了它会把 `dist` 目录本身塞进去，
> 变成 `/var/www/blog/dist/index.html`，访问就是 404。

---

## 七、配置 Nginx

```bash
# 1. 拷配置（仓库里已提供）
sudo cp ~/blog_api/deploy/nginx-blog.conf /etc/nginx/sites-available/blog

# 2. 改域名（两处 server_name）
sudo nano /etc/nginx/sites-available/blog

# 3. 启用站点
sudo ln -s /etc/nginx/sites-available/blog /etc/nginx/sites-enabled/

# 4. 删掉默认站点，否则它会抢占 80 端口
sudo rm -f /etc/nginx/sites-enabled/default

# 5. 语法检查（必须先过再 reload）
sudo nginx -t

# 6. 重载
sudo systemctl reload nginx
```

现在用 **IP 或域名 + http** 访问，应该能看到博客首页了。

> 如果页面出来了但文章列表报错，F12 看 Network：
> `/api/articles` 返回 502 → 后端没起；返回 404 → Nginx 反代路径写错。

---

## 八、配 HTTPS 证书（免费）

用 Let's Encrypt，证书 90 天有效，自动续期。

```bash
sudo apt install -y certbot python3-certbot-nginx

# 一条命令搞定：申请证书 + 改写 Nginx 配置 + 配好自动跳转
sudo certbot --nginx -d blog.你的域名.com
```

按提示填邮箱、同意协议，选 **Redirect**（把 http 全部跳到 https）。

验证自动续期：

```bash
sudo certbot renew --dry-run
```

看到 `Congratulations` 就说明续期没问题（systemd timer 会自动跑）。

### 证书就绪后收紧 Nginx

`nginx-blog.conf` 里已经写好了 443 配置和 http→https 跳转，
certbot 会自动把 `ssl_certificate` 两行填进去。检查一下：

```bash
sudo nginx -t && sudo systemctl reload nginx
curl -I https://blog.你的域名.com
# 应该看到 200，并且有 strict-transport-security 响应头
```

---

## 九、验收清单

逐条过一遍，全部打勾才算真上线：

- [ ] `https://域名` 能打开，地址栏有小锁
- [ ] `http://域名` 自动跳到 `https://`
- [ ] 首页能列出真实文章（不是内置的 6 篇假数据）
- [ ] 登录能成功（`curl` 测过接口，浏览器也要测一次）
- [ ] **直接刷新** `/article/某篇文章` 不 404（这是 SPA 最常见的坑）
- [ ] 发布一篇文章，正文 Markdown 渲染正常
- [ ] 退出登录后，访问"我的文章"被踢回登录页
- [ ] `https://域名/api/articles` 返回 JSON（说明反代通）
- [ ] `https://域名/docs` 返回 404（文档已关闭）
- [ ] 从手机流量（非 WiFi）访问也正常

---

## 十、日常更新流程

改完代码后：

```bash
# 本机
git add . && git commit -m "feat: xxx" && git push

# 服务器
cd ~/blog_api && git pull

# 后端有改动时重建（只改前端可跳过这步）
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  --env-file .env.prod up -d --build

# 前端有改动时重新构建并发布
docker run --rm -v ~/blog_frontend:/app -w /app node:22-alpine \
  sh -c "npm ci && npm run build:prod"
sudo rsync -a --delete ~/blog_frontend/dist/ /var/www/blog/
```

仓库里提供了 `deploy/deploy-blog.sh`，把上面这些串成了一条命令：

```bash
chmod +x ~/deploy-blog.sh
~/deploy-blog.sh update
```

**只有数据卷不会被碰**：`docker compose down` 不加 `-v` 就不删数据；
真要彻底重来才加 `-v`，那时 MySQL 数据会全部丢失。

---

## 十一、运维日常

```bash
# 看日志
docker compose logs -f --tail 100 web

# 看资源
docker stats

# 进容器
docker exec -it blog_api_web sh

# 备份数据库（建议配 cron 每天跑）
docker exec blog_api_db sh -c \
  'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction blog' \
  | gzip > ~/backup/blog-$(date +%F).sql.gz

# Nginx 日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

---

## 十二、常见故障速查

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| 浏览器打不开，curl 本机正常 | 安全组 / UFW 没放行 | 云控制台安全组 + `sudo ufw status` 两边都查 |
| 502 Bad Gateway | 后端容器挂了 | `docker compose ps` → `docker compose logs web` |
| 首页正常，刷新子页面 404 | 缺 SPA 回落 | 检查 `try_files $uri $uri/ /index.html;` |
| 页面是旧版本 | index.html 被缓存 | 确认 `index.html` 配了 `no-cache`，强刷 Ctrl+F5 |
| `/api` 返回 404 | 反代路径错 | `proxy_pass` 结尾别加 `/`，否则会吃掉 `/api` 前缀 |
| 登录一直失败 | JWT_SECRET 为空或前后不一致 | `docker compose logs web` 看启动日志是否报密钥校验失败 |
| MySQL 容器反复重启 | 密码含中文或特殊字符 | 改纯 ASCII 密码，再 `down -v` 重建（数据会丢，首次部署无妨） |
| 构建时被 Killed | 内存不足 OOM | 加 swap；或在本机构建后只传镜像 |
| 容器起来但连不上库 | 用了 `localhost` | 容器内必须用服务名 `db` / `redis` |
| 磁盘满了 | 镜像和日志堆积 | `docker system df` → `docker system prune` |

---

## 附：上线后的安全加固（可选但建议）

1. **SSH 禁密码登录**
   ```bash
   sudo nano /etc/ssh/sshd_config
   # PasswordAuthentication no
   sudo systemctl restart ssh
   ```
   ⚠️ 改之前确认公钥登录已经可用，否则会把自己锁在外面。

2. **限制 22 端口来源 IP**：在云安全组里把 SSH 规则改成只允许自己的 IP。

3. **装 fail2ban**，自动封禁暴力破解 IP：
   ```bash
   sudo apt install -y fail2ban
   sudo systemctl enable --now fail2ban
   ```

4. **定期更新系统**：
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```
