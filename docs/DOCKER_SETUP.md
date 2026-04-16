# Docker 部署指南

> 文档角色：本文件只负责 Docker 相关链路，包括基础设施、轻量运行、完整开发和完整部署。

## 1. 先选 Docker 模式

SpiderBilibili 现在有四种 Docker 用法：

### 模式 A：只启动基础设施

适合：
- 本地开发时只把 PostgreSQL 和 Redis 放进容器

配置文件：
- `docker-compose.yml`

### 模式 B：轻量整套 Docker 运行

适合：
- 用户不想在宿主机安装 Python / Node / Playwright
- 只想直接把完整应用跑起来

入口：
- `launch-docker.bat`
- `close-docker.bat`

配置文件：
- `docker-compose.app.yml`

### 模式 C：完整 Docker 开发

适合：
- 需要看源码
- 需要完整重依赖
- 希望前后端开发环境都在容器里

入口：
- `launch-docker-dev.bat`
- `close-docker-dev.bat`

配置文件：
- `docker-compose.dev-full.yml`

### 模式 D：完整 Docker 部署

适合：
- 服务器部署
- 生产或准生产验收
- 完整容器化运行

配置文件：
- `docker-compose.prod.yml`

## 2. 前置要求

- Docker Engine 24+ 或 Docker Desktop
- Docker Compose v2

确认命令可用：

```powershell
docker --version
docker compose version
```

## 3. 模式 A：只启动基础设施

启动：

```powershell
docker compose up -d
```

会启动：
- PostgreSQL
- Redis

默认端口映射：
- PostgreSQL：`5434 -> 5432`
- Redis：`6381 -> 6379`

查看状态：

```powershell
docker compose ps
```

查看日志：

```powershell
docker compose logs -f
```

停止：

```powershell
docker compose down
```

说明：
- 这种模式下，前端、后端、Worker 仍按本地方式启动
- 对应教程见 `docs/LOCAL_SETUP.md`

## 4. 模式 B：轻量整套 Docker 运行

### 4.1 启动器方式

启动：

```powershell
.\launch-docker.bat
```

关闭：

```powershell
.\close-docker.bat
```

### 4.2 手动方式

先复制模板：

```powershell
Copy-Item docker/.env.app.local.example docker/.env.app.local
```

启动：

```powershell
docker compose --env-file docker/.env.app.local -f docker-compose.app.yml up -d --build
```

停止：

```powershell
docker compose --env-file docker/.env.app.local -f docker-compose.app.yml down
```

### 4.3 会启动什么

- `postgres`
- `redis`
- `backend`
- `worker`
- `web`

说明：
- 不包含 Prometheus、Grafana、Alertmanager
- 适合“用户开箱即用运行”

### 4.4 默认入口

- Web：`http://127.0.0.1:8080`

## 5. 模式 C：完整 Docker 开发

### 5.1 启动器方式

启动：

```powershell
.\launch-docker-dev.bat
```

关闭：

```powershell
.\close-docker-dev.bat
```

### 5.2 手动方式

先复制模板：

```powershell
Copy-Item docker/.env.dev-full.example docker/.env.dev-full
```

启动：

```powershell
docker compose --env-file docker/.env.dev-full -f docker-compose.dev-full.yml up -d --build
```

停止：

```powershell
docker compose --env-file docker/.env.dev-full -f docker-compose.dev-full.yml down
```

### 5.3 会启动什么

- `postgres`
- `redis`
- `backend`
- `worker`
- `frontend`

说明：
- 这是完整开发链路，不是轻量运行链路
- 会在容器里装齐完整 Python 依赖和前端依赖
- `backend` 和 `frontend` 都挂载源码目录，适合看代码和调试

### 5.4 默认入口

- 前端：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8014/api`

## 6. 模式 D：完整 Docker 部署

适合以下场景：
- 服务器部署
- 完整容器化验收
- 需要监控组件

整套部署默认包含：
- `postgres`
- `redis`
- `backend`
- `worker`
- `nginx`
- `redis-exporter`
- `postgres-exporter`
- `prometheus`
- `alertmanager`
- `grafana`

## 7. 完整 Docker 部署前准备

### 7.1 复制生产环境模板

```powershell
Copy-Item docker/.env.production.example docker/.env.production
```

### 7.2 最少要改的配置

部署前至少确认这些值：
- `POSTGRES_PASSWORD`
- `APP_CORS_ORIGINS`
- `APP_PUBLIC_BASE_URL`
- `WEB_PORT`
- `AI_PROVIDER`
- `AI_API_KEY` 或 `DEEPSEEK_API_KEY`
- `GRAFANA_ADMIN_PASSWORD`

如果要通过域名访问，还建议确认：
- `APP_PUBLIC_BASE_URL`
- `GRAFANA_ROOT_URL`
- 反向代理或公网域名配置是否一致

## 8. 启动完整 Docker 部署

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml up -d --build
```

