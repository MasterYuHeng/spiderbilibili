# SpiderBilibili

SpiderBilibili 是一个面向中文内容研究场景的 Bilibili 采集与分析平台，提供任务创建、视频结果分析、主题分析、热门创作者分析、任务报告、运行监控，以及本地一键启动和 Docker 部署方案。

当前仓库已经整理为适合开源发布的结构：
- 不包含真实 API Key、Cookie、数据库密码或个人数据
- 默认提供本地开发、Windows 一键启动、Docker 基础设施、整套 Docker 部署四种使用路径
- 环境变量模板、部署文档和启动入口已经补齐

## 功能概览

- 关键词任务创建，支持发布时间限制、采集数量、搜索范围等参数
- Bilibili 搜索结果采集与原始数据落盘
- AI 摘要、主题聚类、热点分析、任务报告生成
- 主题分析权重自定义，并可确认后重新分析
- 热门 UP 主画像与热门主题关联分析
- 系统设置页内配置 AI Key 和 Bilibili 登录态
- Windows 一键启动器与开发监控面板
- Docker 化基础设施与整套容器部署

## 技术栈

- 前端：Vue 3、TypeScript、Vite、Pinia、Element Plus、ECharts
- 后端：FastAPI、SQLAlchemy、Alembic、Celery、PostgreSQL、Redis
- 采集：httpx、Playwright、selectolax
- 分析：OpenAI Compatible SDK、jieba、pandas、scikit-learn
- 运维：Docker、Nginx、Prometheus、Alertmanager、Grafana

## 仓库结构

```text
spiderbilibili/
├─ backend/                  后端服务、数据库迁移、业务逻辑、测试
├─ frontend/                 前端界面
├─ scripts/                  本地启动、关闭和开发辅助脚本
├─ docker/                   Nginx、Prometheus、Grafana 等部署配置
├─ docs/                     项目文档、环境教程、运行期文档
├─ docker-compose.yml        本地开发基础设施
├─ docker-compose.prod.yml   整套 Docker 部署
├─ launch-dev.bat            Windows 一键启动
├─ close-dev.bat             Windows 一键关闭
└─ LICENSE                   开源许可证
```

## 快速开始

### 方案 A：Windows 一键启动

适合第一次体验项目，也是当前最省心的启动方式。

前置要求：
- Git
- Python 3.11
- Node.js 20 LTS 或更高版本
- npm 10+
- Docker Desktop

启动：

```powershell
git clone <your-repo-url>
cd spiderbilibili
.\launch-dev.bat
```

关闭：

```powershell
.\close-dev.bat
```

默认地址：
- 前端：`http://127.0.0.1:5174`
- 后端 API：`http://127.0.0.1:8014/api`
- 健康检查：`http://127.0.0.1:8014/api/health`

说明：
- 启动器会自动创建 `backend/.env`
- 会自动准备 `.venv`、后端依赖、Playwright Chromium 和前端依赖
- 会自动拉起 PostgreSQL、Redis、后端、Worker、前端

### 方案 B：手动本地开发

适合调试前后端、修改环境变量或在 macOS / Linux 上运行。

完整教程见：
- [本地开发与环境配置](./docs/LOCAL_SETUP.md)

### 方案 C：只用 Docker 启动基础设施

适合本地开发时只把数据库和 Redis 放进容器。

```powershell
docker compose up -d
```

默认端口：
- PostgreSQL：`5434`
- Redis：`6381`

### 方案 D：整套 Docker 部署

适合服务器部署或完整容器化运行。

完整教程见：
- [Docker 部署指南](./docs/DOCKER_SETUP.md)

最短命令：

```powershell
Copy-Item docker/.env.production.example docker/.env.production
docker compose --env-file docker/.env.production -f docker-compose.prod.yml up -d --build
```

## 环境配置

### 后端环境变量

模板文件：
- `backend/.env.example`

实际文件：
- `backend/.env`

常见关键项：
- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `AI_PROVIDER`
- `AI_API_KEY`
- `DEEPSEEK_API_KEY`
- `OPENAI_API_KEY`
- `BILIBILI_COOKIE`

说明：
- 本地开发默认可直接使用 `backend/.env.example` 中的数据库和 Redis 地址
- AI Key 不提交到仓库
- Bilibili Cookie 不提交到仓库

### 前端环境变量

模板文件：
- `frontend/.env.example`

默认情况下，Vite 会把 `/api` 自动代理到 `http://127.0.0.1:8014`，所以本地开发通常不需要额外创建 `frontend/.env`。

只有在前端要连接远程后端时，才需要创建：

```env
VITE_API_BASE_URL=https://your-api-domain.com
```

### Docker 部署环境变量

模板文件：
- `docker/.env.production.example`

实际文件：
- `docker/.env.production`

最少需要确认：
- `POSTGRES_PASSWORD`
- `APP_CORS_ORIGINS`
- `APP_PUBLIC_BASE_URL`
- `WEB_PORT`
- `AI_PROVIDER`
- `AI_API_KEY` 或 `DEEPSEEK_API_KEY`

## 首次配置建议

启动系统后，建议优先完成两项配置：

### 1. AI Key

可通过两种方式配置：
- 在前端“系统设置”页面填写并保存
- 或直接写入 `backend/.env` / `docker/.env.production`

说明：
- 没有配置 AI Key 时，系统仍可启动
- 但依赖 AI 的摘要、分析和报告能力会受限

### 2. Bilibili 登录态

可通过两种方式配置：
- 在“系统设置”页面一键读取本机浏览器登录态
- 或手动粘贴完整 Cookie

说明：
- 不带登录态也可以运行
- 但采集稳定性和可见结果可能受平台分发策略影响

## 常用命令

### 本地基础设施

```powershell
docker compose up -d
docker compose down
```

### 后端

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
.\scripts\start-backend.ps1
```

### Worker

```powershell
.\scripts\start-worker.ps1
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

## 文档入口

- [本地开发与环境配置](./docs/LOCAL_SETUP.md)
- [Docker 部署指南](./docs/DOCKER_SETUP.md)
- [技术栈与环境基线](./docs/02-tech-stack-and-env.md)
- [当前项目状态](./docs/04-current-state.md)

## 常见问题

### 前端打开了，但接口报错

优先检查：
- 后端是否已启动
- `http://127.0.0.1:8014/api/health` 是否返回 `200`
- Worker 是否已启动
- 端口 `8014` 是否被其它进程占用

### 任务一直排队

优先检查：
- Redis 是否正常
- Worker 是否正常运行
- 健康检查中 `worker` 是否为 `ok`

### Windows 启动器无法运行脚本

可以在当前用户范围执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### Docker 整套部署启动失败

优先检查：
- `docker/.env.production` 是否已创建
- `POSTGRES_PASSWORD`、`APP_PUBLIC_BASE_URL`、AI Key 是否已填写
- `docker compose --env-file docker/.env.production -f docker-compose.prod.yml config` 是否能成功展开配置

## 开源发布说明

- 仓库默认不提交 `backend/.env`、`frontend/.env`、`docker/.env.production`
- 仓库默认不提交 `.runtime/`、`backend/data/`、`backend/logs/`
- 当前许可证为 MIT，见 [LICENSE](./LICENSE)
- 若你二次发布到自己的代码托管平台，建议保留环境变量模板和部署文档，不要提交真实密钥或 Cookie

## License

本项目使用 MIT License。
