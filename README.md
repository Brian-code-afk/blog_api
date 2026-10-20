# Blog API

基于 **FastAPI + MySQL + Redis** 构建的博客后端 API，包含完整的用户认证、文章管理与权限隔离，配备 56 个测试用例与 Docker 编排配置。

---

## 技术栈

| 组件 | 选型 |
|---|---|
| Web 框架 | FastAPI |
| 数据库 | MySQL 8.0 |
| ORM | SQLAlchemy 2.0 |
| 迁移 | Alembic |
| 缓存 / 令牌存储 | Redis 7 |
| 认证 | JWT 双令牌（access + refresh），refresh 存 Redis 并支持轮换 |
| 密码哈希 | bcrypt |
| 测试 | pytest |
| 部署 | Docker 多阶段构建 + Docker Compose |

---

## 功能特性

### 认证
- 注册即登录，返回令牌对
- 登录支持**用户名或邮箱**两种方式
- access token 有效期 15 分钟，refresh token 7 天
- refresh token 采用**轮换机制**：每次刷新旧令牌立即失效，重放旧令牌会导致整个令牌族失效（检测到重放攻击时强制登出）
- 登出即时把 refresh token 加入黑名单

### 文章
- 创建时根据标题自动生成 `slug`，冲突自动追加随机后缀
- 支持 `draft` / `published` 两种状态
- **权限隔离**：
  - 游客只能看到已发布文章
  - 作者本人可看到自己的草稿
  - 他人的草稿返回 **404 而非 403**（避免泄露资源存在性）
- 列表接口不返回正文，详情页才返回 `content`
- 浏览量走 Redis 计数，由独立 worker 定时落库

### 工程实践
- 全局统一异常处理，错误响应格式一致
- 分页参数校验（每页最多 100 条）
- 非 root 用户运行容器
- 多阶段构建，镜像内容仅 **64.5MB**

---

## 快速开始

### 方式一：Docker（推荐）

**1. 准备环境变量**

复制模板并填写：

```bash
cp .env.example .env
```

```ini
SECRET_KEY=用 secrets.token_hex(32) 生成的 64 位十六进制字符串
DATABASE_URL=mysql+pymysql://root:devpass123@localhost:3306/blog?charset=utf8mb4
REDIS_URL=redis://localhost:6379/0
CORS_ORIGINS=["*"]
ENV=dev

# 仅 docker compose 使用
MYSQL_ROOT_PASSWORD=devpass123
MYSQL_DATABASE=blog
```

> ⚠️ MySQL 的用户名与密码**不能包含中文或 `@ # % / :`**，否则 PyMySQL 会因 latin-1 编码失败。

**2. 启动全部服务**

```bash
docker compose up -d
```

Compose 会自动完成：等待 MySQL 就绪 → 执行 Alembic 迁移 → 启动应用。

**3. 访问**

- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/healthz`

**4. 停止**

```bash
docker compose down          # 保留数据
docker compose down -v       # 连数据卷一起删除
```

---

### 方式二：本地运行

**1. 安装依赖**

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt   # 如需跑测试
```

**2. 准备 MySQL 与 Redis**

```sql
CREATE DATABASE blog CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

**3. 执行迁移**

```bash
alembic upgrade head
```

**4. 启动**

```bash
uvicorn app.main:app --reload
```

---

## 环境变量说明

| 变量 | 说明 | 默认值 |
|---|---|---|
| `SECRET_KEY` | JWT 签名密钥，必须修改 | — |
| `DATABASE_URL` | MySQL 连接串 | — |
| `REDIS_URL` | Redis 连接串 | — |
| `CORS_ORIGINS` | 允许的跨域来源，JSON 数组字符串 | `["*"]` |
| `ACCESS_TOKEN_TTL_MINUTES` | access token 有效期（分钟） | `15` |
| `REFRESH_TOKEN_TTL_DAYS` | refresh token 有效期（天） | `7` |
| `DEFAULT_PAGE_SIZE` | 默认每页条数 | `20` |
| `ENV` | `dev` 开启 Swagger，`prod` 关闭 | `dev` |
| `DB_ECHO` | 是否打印 SQL | `false` |
| `MYSQL_ROOT_PASSWORD` | 仅 compose 使用 | — |
| `MYSQL_DATABASE` | 仅 compose 使用 | `blog` |

---

## 运行测试

```bash
pytest
```

测试使用独立的 `blog_test` 数据库和 Redis db 15，不会污染开发数据。

```bash
pytest -v                    # 显示每个用例名称
pytest tests/test_auth.py    # 只跑某个文件
pytest -k "draft"            # 只跑名字含 draft 的用例
```

---

## 主要接口

完整列表以启动后的 `/docs` 为准，以下是核心接口：

### 认证 `/api/auth`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/register` | 注册，直接返回令牌对 |
| POST | `/login` | 登录，`account` 可填用户名或邮箱 |
| POST | `/refresh` | 用 refresh token 换新令牌对 |
| POST | `/logout` | 登出，令牌加入黑名单 |

