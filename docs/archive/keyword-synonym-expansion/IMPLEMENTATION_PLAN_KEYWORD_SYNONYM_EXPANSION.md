# 关键词同义补充功能完整实施计划

> 归档说明：本文件已在 2026-04-14 文档治理后移入归档目录，保留为专题实施追溯材料。当前项目级实施路线以 `../../03-implementation-roadmap.md` 为准。

## 1. 文档定位

- 对应 PRD：[PRD_KEYWORD_SYNONYM_EXPANSION.md](./PRD_KEYWORD_SYNONYM_EXPANSION.md)
- 冻结规格：[SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md](./SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md)
- 文档目的：给出从零到一落地该功能的完整实施步骤
- 范围说明：不是 MVP 方案，而是完整上线方案

## 2. 最终交付目标

功能上线后，系统应具备以下完整能力：

- 用户在任务创建页输入关键词后，可选择是否启用关键词同义补充
- 用户可选择补充个数
- 后端在任务执行前调用大模型生成 B 站语境下的同义词、简称、流行语
- 系统使用“原关键词 + 同义词列表”执行多搜索词抓取
- 多搜索词结果统一合并、去重、入库
- 每条视频结果可追踪其命中的搜索词
- 任务详情、视频结果、导出结果、任务报告中都能看到扩词信息
- 后续主题分析、UP 主分析、任务报告仍保持单任务链路，不按同义词拆分
- 重试、恢复、失败回退、日志、测试、文档都完整覆盖

## 3. 阶段 0 冻结结果

阶段 0 已冻结以下内容，后续开发必须严格遵守：

- 任务创建字段：
  - `enable_keyword_synonym_expansion`
  - `keyword_synonym_count`
- 视频结果字段：
  - `matched_keywords`
  - `primary_matched_keyword`
  - `keyword_match_count`
- `extra_params.keyword_expansion` 固定结构
- 扩词状态枚举：
  - `skipped`
  - `pending`
  - `success`
  - `fallback`
  - `failed`

详细定义见 [SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md](./SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md)。

## 4. 总体实施顺序

建议按以下顺序推进，避免返工：

1. 先冻结字段与数据口径
2. 再改数据库和后端契约
3. 再实现 AI 扩词服务
4. 再接入抓取主链路
5. 再补视频级来源存储与查询
6. 再做前端创建页与详情展示
7. 再补视频页、导出、报告展示
8. 最后做测试、回归、文档和上线检查

## 5. 详细实施计划

## Step 0：冻结命名、字段和状态枚举

### 已完成输出

- 字段命名已冻结
- `extra_params` 结构已冻结
- 视频结果新字段已冻结
- 扩词状态枚举已冻结

### 权威文档

- [SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md](./SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md)

### 本步完成标准

- 后续代码实现不得再新增第二套命名
- 数据库字段、前端字段、接口字段统一使用阶段 0 定义

## Step 1：扩展数据库模型与迁移脚本

### 目标

把视频命中来源词从临时内存信息升级成正式持久化字段。

### 需要修改

在 `TaskVideo` 增加以下字段：

- `matched_keywords: JSON`
- `primary_matched_keyword: String(255)`
- `keyword_match_count: Integer`

### 建议修改文件

- [task.py](/E:/code/fullstack/spiderbilibili/backend/app/models/task.py)
- 新增 Alembic 迁移文件：
  - `backend/alembic/versions/<new_revision>_add_keyword_expansion_fields_to_task_video.py`

### 迁移内容

- 为 `task_video` 新增 3 个字段
- 为 `primary_matched_keyword` 增加索引
- 历史数据默认回填：
  - `matched_keywords = []`
  - `primary_matched_keyword = null`
  - `keyword_match_count = 0`

### 验收点

- 数据库迁移可执行
- 旧任务不会因新字段为空而报错

## Step 2：扩展后端 API 契约与校验规则

### 目标

打通任务创建接口、视频结果接口和详情接口的扩词契约。

### 需要修改

在 `TaskCreateRequest` 中增加：

- `enable_keyword_synonym_expansion`
- `keyword_synonym_count`

在 `TaskVideoResultRead` 中增加：

- `matched_keywords`
- `primary_matched_keyword`
- `keyword_match_count`

