# 本地开发与环境配置

本文档说明如何在本地开发环境中运行 SpiderBilibili，包括 Windows 一键启动方式和手动启动方式。

## 1. 环境要求

推荐版本：

- Git
- Python 3.11
- Node.js 20 LTS
- npm 10+
- Docker Desktop

建议先确认下面的命令都能正常执行：

```powershell
git --version
python --version
npm --version
docker --version
docker compose version
```

## 2. 获取项目

```powershell
git clone <your-repo-url>
cd spiderbilibili
```

## 3. 推荐方式：Windows 一键启动

如果你在 Windows 上使用本项目，最推荐直接使用根目录启动器：

```powershell
.\launch-dev.bat
```

启动器会自动完成：

- 创建 `backend/.env`
- 创建 `.venv`
- 安装后端依赖
- 安装 Playwright Chromium 运行时
- 安装前端依赖
- 启动 PostgreSQL 和 Redis
- 启动后端、Worker、前端

关闭环境：

```powershell
.\close-dev.bat
```

## 4. 手动启动流程

### 4.1 启动基础设施

```powershell
docker compose up -d
```

启动后默认端口：

- PostgreSQL：`5434`
- Redis：`6381`

### 4.2 配置后端环境变量

复制模板：

```powershell
Copy-Item backend/.env.example backend/.env
```

首次使用时一般不需要改动数据库和 Redis 地址。如果你本机端口冲突，再按实际情况修改。

### 4.3 创建 Python 虚拟环境并安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m playwright install
```

### 4.4 初始化数据库

```powershell
cd backend
..\.venv\Scripts\python.exe -m alembic upgrade head
cd ..
```

如果你直接用 `scripts/start-backend.ps1`，它也会在启动前自动执行迁移。

### 4.5 启动后端

```powershell
.\scripts\start-backend.ps1
```

默认地址：

- `http://127.0.0.1:8014/api`

### 4.6 启动 Worker

```powershell
.\scripts\start-worker.ps1
```

### 4.7 启动前端

```powershell
cd frontend
npm install
npm run dev
```

默认地址：

- `http://127.0.0.1:5174`

## 5. 前端开发环境说明

项目已经内置本地开发代理：

- 当前端访问 `/api/*` 时，开发服务器会自动转发到 `http://127.0.0.1:8014`

因此本地开发通常不需要配置 `frontend/.env`。

如果你需要连接远程后端，可自行创建：

```env
VITE_API_BASE_URL=https://your-api-domain.com
```

## 6. 首次启动后的必要配置

前端打开后，建议先在左侧 `系统设置` 完成以下配置。

### 6.1 DeepSeek API Key

你可以：

- 在页面中直接输入并保存
- 或在 `backend/.env` 中填写

### 6.2 Bilibili 登录态

你可以：

- 点击“一键读取”自动导入本机浏览器登录态
- 或手动粘贴 Cookie

## 7. 常见开发问题

### PowerShell 拒绝执行脚本

可以在当前用户范围放开脚本执行权限：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 启动器无法创建 `.venv`

请确认：

- 已正确安装 Python 3.11
- `python` 或 `py -3.11` 可直接运行

### 前端显示正常但接口报错

请确认：

- 后端已启动
- Worker 已启动
- `http://127.0.0.1:8014/api/health` 返回正常
