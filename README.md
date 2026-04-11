# spiderbilibili

B站关键词视频采集与分析平台。

## 项目概览

项目围绕“按关键词采集 B 站视频并进行后续分析”展开，核心能力包括：

- 搜索并采集视频基础信息、详情、字幕和文本内容
- 基于相关性与热度对候选视频进行综合评分
- 使用 AI 生成摘要、提取主题并做聚类分析
- 通过前后端页面查看任务、视频结果、主题分析和上线前验收报告

## 技术栈

- 前端：Vue 3、TypeScript、Vite、Pinia、Vue Router、Element Plus、ECharts
- 后端：Python 3.11、FastAPI、SQLAlchemy 2.x、Pydantic、Alembic
- 采集链路：httpx、Playwright、selectolax、tenacity
- 任务系统：Celery、Redis
- 数据存储：PostgreSQL

## 目录结构

```text
spiderbilibili/
├─ backend/               # FastAPI、Celery、采集与分析逻辑
├─ docker/                # 生产部署相关配置
├─ docs/                  # 方案、阶段说明与验收文档
├─ frontend/              # Vue 3 前端
├─ scripts/               # 本地开发与运维脚本
├─ docker-compose.yml     # 本地开发基础设施
└─ docker-compose.prod.yml
```

## 快速开始

### 1. 启动基础设施

```powershell
.\scripts\start-infra.ps1
```

### 2. 启动后端 API

```powershell
.\scripts\start-backend.ps1
```

### 3. 启动 Worker

```powershell
.\scripts\start-worker.ps1
```

### 4. 启动前端

```powershell
.\scripts\start-frontend.ps1
```

### 5. 一键启动本地开发环境

```powershell
.\scripts\start-dev.ps1
```

默认端口：

- PostgreSQL：`5434`
- Redis：`6381`
- FastAPI：`8014`
- Vite：`5174`

## 常用命令

### 后端依赖与测试

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest backend\tests -q
.\.venv\Scripts\python.exe -m ruff check backend\app backend\tests
```

### 前端依赖与构建

```powershell
cd frontend
npm install
npm run lint
npm run test
npm run build
```

## B站登录态

如果需要抓取 `need_login_subtitle: true` 的字幕，请为后端和 Worker 配置 B 站登录态后再重启服务。

推荐直接配置完整 Cookie：

```powershell
$env:BILIBILI_COOKIE="SESSDATA=你的SESSDATA; bili_jct=你的bili_jct; DedeUserID=你的DedeUserID; buvid3=你的buvid3"
```

也可以拆分配置：

```powershell
$env:BILIBILI_SESSDATA="你的SESSDATA"
$env:BILIBILI_BILI_JCT="你的bili_jct"
$env:BILIBILI_DEDEUSERID="你的DedeUserID"
$env:BILIBILI_BUVID3="你的buvid3"
$env:BILIBILI_BUVID4="你的buvid4"
```

配置完成后重启：

```powershell
.\scripts\start-backend.ps1
.\scripts\start-worker.ps1
```

## 生产部署

```bash
cp docker/.env.production.example docker/.env.production
docker compose --env-file docker/.env.production -f docker-compose.prod.yml build
docker compose --env-file docker/.env.production -f docker-compose.prod.yml up -d
```

## 运维脚本

- 健康检查：`.\.venv\Scripts\python.exe .\scripts\check-health.py --include-metrics`
- 重试任务：`.\.venv\Scripts\python.exe .\scripts\retry-task.py --task-id <task-id>`
- 导出任务数据：`.\.venv\Scripts\python.exe .\scripts\export-task-data.py --task-id <task-id> --dataset videos --format csv --output .\exports\task.csv`
- 清理日志：`.\.venv\Scripts\python.exe .\scripts\cleanup-logs.py --dry-run`
- Stage 15 验收：`.\.venv\Scripts\python.exe .\scripts\run-stage15-acceptance.py`

## 文档入口

- `docs/项目PRD与技术方案.md`
- `docs/环境搭建与配置说明.md`
- `docs/从零到一完整开发实施计划.md`
- `docs/阶段13-部署与发布说明.md`
- `docs/阶段14-运维与可观测性说明.md`
- `docs/阶段15-上线前验收说明.md`