在 `TaskDetail` / `TaskProgressPayload` 中继续透传 `extra_params.keyword_expansion`

### 固定规则

- 仅在 `crawl_mode = keyword` 时允许开启
- `keyword_synonym_count` 仅允许 `1 | 2 | 3 | 5`
- 未开启时 `keyword_synonym_count = null`
- 热榜模式传入扩词参数时，后端忽略并规范化为关闭状态

### 建议修改文件

- [task.py](/E:/code/fullstack/spiderbilibili/backend/app/schemas/task.py)
- [tasks.py](/E:/code/fullstack/spiderbilibili/backend/app/api/routes/tasks.py)
- [types.ts](/E:/code/fullstack/spiderbilibili/frontend/src/api/types.ts)

### 验收点

- 前端提交新增字段后，后端能稳定接收
- 非法参数能返回清晰错误

## Step 3：扩展任务创建与重试复制逻辑

### 目标

把扩词配置正式写入任务元数据，确保任务创建、重试、恢复口径一致。

### 需要修改

在任务创建时写入 `extra_params.task_options`：

- `enable_keyword_synonym_expansion`
- `keyword_synonym_count`

初始化 `extra_params.keyword_expansion`：

- `source_keyword`
- `enabled`
- `requested_synonym_count`
- `generated_synonyms = []`
- `expanded_keywords = [原始关键词]`
- `status = pending 或 skipped`
- `model_name = null`
- `error_message = null`
- `generated_at = null`

重试任务时：

- 复制原任务的扩词配置
- 若原任务扩词成功，则复制扩词结果
- 若原任务扩词未成功，则重置为 `pending`

恢复任务时：

- 直接复用当前任务已持久化扩词结果，不重新生成

### 建议修改文件

- [task_service.py](/E:/code/fullstack/spiderbilibili/backend/app/services/task_service.py)
- [test_task_api.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_task_api.py)
- [test_task_service.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_task_service.py)

### 验收点

- 创建任务后，详情接口返回扩词配置
- 重试和恢复时扩词状态符合冻结口径

## Step 4：新增关键词扩词服务

### 目标

把“大模型生成同义词”封装成独立服务。

### 建议新增文件

- `backend/app/services/keyword_expansion_service.py`

### 服务职责

- 判断是否需要扩词
- 调用现有 AI 客户端
- 生成结构化 JSON 结果
- 对结果做清洗、去重、兜底
- 产出统一扩词结果对象

### 复用现有基础设施

- [ai_client.py](/E:/code/fullstack/spiderbilibili/backend/app/services/ai_client.py)

### 输出结构

必须与冻结规格一致。

### 失败回退

- AI 不可用时：直接回退
- AI 返回格式错误时：直接回退
- AI 返回空列表时：标记 `fallback`

### 测试

- 新增 `backend/tests/test_keyword_expansion_service.py`

### 验收点

- 扩词服务可单独测试
- AI 成功、失败、空返回、格式错误都可稳定处理

## Step 5：在任务执行主链路中接入扩词

### 目标

把扩词接入执行链路，并确保它发生在搜索抓取之前。

### 需要修改

在 `CrawlPipelineService.run_task` 中新增以下流程：

1. 读取 `task_options`
2. 判断是否为关键词模式且启用了扩词
3. 若需要扩词：
   - 优先读取已持久化成功结果
   - 没有成功结果时调用 `KeywordExpansionService`
   - 将结果写回 `task.extra_params.keyword_expansion`
4. 根据扩词结果生成最终搜索词列表
5. 进入多搜索词抓取

### 必须新增日志

- `Starting keyword expansion.`
- `Keyword expansion succeeded.`
- `Keyword expansion failed, fallback to source keyword.`
- `Starting keyword search for expansion item.`
- `Finished multi-keyword search merge.`

### 建议修改文件

- [crawl_pipeline_service.py](/E:/code/fullstack/spiderbilibili/backend/app/services/crawl_pipeline_service.py)

### 验收点

- 扩词发生在搜索之前
- 单任务只会扩词一次并持久化
- 同一任务恢复运行时不重复扩词

## Step 6：改造搜索抓取为多搜索词执行 + 统一去重

