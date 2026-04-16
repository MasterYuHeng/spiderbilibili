# SpiderBilibili

SpiderBilibili 是一个面向中文内容研究场景的 Bilibili 采集与分析平台，提供任务创建、视频结果分析、主题分析、热门创作者分析、任务报告、运行监控，以及本地和 Docker 两类部署方案。

当前仓库已经整理为适合开源发布的结构：
- 不包含真实 API Key、Cookie、数据库密码或个人数据
- 同时提供轻量运行链路和完整开发链路
- 支持本地部署与 Docker 部署两种形态
- 环境变量模板、启动脚本和部署文档已经补齐

## 开源协作

- 贡献说明见 [CONTRIBUTING.md](CONTRIBUTING.md)
- 安全披露流程见 [SECURITY.md](SECURITY.md)
- 社区协作约定见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- 本地配置请始终从 `*.example` 模板复制生成，不要提交 `.env`、`.venv`、`.venv-app`、`.runtime`、日志和抓取数据目录

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
- 采集：httpx、Playwright
- 分析：OpenAI Compatible SDK、jieba
- 运维：Docker、Nginx、Prometheus、Alertmanager、Grafana

## 仓库结构

```text
spiderbilibili/
├─ backend/                      后端服务、数据库迁移、业务逻辑、测试
├─ frontend/                     前端界面
├─ scripts/                      本地启动、关闭和开发辅助脚本
├─ docker/                       Nginx、Prometheus、Grafana 等部署配置
├─ docs/                         项目文档、环境教程、运行期文档
├─ docker-compose.yml            本地开发基础设施
├─ docker-compose.local-app.yml  轻量本地运行前端容器
├─ docker-compose.app.yml        轻量整套 Docker 运行
├─ docker-compose.dev-full.yml   完整 Docker 开发
├─ docker-compose.prod.yml       完整 Docker 部署
├─ launch-app.bat                轻量本地运行
├─ launch-dev.bat                完整本地开发
├─ launch-docker.bat             轻量 Docker 运行
├─ launch-docker-dev.bat         完整 Docker 开发
└─ LICENSE                       开源许可证
```

## 四种使用模式

### 1. 轻量本地运行

适合：
- 只想开箱即用运行项目
- 宿主机尽量少装依赖
- 需要保留本地 API、Worker 调试能力，但不想本机装 Node

特点：
- 宿主机只安装轻量 Python 运行依赖，见 `backend/requirements.runtime.txt`
- 前端静态页面走 Docker 容器，不需要本机 `npm install`
- AI、Excel 导出、浏览器登录导入、监控等重依赖首次真正用到时才按需安装

启动：

```powershell
.\launch-app.bat
```

关闭：

```powershell
.\close-app.bat
```

默认入口：
- Web：`http://127.0.0.1:8080`
- 如果 `8080` 已被占用，启动器会自动切到下一个可用端口，例如 `8081`
- API：`http://127.0.0.1:8014/api`

前置要求：
- Git
- Python 3.11 或 3.12
- Docker Desktop

### 2. 完整本地开发

适合：
- 需要修改源码
- 需要完整前后端开发体验
- 需要一次性装齐 Playwright、OpenAI SDK、jieba、导出等重依赖

特点：
- 宿主机会安装完整 Python 依赖，见 `backend/requirements.full.txt`
- 宿主机会安装前端 `node_modules`
- 前端、后端、Worker 都在本机直接运行

启动：

```powershell
.\launch-dev.bat
```

关闭：

```powershell
.\close-dev.bat
```

默认入口：
- 前端：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8014/api`
- 健康检查：`http://127.0.0.1:8014/api/health`

前置要求：
- Git
- Python 3.11 或 3.12
- Node.js 20 LTS 或更高版本
- npm 10+
- Docker Desktop

### 3. 轻量 Docker 运行

适合：
- 用户不想在宿主机安装 Python / Node / Playwright
- 只想把完整应用跑起来

