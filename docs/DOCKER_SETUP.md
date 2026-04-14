# Docker 部署指南

> 文档角色：本文件只负责 Docker 使用与部署步骤。项目级技术栈、环境基线和文档治理口径以 `docs/02-tech-stack-and-env.md` 为准。

SpiderBilibili 提供两种 Docker 使用方式：

- 仅使用 Docker 启动 PostgreSQL 和 Redis，前后端继续本地开发
- 使用 Docker 启动整套服务

## 1. 前置要求

- Docker Engine 24+
- Docker Compose v2

确认命令可用：

```powershell
docker --version
docker compose version
```

## 2. 方式一：只启动基础设施

适合本地开发。

```powershell
docker compose up -d
```

当前文件：

- [docker-compose.yml](../docker-compose.yml)

会启动：

- PostgreSQL
- Redis

端口映射：

- PostgreSQL：`5434 -> 5432`
- Redis：`6381 -> 6379`

关闭：

```powershell
docker compose down
```

## 3. 方式二：整套服务 Docker 化部署

当前文件：

- [docker-compose.prod.yml](../docker-compose.prod.yml)

### 3.1 准备配置

复制模板：

```powershell
Copy-Item docker/.env.production.example docker/.env.production
```

至少需要修改这些配置：

- `POSTGRES_PASSWORD`
- `APP_CORS_ORIGINS`
- `APP_PUBLIC_BASE_URL`
- `WEB_PORT`
- `AI_PROVIDER`
- `AI_API_KEY` 或 `DEEPSEEK_API_KEY`

如果你要用域名部署，还应同步调整：

- `GRAFANA_ROOT_URL`
- 反向代理或公网域名配置

### 3.2 构建并启动

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml up -d --build
```

### 3.3 查看状态

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml ps
```

### 3.4 停止服务

```powershell
docker compose --env-file docker/.env.production -f docker-compose.prod.yml down
```

## 4. 整套部署包含的组件

- `postgres`
- `redis`
- `backend`
- `worker`
- `nginx`
- `prometheus`
- `alertmanager`
- `grafana`

## 5. 默认访问入口

整套部署完成后，默认入口通常是：

- Web：`http://<your-host>:<WEB_PORT>`
- Grafana：`http://<your-host>:<GRAFANA_PORT>`
- Prometheus：`http://<your-host>:<PROMETHEUS_PORT>`

## 6. 数据持久化

`docker-compose.prod.yml` 已声明以下卷：

- `postgres_data`
- `redis_data`
- `backend_logs`
- `backend_raw_data`
- `prometheus_data`
- `alertmanager_data`
- `grafana_data`

## 7. 建议

- 本地开发优先使用 `docker-compose.yml`
- 发布环境再使用 `docker-compose.prod.yml`
- 不要把真实的 `docker/.env.production` 提交到公共仓库
