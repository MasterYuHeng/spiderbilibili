# 本地开发与环境配置

> 文档角色：本文件只负责“本地部署”和“本地开发”两类链路。Docker 侧完整说明见 `docs/DOCKER_SETUP.md`。

## 1. 先选模式

本地有两种模式：

### 模式 A：轻量本地运行

适合：
- 只想在本机开箱即用运行
- 尽量少装宿主机依赖
- 不想本机安装 Node

特点：
- 宿主机安装轻量 Python 运行依赖
- 前端页面由 Docker 容器提供
- 重依赖按功能首次使用时再自动安装

入口：
- `launch-app.bat`
- `close-app.bat`

### 模式 B：完整本地开发

适合：
- 需要看源码和改代码
- 需要完整前后端开发体验
- 需要一次性装齐重依赖

特点：
- 宿主机安装完整 Python 依赖
- 宿主机安装前端 `node_modules`
- 前后端和 Worker 都直接在本机运行

入口：
- `launch-dev.bat`
- `close-dev.bat`

## 2. 前置要求

### 模式 A：轻量本地运行

- Git
- Python 3.11 或 3.12
- Docker Desktop 或 Docker Engine + Docker Compose v2

### 模式 B：完整本地开发

- Git
- Python 3.11 或 3.12
- Node.js 20 LTS 或更高版本
- npm 10+
- Docker Desktop 或 Docker Engine + Docker Compose v2

建议先确认以下命令可用：

```powershell
git --version
python --version
docker --version
docker compose version
```

完整本地开发再额外确认：

```powershell
npm --version
```

## 3. 获取项目

```powershell
git clone <your-repo-url>
cd spiderbilibili
```

## 4. 轻量本地运行

### 4.1 一键启动

```powershell
.\launch-app.bat
```

### 4.2 一键关闭

```powershell
.\close-app.bat
```

### 4.3 这条链路会做什么

- 自动创建 `backend/.env`
- 自动创建 `.venv-app`
- 安装 `backend/requirements.runtime.txt`
- 启动容器里的 PostgreSQL 和 Redis
- 启动容器里的静态前端页面
- 在宿主机启动后端和 Worker

### 4.4 默认地址

- Web：`http://127.0.0.1:8080`
- API：`http://127.0.0.1:8014/api`
- 健康检查：`http://127.0.0.1:8014/api/health`

如果 `8080` 已被占用，启动器会自动切换到下一个可用端口。

### 4.5 轻量依赖说明

轻量模式默认安装：
- `backend/requirements.runtime.txt`

不默认安装，但会在第一次真正用到对应功能时自动安装：
- `openai`
- `playwright`
- `cryptography`
- `openpyxl`
- `jieba`
- `prometheus-client`

对应场景：
- AI 摘要、分析、报告
- 浏览器登录态导入
- Excel 导出
- 主题提取与分词
- 监控指标

## 5. 完整本地开发

### 5.1 一键启动

```powershell
.\launch-dev.bat
```

### 5.2 一键关闭

```powershell
.\close-dev.bat
```

### 5.3 这条链路会做什么

- 自动创建 `backend/.env`
- 自动创建 `.venv`
- 安装 `backend/requirements.full.txt`
- 安装前端 `node_modules`
- 启动容器里的 PostgreSQL 和 Redis
- 在宿主机启动后端、Worker、Vite 前端

### 5.4 默认地址

- 前端：`http://127.0.0.1:5174`
- API：`http://127.0.0.1:8014/api`
- 健康检查：`http://127.0.0.1:8014/api/health`

### 5.5 如果你要手动安装完整依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.full.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

前端：

```powershell
cd frontend
npm install
npm run dev
```

## 6. 启动基础设施

无论是轻量本地运行还是完整本地开发，本地链路默认都依赖容器里的 PostgreSQL 和 Redis。

手动启动：

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

## 7. 配置后端环境变量

先复制模板：

```powershell
Copy-Item backend/.env.example backend/.env
```

本地默认通常不需要改这些地址：
- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`

需要按实际情况填写的主要是：
- `AI_PROVIDER`
- `AI_API_KEY` 或 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`
- `BILIBILI_COOKIE`

说明：
- 不配置 AI Key，系统通常仍可启动，但 AI 相关功能会受限
- 不配置 Bilibili 登录态，也能运行，但采集稳定性和结果可见性可能下降

## 8. 前端环境变量说明

模板文件：
- `frontend/.env.example`

说明：
- 完整本地开发模式下，Vite 默认把 `/api` 代理到 `http://127.0.0.1:8014`
- 轻量本地运行模式使用构建后的静态前端，不需要本机创建 `frontend/.env`

只有在以下场景才需要创建：
- 前端连远程后端
- 本地后端端口不是 `8014`

示例：

```env
VITE_API_BASE_URL=https://your-api-domain.com
```

## 9. 首次启动后的建议配置

启动成功后，建议优先进入前端“系统设置”页面完成：

### 9.1 AI Key

可在页面中直接填写并保存，也可放到 `backend/.env`。

### 9.2 Bilibili 登录态

可在页面中一键读取本机浏览器登录态，也可手动粘贴 Cookie。

## 10. 最小自检清单

### 轻量本地运行

1. `http://127.0.0.1:8014/api/health` 返回 `200`
2. Web 页面可打开
3. Worker 已启动
4. 可以进入任务创建页

### 完整本地开发

1. `docker compose ps` 里 PostgreSQL 和 Redis 正常运行
2. `http://127.0.0.1:8014/api/health` 返回 `200`
3. `http://127.0.0.1:5174` 可访问
4. Worker 已启动
5. 可以进入任务创建页

## 11. 常见问题

### PowerShell 不允许执行脚本

可在当前用户范围放开：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### `.venv-app` 或 `.venv` 创建失败

优先检查：
- 是否安装了 Python 3.11 或 3.12
- `python` 或 `py -3.12` 是否可用

### 页面能打开，但接口报错

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

完整本地开发可手动重试：

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```

轻量本地运行则在首次使用浏览器能力时自动补装。若网络受限，建议确认本机能访问 Playwright 浏览器运行时下载源。