启动：

```powershell
.\launch-docker.bat
```

关闭：

```powershell
.\close-docker.bat
```

默认入口：
- Web：`http://127.0.0.1:8080`

前置要求：
- Docker Desktop

### 4. 完整 Docker 开发

适合：
- 需要完整重依赖
- 需要在容器里做源码开发
- 不希望宿主机安装本地 Python / Node 重依赖

启动：

```powershell
.\launch-docker-dev.bat
```

关闭：

```powershell
.\close-docker-dev.bat
```

默认入口：
- 前端：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8014/api`

前置要求：
- Docker Desktop

## 快速开始建议

如果你只想体验项目：
- 优先用 `launch-docker.bat`
- 或者用 `launch-app.bat`

如果你要改代码：
- 本机开发优先用 `launch-dev.bat`
- 想把完整开发环境放进容器，就用 `launch-docker-dev.bat`

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
- 本地链路默认可直接使用 `backend/.env.example` 中的数据库和 Redis 地址
- AI Key 不提交到仓库
- Bilibili Cookie 不提交到仓库

### 前端环境变量

模板文件：
- `frontend/.env.example`

说明：
- 完整本地开发模式下，Vite 默认把 `/api` 代理到 `http://127.0.0.1:8014`
- 轻量本地运行和轻量 Docker 运行使用构建后的静态前端，不需要本机创建 `frontend/.env`
- 只有前端要连接远程后端时，才需要显式设置 `VITE_API_BASE_URL`

### Docker 环境变量

模板文件：
- `docker/.env.local-app.example`
- `docker/.env.app.local.example`
- `docker/.env.dev-full.example`
- `docker/.env.production.example`

分别对应：
- 轻量本地运行的前端容器
- 轻量整套 Docker 运行
- 完整 Docker 开发
- 完整 Docker 部署

## 首次配置建议

启动系统后，建议优先完成两项配置：

### 1. AI Key

可通过两种方式配置：
- 在前端“系统设置”页面填写并保存
- 或直接写入 `backend/.env` / `docker/.env.*`

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

### 轻量本地运行

```powershell
.\launch-app.bat
.\close-app.bat
```

### 完整本地开发

```powershell
.\launch-dev.bat
.\close-dev.bat
```

### 轻量 Docker 运行

```powershell
.\launch-docker.bat
.\close-docker.bat
```

### 完整 Docker 开发

```powershell
.\launch-docker-dev.bat
.\close-docker-dev.bat
```

### 只启动本地开发基础设施

```powershell
docker compose up -d
docker compose down
```

## 文档入口

- [本地开发与环境配置](./docs/LOCAL_SETUP.md)
- [Docker 部署指南](./docs/DOCKER_SETUP.md)
- [技术栈与环境基线](./docs/02-tech-stack-and-env.md)
- [当前项目状态](./docs/04-current-state.md)

## 常见问题

### 我只想运行，不想装重依赖

用：
- `launch-app.bat`
- 或 `launch-docker.bat`

### 我需要看源码和完整能力

用：
- `launch-dev.bat`
- 或 `launch-docker-dev.bat`

### 页面能打开，但接口报错

优先检查：
- `http://127.0.0.1:8014/api/health` 是否返回 `200`
- Worker 是否已启动
- `8014` 端口是否被其它进程占用

### Docker 启动失败

优先检查：
- 对应的 `docker/.env.*` 是否已创建
- 目标端口是否已被占用
- `docker compose ... config` 是否能成功展开配置

## 开源发布说明

- 仓库默认不提交 `backend/.env`、`frontend/.env`、`docker/.env.*`
- 仓库默认不提交 `.runtime/`、`backend/data/`、`backend/logs/`
- 当前许可证为 MIT，见 [LICENSE](./LICENSE)
- 二次发布时建议保留环境变量模板和部署文档，不要提交真实密钥或 Cookie

## License

本项目使用 MIT License。