### 文章 `/api/articles`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/` | 创建文章 |
| GET | `/` | 文章列表（分页） |
| GET | `/{slug}` | 文章详情，浏览量 +1 |
| PATCH | `/{slug}` | 修改自己的文章 |
| DELETE | `/{slug}` | 删除自己的文章 |

### 鉴权方式

```http
Authorization: Bearer <access_token>
```

在 Swagger 页面点右上角 **Authorize**，粘贴 `access_token` 即可（**不要带 `Bearer ` 前缀**，Swagger 会自动添加）。

---

## 项目结构

```
blog_api/
├── app/
│   ├── main.py              # 应用入口、异常处理器
│   ├── config.py            # 环境变量配置
│   ├── dependencies.py      # 依赖注入（会话、当前用户、分页）
│   ├── models/              # SQLAlchemy 模型
│   ├── schemas/             # Pydantic 请求/响应模型
│   ├── routers/             # 路由层
│   ├── services/            # 业务逻辑层
│   ├── core/                # 安全、异常处理
│   ├── db/                  # 会话与基类
│   └── utils/               # 工具函数
├── alembic/                 # 数据库迁移
├── tests/                   # pytest 用例
├── scripts/
│   ├── wait_for_db.py       # 等待 MySQL 就绪
│   └── flush_views.py       # 浏览量落库 worker
├── Dockerfile               # 多阶段构建
├── docker-compose.yml       # web + db + redis + worker
├── docker-entrypoint.sh     # 等数据库 → 迁移 → 启动
└── requirements.txt
```

---

## Docker 服务说明

| 服务 | 镜像 | 说明 |
|---|---|---|
| `web` | blog-api | FastAPI 应用，端口 8000 |
| `db` | mysql:8.0 | MySQL，端口 3306 |
| `redis` | redis:7-alpine | Redis，开启 AOF 持久化 |
| `worker` | blog-api | 每 5 分钟把浏览量增量写回 MySQL |

**服务间通过服务名通信**，容器内 `DATABASE_URL` 的主机是 `db` 而非 `localhost`，由 Docker 内置 DNS 解析。代码无需为此改动。

`worker` 与 `web` 共用同一镜像，通过 `RUN_MIGRATIONS=false` 避免两个容器并发执行数据库迁移。

### 常用命令

```bash
docker compose ps              # 查看服务状态
docker compose logs -f web     # 跟随应用日志
docker compose logs worker     # 查看 worker 日志
docker compose exec web sh     # 进入容器
docker compose build --no-cache   # 依赖更新后重新构建
```

---

## 常见问题

**启动时报 `/bin/sh^M: bad interpreter`**

`docker-entrypoint.sh` 被保存成了 CRLF 换行。在编辑器里切换为 LF 后重新构建（项目根目录的 `.gitattributes` 已强制 LF）。

**MySQL 容器端口冲突**

本地已装 MySQL 占用 3306 时，修改 `docker-compose.yml` 中 db 的端口映射为 `"3307:3306"`。

**容器启动后文章列表为空**

容器内是独立的 MySQL 实例，与本地数据库不互通。执行 `docker compose down -v` 后重新启动可得到干净环境。

**WSL2 中构建极慢或挂载失效**

`/mnt/c`、`/mnt/e` 这类跨文件系统路径性能差且不稳定。建议把项目复制到 WSL 家目录（如 `~/blog_api`）后再构建。

---

## 安全提醒

- `.env` 包含密钥，**已加入 `.gitignore`，切勿提交**
- 生产部署前务必更换 `SECRET_KEY`
- 生产环境建议设置 `ENV=prod` 关闭 Swagger 文档
- MySQL 凭据避免使用中文及 URL 特殊字符

---

## 许可证

MIT
