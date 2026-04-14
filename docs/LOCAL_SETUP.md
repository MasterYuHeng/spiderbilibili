# 本地开发与环境配置

> 文档角色：本文件只负责“如何在本地把项目跑起来”。项目级技术栈、环境基线和文档分层口径以 `docs/02-tech-stack-and-env.md` 为准。

## 1. 适用场景

适合以下场景：
- 在 Windows / macOS / Linux 上手动启动项目
- 单独调试前端、后端或 Worker
- 需要自行修改环境变量
- 不想使用 Windows 一键启动器

如果你是 Windows 用户，且只是想先体验项目，优先使用根目录的：
- `launch-dev.bat`
- `close-dev.bat`

## 2. 前置要求

推荐版本：
- Git
- Python 3.11
- Node.js 20 LTS 或更高版本
- npm 10+
- Docker Desktop 或 Docker Engine + Docker Compose v2

建议先确认以下命令都能正常执行：

```powershell
git --version
python --version
npm --version
docker --version
docker compose version
```

## 3. 获取项目

```powershell
git clone <your-repo-url>
cd spiderbilibili
```

## 4. 启动基础设施

本项目本地开发默认依赖容器里的 PostgreSQL 和 Redis。

启动：

```powershell
docker compose up -d
```

默认端口：
- PostgreSQL：`5434`
- Redis：`6381`

查看状态：

```powershell
docker compose ps
```

关闭：

```powershell
docker compose down
```

## 5. 配置后端环境变量

先复制模板：

```powershell
Copy-Item backend/.env.example backend/.env
```

本地开发默认通常不需要改这些地址：
- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

需要你按实际情况填写的主要是：
- `AI_PROVIDER`
- `AI_API_KEY` 或 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`
- `BILIBILI_COOKIE`

说明：
- 不配置 AI Key，系统通常仍可启动，但 AI 相关功能会受限
- 不配置 Bilibili 登录态，也能运行，但采集稳定性和结果可见性可能下降

## 6. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 7. 初始化数据库

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
```

说明：
- `scripts/start-backend.ps1` 启动前也会自动执行迁移
- 但第一次本地初始化时，手动跑一遍更容易定位问题

## 8. 启动后端

```powershell
.\scripts\start-backend.ps1
```

默认地址：
- API：`http://127.0.0.1:8014/api`
- 健康检查：`http://127.0.0.1:8014/api/health`

## 9. 启动 Worker

```powershell
.\scripts\start-worker.ps1
```

说明：
- 只启动后端不启动 Worker 时，项目页面可能能打开
- 但任务执行、异步分析和部分运行健康状态会不完整

## 10. 启动前端

如果你需要改前端，进入前端目录：

```powershell
cd frontend
npm install
npm run dev
```

默认地址：
- 前端：`http://127.0.0.1:5174`

## 11. 前端环境变量说明

模板文件：
- `frontend/.env.example`

默认情况下，前端开发服务会把 `/api` 自动代理到 `http://127.0.0.1:8014`，所以本地开发通常不需要创建 `frontend/.env`。

只有在以下场景才需要创建：
- 前端连远程后端
- 本地后端端口不是 `8014`

示例：

```env
VITE_API_BASE_URL=https://your-api-domain.com
```

## 12. 首次启动后的建议配置

启动成功后，建议优先进入前端“系统设置”页面完成：

### 12.1 AI Key

可在页面中直接填写并保存，也可放到 `backend/.env`。

### 12.2 Bilibili 登录态

可在页面中一键读取本机浏览器登录态，也可手动粘贴 Cookie。

## 13. 最小自检清单

本地启动完成后，至少确认：

1. `docker compose ps` 里 PostgreSQL 和 Redis 正常运行
2. `http://127.0.0.1:8014/api/health` 返回 `200`
3. 前端页面可打开
4. Worker 已启动
5. 可以进入任务创建页

## 14. 常见问题

### PowerShell 不允许执行脚本

可在当前用户范围放开：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### `.venv` 创建失败

优先检查：
- 是否安装了 Python 3.11
- `python` 或 `py -3.11` 是否可用

### 前端能打开，但接口报错

优先检查：
- 后端是否已启动
- Worker 是否已启动
- `http://127.0.0.1:8014/api/health` 是否正常
- `8014` 端口是否被其它进程占用

### 任务一直排队

优先检查：
- Redis 是否正常
- Worker 是否运行
- 后端健康检查中的 `worker` 是否为 `ok`

### Playwright 安装失败

可重试：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

如果网络环境较严格，建议确认本机能正常下载浏览器运行时。