### 目标

把原来的单关键词搜索改造成多搜索词编排。

### 需要修改

当前逻辑：

- 单次调用 `search_spider.search_keyword(task.keyword, ...)`

目标逻辑：

- 对 `expanded_keywords` 逐个调用 `search_spider.search_keyword(keyword_i, ...)`
- 汇总为一个候选列表
- 对同一视频按 `bvid` 去重
- 合并命中来源词

### 建议实现方式

新增内部方法，例如：

- `_collect_keyword_candidates(...)`

职责：

- 依次抓取每个搜索词
- 记录每个搜索词抓到多少条
- 合并相同 `bvid`
- 生成统一候选对象

### 需要调整的数据结构

扩展 `SearchVideoCandidate`：

- `matched_keywords`
- `primary_matched_keyword`

### 去重规则

同一 `bvid` 被多个搜索词命中时：

- 合并 `matched_keywords`
- `primary_matched_keyword` 取原始关键词优先，否则取最早命中的词
- `search_rank` 取最佳名次

### 建议修改文件

- [models.py](/E:/code/fullstack/spiderbilibili/backend/app/crawler/models.py)
- [search_spider.py](/E:/code/fullstack/spiderbilibili/backend/app/crawler/search_spider.py)
- [crawl_pipeline_service.py](/E:/code/fullstack/spiderbilibili/backend/app/services/crawl_pipeline_service.py)

### 验收点

- 最终候选列表不重复
- 每条候选都能知道自己被哪些搜索词命中

## Step 7：改造视频评分与入库存储

### 目标

让扩词命中信息进入正式结果表。

### 需要修改

在 `persist_scored_video` 流程中，把候选对象上的：

- `matched_keywords`
- `primary_matched_keyword`
- `keyword_match_count`

写入 `TaskVideo`

### 评分口径

评分继续使用原始关键词 `task.keyword`，不改成用某个同义词评分。

### 建议修改文件

- [video_storage_service.py](/E:/code/fullstack/spiderbilibili/backend/app/services/video_storage_service.py)
- [task.py](/E:/code/fullstack/spiderbilibili/backend/app/models/task.py)

### 验收点

- 入库后每条 `TaskVideo` 有稳定命中信息
- 评分逻辑未被同义词污染

## Step 8：扩展结果查询、详情接口和导出结构

### 目标

把扩词信息和命中信息完整暴露给前端与导出功能。

### 需要修改

#### 8.1 视频结果接口

返回：

- `matched_keywords`
- `primary_matched_keyword`
- `keyword_match_count`

#### 8.2 任务详情与进度接口

透出：

- `keyword_expansion`
- `search_keywords_used`
- `expanded_keyword_count`

#### 8.3 导出接口

导出 `videos` 数据集时增加列：

- 原始关键词
- 是否启用扩词
- 实际搜索词列表
- 当前视频命中词列表
- 主命中词
- 命中词数量

### 建议修改文件

- `backend/app/services/task_result_service.py`
- `backend/app/services/task_export_service.py`
- [task.py](/E:/code/fullstack/spiderbilibili/backend/app/schemas/task.py)
- [types.ts](/E:/code/fullstack/spiderbilibili/frontend/src/api/types.ts)

### 验收点

- 前端拿到完整字段
- 导出文件可直接看出某条视频是因哪个词被召回

## Step 9：前端任务创建页改造

### 目标

让用户能在任务创建时明确控制扩词开关和数量。

### 需要修改

在 `TaskCreateView` 中新增表单项：

- 启用关键词同义补充
- 补充个数

### 展示逻辑

- 仅 `crawl_mode = keyword` 时展示
- 关闭时数量控件禁用或隐藏
- 默认关闭
- 默认数量为 `1`

### 文案要求

- 明确说明：仅增强搜索召回，不会拆成多个分析任务

### 建议修改文件

- [TaskCreateView.vue](/E:/code/fullstack/spiderbilibili/frontend/src/views/TaskCreateView.vue)
- [types.ts](/E:/code/fullstack/spiderbilibili/frontend/src/api/types.ts)
- [TaskCreateView.spec.ts](/E:/code/fullstack/spiderbilibili/frontend/src/views/__tests__/TaskCreateView.spec.ts)

