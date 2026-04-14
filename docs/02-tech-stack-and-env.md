# 技术栈与环境文档

## 1. 文档定位

本文件定义项目级技术栈、运行环境、目录职责和环境基线。具体操作步骤以 `docs/LOCAL_SETUP.md` 和 `docs/DOCKER_SETUP.md` 为补充指南。

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
- Sass
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
- OpenAI 兼容 SDK

### 2.4 运维与部署

- Docker / Docker Compose
- Nginx
- Prometheus
- Alertmanager
- Grafana

## 3. 当前架构解释

项目当前是典型的“前端 + 后端 API + 异步任务 + 数据存储 + 采集/分析服务”结构：

- `frontend/` 提供任务创建、结果展示、报告和设置页面。
- `backend/app/api/` 暴露系统设置、健康检查和任务相关接口。
- `backend/app/services/` 组织采集、分析、导出、验收和配置服务。
- `backend/app/crawler/` 负责搜索、详情和 UP 主等采集逻辑。
- `backend/alembic/` 维护数据库迁移。
- `docker/` 与根目录 Compose 文件负责本地基础设施和整套部署。

## 4. 关键目录职责

- `backend/`：后端服务、数据模型、接口、业务服务、迁移、测试
- `frontend/`：前端页面、组件、路由、状态管理、前端测试
- `scripts/`：本地启动和开发辅助脚本
- `docker/`：生产部署与监控相关配置
- `docs/codex/`：固定协作文档，不作为普通项目文档改写
- `docs/00-05`：项目级主文档
- `docs/archive/`：历史专题文档归档区

## 5. 环境基线

### 5.1 本地开发

- Git
- Python 3.11
- Node.js 20 LTS 或更高
- npm 10+
- Docker Desktop

### 5.2 Docker 部署

- Docker Engine 24+
- Docker Compose v2

## 6. 默认端口口径

- `5174`：前端开发服务器
- `8014`：后端 API
- `5434`：PostgreSQL
- `6381`：Redis
- `4174`：前端预览端口

## 7. 关键配置文件

### 7.1 后端

- `backend/.env.example`：后端环境变量模板
- `backend/.env`：本地运行配置

常见关键项：

- `DATABASE_URL`
- `REDIS_URL`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `AI_PROVIDER`
- `DEEPSEEK_API_KEY`
- `BILIBILI_COOKIE`

### 7.2 前端

- `frontend/.env.example`：前端环境变量模板
- `frontend/.env`：可选，本地连远程后端时使用

### 7.3 Docker

- `docker/.env.production.example`：整套部署配置模板
- `docker/.env.production`：部署时的实际环境变量文件

## 8. 运行与验证入口

### 8.1 推荐本地启动

- `launch-dev.bat`
- `close-dev.bat`

### 8.2 手动本地开发

详见 `docs/LOCAL_SETUP.md`。

### 8.3 Docker 使用

详见 `docs/DOCKER_SETUP.md`。

## 9. 文档分层与职责

- `docs/codex/`：固定协作文档层。默认长期有效，除非用户明确要求，否则不重写。
- `docs/00-05`：项目运行期主文档层。负责需求解释、PRD、技术口径、实施路线、当前状态和关键决策。
- `docs/LOCAL_SETUP.md` 与 `docs/DOCKER_SETUP.md`：操作指南层。只回答“怎么启动、怎么部署、怎么操作”。
- `docs/archive/`：归档层。保留已失去主文档地位但仍有追溯价值的专题文档与过程记录。
- `docs/90-tech-completion-report.md` 与 `docs/91-requirement-completion-report.md`：完成评估层。仅在进入收口评估阶段时正式补全。

## 10. 文档治理约束

- 项目级信息优先回写到 `docs/00-05`，不再把专题 PRD、Spec、Plan 直接堆在 `docs/` 根目录。
- 环境基线变化先更新本文件，再决定是否同步 `docs/LOCAL_SETUP.md` 或 `docs/DOCKER_SETUP.md`。
- 专题文档失去主文档地位后，统一迁入 `docs/archive/<feature-slug>/`，并由 `docs/archive/README.md` 维护归档使用说明。
