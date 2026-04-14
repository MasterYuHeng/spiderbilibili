# Docker 部署指南

> 文档角色：本文件只负责 Docker 使用与部署步骤。项目级技术栈、环境基线和文档治理口径以 `docs/02-tech-stack-and-env.md` 为准。

SpiderBilibili 提供两种 Docker 使用方式：
- 方式 A：只用 Docker 启动 PostgreSQL 和 Redis，前后端继续本地开发
- 方式 B：使用 Docker 启动整套服务，适合服务器部署或完整容器化运行

## 1. 前置要求

- Docker Engine 24+ 或 Docker Desktop
- Docker Compose v2

确认命令可用：

```powershell
docker --version
docker compose version
```

## 2. 方式 A：只启动基础设施

适合本地开发时只把数据库和 Redis 放进容器。

启动：

```powershell
docker compose up -d
```

配置文件：
- `docker-compose.yml`

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

## 3. 方式 B：整套 Docker 部署

适合以下场景：
- 服务器部署
- 完整容器化验收
- 不希望宿主机直接安装 Python / Node 运行时

配置文件：
- `docker-compose.prod.yml`

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

## 4. 部署前准备

### 4.1 复制生产环境模板

```powershell
Copy-Item docker/.env.production.example docker/.env.production
```

### 4.2 最少要改的配置

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

## 5. 启动整套服务

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml up -d --build
```

说明：
- `backend` 启动前会自动执行 `alembic upgrade head`
- `frontend` 会在构建阶段编译静态资源，并由 `nginx` 对外提供

## 6. 查看部署状态

查看容器：

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml ps
```

查看日志：

```powershell
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

## 7. 默认访问入口

整套部署成功后，通常可访问：
- Web：`http://<your-host>:<WEB_PORT>`
- Grafana：`http://<your-host>:<GRAFANA_PORT>`
- Prometheus：`http://<your-host>:<PROMETHEUS_PORT>`
- Alertmanager：`http://<your-host>:<ALERTMANAGER_PORT>`

如果 `WEB_PORT=80`，则 Web 默认入口通常是：
- `http://<your-host>`

## 8. 数据持久化

`docker-compose.prod.yml` 已声明以下卷：
- `postgres_data`
- `redis_data`
- `backend_logs`
- `backend_raw_data`
- `prometheus_data`
- `alertmanager_data`
- `grafana_data`

说明：
- 这些卷用于保存数据库、Redis、日志、原始抓取数据和监控数据
- 删除容器不会自动删除这些卷

如需连同卷一起清理：

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml down -v
```

请谨慎执行，这会删除持久化数据。

## 9. 配置校验建议

在正式启动前，建议先检查 Compose 是否能正确展开：

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml config
```

如果这一步失败，优先检查：
- `.env.production` 是否存在
- 环境变量格式是否正确
- 端口是否写成了非法值

## 10. 发布前最小验收清单

整套 Docker 部署后，建议至少确认：

1. `docker compose ... ps` 中核心服务都在运行
2. Web 页面可访问
3. `backend` 健康检查通过
4. Worker 正常启动
5. 可以创建任务
6. 至少完成一次任务主链路验证

## 11. 常见问题

### 启动失败，提示端口占用

优先检查这些端口是否已被宿主机占用：
- `80`
- `3000`
- `5434` 或数据库相关端口
- `6381` 或 Redis 相关端口
- `9090`
- `9093`

如果冲突，修改 `docker/.env.production` 中对应端口。

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

## 12. 建议

- 本地开发优先使用 `docker-compose.yml`
- 完整部署优先使用 `docker-compose.prod.yml`
- 不要把真实 `docker/.env.production` 提交到公开仓库
- 首次对外发布前，至少做一次真实环境启动验收