### 验收点

- 表单字段显示正确
- 提交时携带新增字段
- 热榜模式自动隐藏

## Step 10：前端任务详情页展示扩词信息

### 目标

让用户在任务详情页能直接看到这次任务用了哪些搜索词。

### 建议展示内容

- 原始关键词
- 是否启用扩词
- 扩词状态
- 补充个数
- 实际生成的同义词
- 最终搜索词列表
- 扩词失败原因或回退说明

### 建议修改文件

- [TaskDetailView.vue](/E:/code/fullstack/spiderbilibili/frontend/src/views/TaskDetailView.vue)
- [taskLifecycle.ts](/E:/code/fullstack/spiderbilibili/frontend/src/utils/taskLifecycle.ts)

### 验收点

- 用户能明确知道当前任务如何扩词
- 扩词失败时能看到“已回退为原关键词”

## Step 11：前端视频结果页展示命中来源词

### 目标

让用户能判断某条视频是因原词命中，还是因某个同义词被召回。

### 建议展示

- 命中搜索词
- 主命中词
- 命中多个词时以标签形式展示

### 建议修改文件

- [VideoListView.vue](/E:/code/fullstack/spiderbilibili/frontend/src/views/VideoListView.vue)
- [types.ts](/E:/code/fullstack/spiderbilibili/frontend/src/api/types.ts)

### 验收点

- 视频结果页能看到命中来源
- 同一视频被多个词命中时标签显示完整

## Step 12：任务报告与分析页补充搜索口径说明

### 目标

虽然报告不按同义词拆分，但要让用户知道这次分析样本的搜索来源。

### 需要修改

报告页或报告快照中增加搜索口径说明：

- 原始关键词
- 实际搜索词列表
- 扩词是否启用
- 扩词状态

### 建议修改文件

- `backend/app/services/task_report_service.py`
- [TaskReportView.vue](/E:/code/fullstack/spiderbilibili/frontend/src/views/TaskReportView.vue)

### 验收点

- 用户在报告页能理解数据来源范围

## Step 13：补全自动化测试

### 后端测试

- 创建任务参数校验
- 扩词服务成功、失败、空返回、格式错误
- 多关键词抓取与去重
- 扩词失败回退
- 重试和恢复逻辑
- 视频级字段落库
- 结果接口和导出接口返回新增字段

### 前端测试

- 创建页开关与数量交互
- 详情页展示扩词结果
- 视频页展示命中来源词

### 建议涉及文件

- [test_task_api.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_task_api.py)
- [test_task_service.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_task_service.py)
- [test_crawl_pipeline_service.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_crawl_pipeline_service.py)
- [test_crawler_review_regressions.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_crawler_review_regressions.py)
- 新增 `backend/tests/test_keyword_expansion_service.py`
- [TaskCreateView.spec.ts](/E:/code/fullstack/spiderbilibili/frontend/src/views/__tests__/TaskCreateView.spec.ts)
- [TaskDetailView.spec.ts](/E:/code/fullstack/spiderbilibili/frontend/src/views/__tests__/TaskDetailView.spec.ts)
- [VideoListView.spec.ts](/E:/code/fullstack/spiderbilibili/frontend/src/views/__tests__/VideoListView.spec.ts)

## Step 14：手工回归清单

必跑用例：

- 标准成功路径：和平精英 -> 吃鸡
- 关闭扩词：行为与旧逻辑一致
- AI 不可用：自动 fallback
- 同一视频多词命中：展示多个命中标签
- 重试：复制或复用扩词结果
- 导出：新增列完整

### 本步补充要求

为了避免 Step 14 只停留在“清单存在、无人落地”的状态，本步应至少产出一份可追溯的回归记录文档，建议放在 `docs/` 下，明确记录：

- 执行日期
- 执行命令
- 每个必跑用例的结果
- 是否发现问题
- 若无问题，明确给出“可进入 Step 15 / Step 16”的结论

本仓库当前回归记录见：

- [REGRESSION_PHASE14_KEYWORD_SYNONYM_EXPANSION.md](./REGRESSION_PHASE14_KEYWORD_SYNONYM_EXPANSION.md)

## Step 15：文档更新

