# SpiderBilibili

一个面向中文内容研究场景的 Bilibili 关键词采集与分析平台，提供任务创建、视频结果分析、主题分析、UP 主分析、任务报告、上线验收和本地一键启动能力。

项目已经整理为适合公开使用的仓库形态，默认不包含任何私密配置。你可以直接克隆后按本文档完成本地开发或 Docker 部署。

## 功能概览

- 关键词任务创建与抓取范围配置
- Bilibili 搜索结果采集与原始数据落库
- AI 摘要、主题聚类、热度分析和任务报告生成
- 热门 UP 主工作台与内容分析
- 运行时配置 DeepSeek API Key 和 Bilibili 登录态
- Windows 一键启动器与后台监控面板
- Docker 化基础设施和整套容器部署

## 技术栈

- 前端：Vue 3、TypeScript、Vite、Pinia、Element Plus、ECharts
- 后端：FastAPI、SQLAlchemy、Alembic、Celery、Redis、PostgreSQL
- 采集：httpx、Playwright、selectolax
- AI 与分析：OpenAI 兼容 SDK、jieba、pandas、scikit-learn

## 仓库结构

```text
spiderbilibili/
├─ backend/                 后端服务、数据库迁移、业务逻辑
├─ frontend/                前端界面
├─ scripts/                 启动器、关闭器和开发脚本
├─ docker/                  Nginx、Prometheus、Grafana 等容器配置
├─ docs/                    面向使用者的补充文档
├─ docker-compose.yml       本地开发基础设施
├─ docker-compose.prod.yml  整套 Docker 部署
├─ launch-dev.bat           Windows 一键启动
└─ close-dev.bat            Windows 一键关闭
```

## 推荐使用方式

### 方式一：Windows 一键启动

适合第一次使用本项目，也是当前最省心的方式。启动器会自动完成下面这些事情：

- 检查并创建 `backend/.env`
- 自动创建 `.venv`
- 自动安装后端依赖
- 自动安装 Playwright Chromium 运行时
- 自动安装前端依赖
- 启动 PostgreSQL 和 Redis 容器
- 启动后端、Celery Worker、前端
- 打开浏览器并显示后台监控面板

使用前请先安装：

- Python 3.11
- Node.js 20 LTS 或更高版本
- Docker Desktop

启动步骤：

```powershell
git clone <your-repo-url>
cd spiderbilibili
.\launch-dev.bat
```

关闭开发环境：

```powershell
.\close-dev.bat
```

启动成功后默认地址：

- 前端：`http://127.0.0.1:5174`
- 后端：`http://127.0.0.1:8014/api`

首次启动可能会比后续启动更慢一些，因为启动器会自动准备 Python 依赖、前端依赖和 Playwright 浏览器运行时。

### 方式二：手动本地开发

适合需要单独调试前后端或自定义环境的用户。完整步骤见：

- [本地开发与环境配置](./docs/LOCAL_SETUP.md)

### 方式三：Docker 整套部署

适合想直接使用整套容器运行前端、后端、Worker、数据库和监控组件的用户。完整步骤见：

- [Docker 部署指南](./docs/DOCKER_SETUP.md)

## 快速配置

### 1. 配置 DeepSeek API Key

项目支持两种方式：

- 推荐：启动前端后，进入左侧 `系统设置`
- 可选：直接在 `backend/.env` 中配置

前端页面支持查看、保存、修改和清空运行时 API Key，适合开箱即用。

### 2. 配置 Bilibili 登录态

项目同样支持两种方式：

- 推荐：在 `系统设置` 页面使用“一键读取”导入本机浏览器中的 Bilibili 登录态
- 可选：手动粘贴完整 Cookie

如果你需要更稳定的采集结果，建议使用登录态运行任务。

### 3. 浏览器与账号倾向问题

项目已经提供独立的 Bilibili 登录配置入口，但搜索结果仍可能受到平台侧内容分发策略影响。为了尽量减小干扰，建议：

- 使用专门的 Bilibili 账号执行采集
- 避免在该账号下进行大量个性化观看操作
- 定期更新登录态

## 环境要求

### 本地开发

- Git
- Python 3.11
- Node.js 20 LTS 或更高
- npm 10+
- Docker Desktop

### Docker 部署

- Docker Engine 24+
- Docker Compose v2

## 本地开发默认端口

- `5174`：前端开发服务器
- `8014`：后端 API
- `5434`：PostgreSQL
- `6381`：Redis
- `4174`：前端预览端口

## 配置文件说明

### 后端

首次使用时，启动器会自动从 `backend/.env.example` 复制出 `backend/.env`。

常用项：

- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `AI_PROVIDER`
- `DEEPSEEK_API_KEY`
- `BILIBILI_COOKIE`

### 前端

前端开发环境默认通过 `/api` 访问后端，并在本地开发时自动代理到 `http://127.0.0.1:8014`。通常不需要额外配置。

如果你要连接远程后端，可新建 `frontend/.env`：

```env
VITE_API_BASE_URL=http://127.0.0.1:8014
```

### Docker 部署

整套 Docker 部署建议复制：

```powershell
Copy-Item docker/.env.production.example docker/.env.production
```

然后按实际情况修改域名、端口、数据库密码和 AI Key。

## 常用命令

### 基础设施

```powershell
docker compose up -d
docker compose down
```

### 后端

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m playwright install
.\.venv\Scripts\python.exe -m alembic upgrade head
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

## Docker 快速开始

### 仅启动数据库和 Redis

```powershell
docker compose up -d
```

### 启动整套服务

```powershell
Copy-Item docker/.env.production.example docker/.env.production
docker compose --env-file docker/.env.production -f docker-compose.prod.yml up -d --build
```

默认会启动：

- PostgreSQL
- Redis
- Backend
- Celery Worker
- Nginx
- Prometheus
- Alertmanager
- Grafana

## 常见问题

### 1. 启动器提示缺少 Python、npm 或 Docker

请先安装对应软件，并确认命令可在 PowerShell 中直接执行：

```powershell
python --version
npm --version
docker --version
docker compose version
```

### 2. 前端打开了但无法访问接口

优先检查：

- 后端是否已经启动
- `http://127.0.0.1:8014/api/health` 是否可访问
- 端口 `8014` 是否被占用

### 3. 任务一直排队或提示没有 Worker 处理

优先检查：

- Redis 容器是否正常
- Worker 进程是否在运行
- 后端健康检查中的 `worker` 状态是否为 `ok`

### 4. 一键读取 Bilibili 登录态失败

优先检查：

- 当前 Windows 账号是否能访问浏览器用户目录
- Edge 或 Chrome 中是否已经登录 Bilibili
- 是否被安全软件拦截

必要时可以退回到手动粘贴 Cookie。

## 面向开源使用的说明

- 仓库中不包含任何真实 API Key、Cookie、数据库密码或个人数据
- `backend/.env`、`frontend/.env`、`docker/.env.production`、`.runtime/`、`backend/data/`、`backend/logs/` 均已加入忽略规则
- Windows 启动器保留可用，适合作为默认体验入口
- 如果你准备公开发布到 GitHub，建议在发布前补充你自己的 `LICENSE`

## 补充文档

- [本地开发与环境配置](./docs/LOCAL_SETUP.md)
- [Docker 部署指南](./docs/DOCKER_SETUP.md)
