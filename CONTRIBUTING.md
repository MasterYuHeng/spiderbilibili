# 贡献指南

感谢你为 SpiderBilibili 做贡献。为了让仓库保持可复现、可协作、适合开源发布，请在提交前遵循下面的约定。

## 开始之前

- 先阅读 [README.md](README.md)、[docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) 和 [docs/DOCKER_SETUP.md](docs/DOCKER_SETUP.md)。
- 所有本地配置都应从 `*.example` 模板复制生成，不要直接修改示例文件中的占位值。
- 不要提交任何真实 API Key、Cookie、代理地址、数据库凭据、日志、导出结果、抓取原始数据或本地虚拟环境目录。

## 选择开发链路

根据目标选择合适的启动方式：

- 轻量本地运行：`.\launch-app.bat`
- 完整本地开发：`.\launch-dev.bat`
- 轻量 Docker 运行：`.\launch-docker.bat`
- 完整 Docker 开发：`.\launch-docker-dev.bat`

如果你需要修改源代码、运行测试或验证前后端联调，请优先使用“完整本地开发”或“完整 Docker 开发”。

## 提交前检查

后端：

```powershell
cd backend
python -m pytest
python -m ruff check .
python -m black --check .
python -m mypy app
```

前端：

```powershell
cd frontend
npm run lint
npm run test
npm run build
```

如果你的改动涉及部署、启动脚本、依赖结构或环境变量，请同步更新对应文档。

## Pull Request 约定

- 保持单个 PR 聚焦在一个明确目标，避免把无关重构和功能改动混在一起。
- 行为变更必须补充测试，或者在 PR 描述中明确说明为什么暂时无法覆盖。
- UI、接口、部署方式或依赖策略变更时，请补充 README 或 `docs/` 文档。
- 不要提交构建产物、运行日志、本地数据库、虚拟环境和任何临时调试文件。

## Issue 建议

- Bug 报告请附带复现步骤、实际结果、预期结果和运行方式。
- 功能建议请说明使用场景、当前痛点和期望结果。
- 涉及漏洞或敏感信息时，不要直接公开发 Issue，请改走 [SECURITY.md](SECURITY.md) 中的披露流程。