需要更新：

- [README.md](/E:/code/fullstack/spiderbilibili/README.md)
- [LOCAL_SETUP.md](/E:/code/fullstack/spiderbilibili/docs/LOCAL_SETUP.md)

说明内容：

- 该功能只对关键词任务生效
- 扩词只增强搜索召回
- 扩词失败会自动回退

## Step 16：上线前检查

必检项：

- 数据库迁移脚本已验证
- 新字段不会影响旧任务查询
- 扩词失败不会阻断主链路
- 导出文件结构已验证
- 前端字段与后端字段完全一致
- 所有新增测试已通过

上线顺序建议：

1. 合并数据库迁移
2. 部署后端
3. 跑迁移
4. 部署前端
5. 创建一条真实扩词任务验证

## 6. 建议涉及的核心文件清单

### 后端

- [task.py](/E:/code/fullstack/spiderbilibili/backend/app/models/task.py)
- [models.py](/E:/code/fullstack/spiderbilibili/backend/app/crawler/models.py)
- [search_spider.py](/E:/code/fullstack/spiderbilibili/backend/app/crawler/search_spider.py)
- [task.py](/E:/code/fullstack/spiderbilibili/backend/app/schemas/task.py)
- [tasks.py](/E:/code/fullstack/spiderbilibili/backend/app/api/routes/tasks.py)
- [task_service.py](/E:/code/fullstack/spiderbilibili/backend/app/services/task_service.py)
- [crawl_pipeline_service.py](/E:/code/fullstack/spiderbilibili/backend/app/services/crawl_pipeline_service.py)
- [video_storage_service.py](/E:/code/fullstack/spiderbilibili/backend/app/services/video_storage_service.py)
- [ai_client.py](/E:/code/fullstack/spiderbilibili/backend/app/services/ai_client.py)
- 新增 `backend/app/services/keyword_expansion_service.py`
- 新增 Alembic 迁移文件

### 前端

- [types.ts](/E:/code/fullstack/spiderbilibili/frontend/src/api/types.ts)
- [TaskCreateView.vue](/E:/code/fullstack/spiderbilibili/frontend/src/views/TaskCreateView.vue)
- [TaskDetailView.vue](/E:/code/fullstack/spiderbilibili/frontend/src/views/TaskDetailView.vue)
- [VideoListView.vue](/E:/code/fullstack/spiderbilibili/frontend/src/views/VideoListView.vue)
- [TaskReportView.vue](/E:/code/fullstack/spiderbilibili/frontend/src/views/TaskReportView.vue)
- [taskLifecycle.ts](/E:/code/fullstack/spiderbilibili/frontend/src/utils/taskLifecycle.ts)

### 测试

- [test_task_api.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_task_api.py)
- [test_task_service.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_task_service.py)
- [test_crawl_pipeline_service.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_crawl_pipeline_service.py)
- [test_crawler_review_regressions.py](/E:/code/fullstack/spiderbilibili/backend/tests/test_crawler_review_regressions.py)
- [TaskCreateView.spec.ts](/E:/code/fullstack/spiderbilibili/frontend/src/views/__tests__/TaskCreateView.spec.ts)
- [TaskDetailView.spec.ts](/E:/code/fullstack/spiderbilibili/frontend/src/views/__tests__/TaskDetailView.spec.ts)
- [VideoListView.spec.ts](/E:/code/fullstack/spiderbilibili/frontend/src/views/__tests__/VideoListView.spec.ts)
- 新增关键词扩词服务测试

## 7. 推荐开发顺序

1. 先完成 Step 1 到 Step 3
2. 再完成 Step 4 到 Step 7
3. 跑后端测试与迁移验证
4. 再完成 Step 8 到 Step 12
5. 跑前端测试
6. 执行 Step 14 手工回归
7. 更新文档并上线

## 8. 最终验收标准

满足以下条件才算完整交付：

- 创建页可配置扩词
- 后端能稳定扩词并持久化结果
- 多搜索词抓取、去重、入库成功
- 视频级命中来源可查询、可展示、可导出
- 详情页、视频页、报告页都能体现扩词信息
- 重试、恢复、失败回退口径完整
- 自动化测试与手工回归都通过