说明：
- `backend` 启动前会自动执行 `alembic upgrade head`
- `frontend` 会在构建阶段编译静态资源，并由 `nginx` 对外提供

## 9. 查看部署状态

### 轻量运行

```powershell
docker compose --env-file docker/.env.app.local -f docker-compose.app.yml ps
docker compose --env-file docker/.env.app.local -f docker-compose.app.yml logs -f
```

### 完整 Docker 开发

```powershell
docker compose --env-file docker/.env.dev-full -f docker-compose.dev-full.yml ps
docker compose --env-file docker/.env.dev-full -f docker-compose.dev-full.yml logs -f
```

### 完整 Docker 部署

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml ps
docker compose --env-file docker/.env.production -f docker-compose.prod.yml logs -f
```

只看后端：

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml logs -f backend
```

只看 Worker：

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml logs -f worker
```

## 10. 默认访问入口

### 轻量整套 Docker 运行

- Web：`http://127.0.0.1:8080`

### 完整 Docker 开发

- 前端：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8014/api`

### 完整 Docker 部署

- Web：`http://<your-host>:<WEB_PORT>`
- Grafana：`http://<your-host>:<GRAFANA_PORT>`
- Prometheus：`http://<your-host>:<PROMETHEUS_PORT>`
- Alertmanager：`http://<your-host>:<ALERTMANAGER_PORT>`

如果 `WEB_PORT=80`，则 Web 默认入口通常是：
- `http://<your-host>`

## 11. 数据持久化

### 轻量整套 Docker 运行

`docker-compose.app.yml` 使用：
- `app_postgres_data`
- `app_redis_data`
- `app_backend_logs`
- `app_backend_raw_data`

### 完整 Docker 开发

`docker-compose.dev-full.yml` 使用：
- `dev_postgres_data`
- `dev_redis_data`
- `dev_frontend_node_modules`

### 完整 Docker 部署

`docker-compose.prod.yml` 使用：
- `postgres_data`
- `redis_data`
- `backend_logs`
- `backend_raw_data`
- `prometheus_data`
- `alertmanager_data`
- `grafana_data`

说明：
- 删除容器不会自动删除这些卷
- 如果要连卷一起删，请显式使用 `down -v`

## 12. 配置校验建议

正式启动前建议先检查 Compose 是否能正确展开。

轻量整套 Docker 运行：

```powershell
docker compose --env-file docker/.env.app.local -f docker-compose.app.yml config
```

完整 Docker 开发：

```powershell
docker compose --env-file docker/.env.dev-full -f docker-compose.dev-full.yml config
```

完整 Docker 部署：

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml config
```

## 13. 最小验收清单

### 轻量整套 Docker 运行

1. Web 页面可访问
2. `backend` 健康检查通过
3. Worker 正常启动
4. 可以创建任务

### 完整 Docker 开发

1. `http://127.0.0.1:5174` 可访问
2. `http://127.0.0.1:8014/api/health` 返回 `200`
3. Worker 正常启动
4. 可以进入任务创建页

### 完整 Docker 部署

1. `docker compose ... ps` 中核心服务都在运行
2. Web 页面可访问
3. `backend` 健康检查通过
4. Worker 正常启动
5. 可以创建任务
6. 至少完成一次任务主链路验证

## 14. 常见问题

### 启动失败，提示端口占用

优先检查这些端口是否已被宿主机占用：
- `80` 或 `8080`
- `5174`
- `8014`
- `5434`
- `6381`
- `3000`
- `9090`
- `9093`

如果冲突，修改对应 `docker/.env.*` 文件中的端口。

### 前端能打开，但接口失败

优先检查：
- `backend` 容器是否健康
- `worker` 是否已启动
- `APP_PUBLIC_BASE_URL` 与前端访问入口是否一致
- `APP_CORS_ORIGINS` 是否覆盖当前访问域名

### AI 功能不可用

优先检查：
- 是否配置了 `AI_PROVIDER`
- 是否配置了对应的 `AI_API_KEY` / `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`
- 容器网络是否能访问外部 AI 服务地址

### 监控页打不开

优先检查：
- `PROMETHEUS_PORT`
- `ALERTMANAGER_PORT`
- `GRAFANA_PORT`
- Grafana 管理员密码是否已设置

## 15. 建议

- 只想运行，优先使用 `docker-compose.app.yml` 或 `launch-docker.bat`
- 需要在容器里开发，优先使用 `docker-compose.dev-full.yml` 或 `launch-docker-dev.bat`
- 只想给本地开发提供数据库和 Redis，就继续使用 `docker-compose.yml`
- 生产部署使用 `docker-compose.prod.yml`
- 不要把真实 `docker/.env.*` 提交到公开仓库
