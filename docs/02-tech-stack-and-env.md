# 技术栈与环境文档

## 1. 文档定位

本文件定义项目级技术栈、运行环境、目录职责、配置文件口径和开源发布基线。

具体操作步骤由以下文档承担：
- `docs/LOCAL_SETUP.md`
- `docs/DOCKER_SETUP.md`

## 2. 当前技术栈

### 2.1 前端

- Vue 3
- TypeScript
- Vite
- Vue Router
- Pinia
- Axios
- Element Plus
- ECharts
- Vitest

### 2.2 后端

- FastAPI
- SQLAlchemy
- Alembic
- Celery
- Pydantic
- PostgreSQL
- Redis
- Uvicorn
- Pytest

### 2.3 采集与分析

- httpx
- Playwright
- selectolax
- jieba
- pandas
- scikit-learn
- openpyxl
- OpenAI Compatible SDK

### 2.4 运维与部署

- Docker / Docker Compose
- Nginx
- Prometheus
- Alertmanager
- Grafana

## 3. 当前架构解释

项目当前是“前端 + 后端 API + 异步任务 + 数据存储 + 采集/分析服务”的结构：

- `frontend/`：任务创建、结果展示、主题分析、作者分析、报告、系统设置
- `backend/app/api/`：对外 API
- `backend/app/services/`：任务、采集、分析、导出、报告、验收等业务逻辑
- `backend/app/crawler/`：Bilibili 采集逻辑
- `backend/alembic/`：数据库迁移
- `scripts/`：本地启动、关闭、辅助脚本
- `docker/`：生产部署和监控相关配置

## 4. 关键目录职责

- `backend/`：后端服务、数据库模型、迁移、测试
- `frontend/`：前端页面、组件、路由、状态管理、测试
- `scripts/`：Windows 一键启动、关闭、本地辅助启动
- `docker/`：生产部署与监控配置
- `docs/codex/`：固定协作文档层
- `docs/00-05`：项目运行期主文档层
- `docs/archive/`：历史专题归档层

## 5. 环境基线

### 5.1 本地开发

- Git
- Python 3.11
- Node.js 20 LTS 或更高
- npm 10+
- Docker Desktop 或 Docker Engine + Compose v2

### 5.2 Docker 部署

- Docker Engine 24+
- Docker Compose v2

## 6. 默认端口口径

- `5174`：前端开发服务
- `4174`：前端预览
- `8014`：后端 API
- `5434`：本地 PostgreSQL 容器映射
- `6381`：本地 Redis 容器映射
- `80`：整套 Docker 部署下的 Web 入口默认端口
- `3000`：Grafana 默认端口
- `9090`：Prometheus 默认端口
- `9093`：Alertmanager 默认端口

## 7. 关键配置文件

### 7.1 后端

- `backend/.env.example`：后端环境变量模板
- `backend/.env`：本地实际运行配置

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

### 7.2 前端

- `frontend/.env.example`：前端环境变量模板
- `frontend/.env`：可选，本地连接远程后端时使用

### 7.3 Docker

- `docker/.env.production.example`：整套 Docker 部署模板
- `docker/.env.production`：部署时的实际环境变量文件

## 8. 启动入口

### 8.1 推荐本地启动

- `launch-dev.bat`
- `close-dev.bat`

### 8.2 手动本地开发

详见：
- `docs/LOCAL_SETUP.md`

### 8.3 Docker 使用

详见：
- `docs/DOCKER_SETUP.md`

## 9. 文档分层与职责

- `docs/codex/`：固定协作文档层，不作为普通项目文档重写
- `docs/00-05`：项目运行期主文档层，负责需求、PRD、技术口径、路线、当前状态和决策
- `docs/LOCAL_SETUP.md` 与 `docs/DOCKER_SETUP.md`：操作指南层，只回答如何启动、如何部署、如何配置
- `docs/archive/`：历史专题归档层
- `docs/90-tech-completion-report.md` 与 `docs/91-requirement-completion-report.md`：完成评估层

## 10. 开源发布基线

当前仓库按开源发布口径整理时，应保持以下基线：

- 根目录 `README.md` 作为对外入口，优先面向首次访问仓库的使用者
- 环境变量只提交模板文件，不提交真实配置
- 本地开发教程和 Docker 教程保持独立，避免把“如何操作”和“项目级口径”混写
- 不提交运行日志、运行时数据、个人登录态、API Key、数据库密码
- 开源版本默认保留完整功能，但所有敏感信息都要求由使用者自行配置

## 11. .gitignore 与开源安全口径

当前开源口径下，以下文件和目录应保持不入库：

- `backend/.env`
- `frontend/.env`
- `docker/.env.production`
- `.runtime/`
- `backend/data/`
- `backend/logs/`
- `frontend/node_modules/`
- `frontend/dist/`
- `.venv/`

## 12. 文档治理约束

- 项目级信息优先写入 `docs/00-05`
- 操作型内容优先写入 `docs/LOCAL_SETUP.md` 和 `docs/DOCKER_SETUP.md`
- 失去主文档地位但仍有参考价值的专题文档归档到 `docs/archive/<feature-slug>/`

## 13. 本轮性能优化口径

本轮不改变项目需求边界和核心架构，主要调整以下技术实现口径：

- Windows 启动链路继续保留 `launch-dev.bat -> scripts/start-dev.ps1`，但启动器默认以“前端页面可访问 + 后端 API 可访问”为首要就绪条件，避免把浏览器打开和启动器返回阻塞到 Worker 完全就绪之后。
- `scripts/start-backend.ps1` 在本地开发模式下增加 Alembic 版本对比，数据库已经处于当前 head 时跳过重复 `upgrade head`，减少重复启动耗时。
- 任务视频列表、主题分析、报告生成相关的“最新指标快照”查询统一收敛为“按当前 task_id 先过滤，再做窗口排序”，避免对全库 `video_metric_snapshot` 做无谓排序。
- 主题分析内部获取 Top N 视频时，优先在 SQL 层限流，避免先读取整任务全部视频再切片。
