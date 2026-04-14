# 阶段 14 回归记录：关键词同义补充

> 归档说明：本文件已在 2026-04-14 文档治理后移入归档目录，保留为专题回归记录。当前项目级状态和路线以 `../../04-current-state.md` 与 `../../03-implementation-roadmap.md` 为准。

## 1. 文档目的

记录 [IMPLEMENTATION_PLAN_KEYWORD_SYNONYM_EXPANSION.md](./IMPLEMENTATION_PLAN_KEYWORD_SYNONYM_EXPANSION.md) 中 Step 14 的实际执行结果，确保“手工回归清单”有可追溯的完成产物，而不是只停留在待办项。

## 2. 参考文档

- [PRD_KEYWORD_SYNONYM_EXPANSION.md](./PRD_KEYWORD_SYNONYM_EXPANSION.md)
- [SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md](./SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md)
- [IMPLEMENTATION_PLAN_KEYWORD_SYNONYM_EXPANSION.md](./IMPLEMENTATION_PLAN_KEYWORD_SYNONYM_EXPANSION.md)

## 3. 执行日期

- 执行时间：2026-04-14
- 执行范围：后端服务层、API 层、导出链路、前端创建页、详情页、结果页、报告页

## 4. 执行方式

本次回归遵循“整体完成”原则，不按 MVP 缩减场景。  
由于回归点同时覆盖服务、接口、导出和前端展示，本次采用“接口/服务专项测试 + 前端页面测试”的组合方式执行，作为阶段 14 的正式回归产物。

执行命令：

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_crawl_pipeline_service.py backend\tests\test_task_service.py backend\tests\test_task_report_service.py backend\tests\test_crawler_dedupe.py backend\tests\test_task_video_model.py backend\tests\test_video_storage_service.py -q
.\.venv\Scripts\python.exe -m pytest backend\tests\test_task_api.py -q
cd frontend
npx vitest run src\views\__tests__\TaskCreateView.spec.ts src\views\__tests__\TaskDetailView.spec.ts src\views\__tests__\TaskReportView.spec.ts src\views\__tests__\VideoListView.spec.ts src\components\tasks\__tests__\TaskSearchContextCard.spec.ts src\router\__tests__\router.spec.ts
```

执行结果汇总：

- 后端专项回归：28 通过
- 后端 API 回归：36 通过
- 前端页面回归：16 通过

## 5. 回归项结果

### 5.1 标准成功路径：和平精英 -> 吃鸡

结论：通过

验证点：

- 扩词服务成功返回同义词后，搜索词列表变为 `["和平精英", "吃鸡"]`
- 搜索链路按原词优先、扩词追加的顺序执行
- `crawl_stats.search_keywords_used` 正确持久化
- 详情页、报告页、视频结果页都能展示搜索口径

对应验证：

- `backend/tests/test_crawl_pipeline_service.py`
- `frontend/src/views/__tests__/TaskDetailView.spec.ts`
- `frontend/src/views/__tests__/TaskReportView.spec.ts`
- `frontend/src/views/__tests__/VideoListView.spec.ts`

### 5.2 关闭扩词：行为与旧逻辑一致

结论：通过

验证点：

- 关闭扩词时 `keyword_expansion.status = "skipped"`
- `expanded_keywords` 仅保留原始关键词
- 不伪造额外搜索词
- 热榜模式继续忽略扩词参数

对应验证：

- `backend/tests/test_task_api.py`
- `frontend/src/views/__tests__/TaskCreateView.spec.ts`
- `frontend/src/views/__tests__/TaskDetailView.spec.ts`
- `frontend/src/views/__tests__/TaskReportView.spec.ts`
- `frontend/src/views/__tests__/VideoListView.spec.ts`

### 5.3 AI 不可用：自动 fallback

结论：通过

验证点：

- AI 不可用或扩词结果为空时，状态进入 `fallback`
- 主任务不阻断，自动退回原始关键词抓取
- 搜索词列表仅保留原始关键词
- 搜索阶段写入 warning 日志

对应验证：

- `backend/tests/test_keyword_expansion_service.py`
- `backend/tests/test_crawl_pipeline_service.py`

### 5.4 同一视频多词命中：展示多个命中标签

结论：通过

验证点：

- 同一 `bvid` 多搜索词命中后合并去重
- `matched_keywords`、`primary_matched_keyword`、`keyword_match_count` 正确入库
- 视频结果页可见多个命中标签与主命中词

对应验证：

- `backend/tests/test_crawler_dedupe.py`
- `backend/tests/test_crawl_pipeline_service.py`
- `backend/tests/test_task_video_model.py`
- `backend/tests/test_video_storage_service.py`
- `frontend/src/views/__tests__/VideoListView.spec.ts`

### 5.5 重试：复制或复用扩词结果

结论：通过

验证点：

- 原任务扩词成功时，重试任务复制成功扩词结果
- 原任务为 `fallback` 或未成功状态时，重试任务重置为 `pending`
- `resume` 复用当前任务已持久化扩词结果，不重复扩词

对应验证：

- `backend/tests/test_task_service.py`
- `backend/tests/test_task_api.py`

### 5.6 导出：新增列完整

结论：通过

验证点：

- 视频导出包含：
  - `original_keyword`
  - `enable_keyword_synonym_expansion`
  - `search_keywords_used`
  - `expanded_keyword_count`
  - `matched_keywords`
  - `primary_matched_keyword`
  - `keyword_match_count`
- JSON、CSV、Excel 三种格式都能正常导出

对应验证：

- `backend/tests/test_task_api.py`

## 6. 回归结论

截至 2026-04-14，Step 14 清单中的 6 个必跑场景均已完成回归验证，未发现需要修改核心功能或核心架构的问题。

当前建议顺序：

1. 进入 Step 15，补正文档中的用户说明与开发说明
2. 进入 Step 16，执行上线前检查

## 7. 备注

- 本次回归没有改变阶段 0 已冻结的字段命名、状态枚举、`extra_params` 结构和单任务主链路架构。
- `backend/tests/test_task_api.py` 运行时间明显长于其他专项测试，执行阶段 14 时建议单独跑，避免组合命令超时误判。
