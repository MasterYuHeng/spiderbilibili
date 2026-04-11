# 阶段6：AI 摘要与主题提取实现说明

## 1. 目标

阶段 6 的目标是把阶段 5 已经清洗并落库的 `video_text_content`，正式接入 AI 摘要与主题提取链路，并将结构化结果写入 `ai_summary`。

本阶段完成后，系统具备以下能力：

- 基于标准 OpenAI 协议调用大模型
- 对单个视频生成摘要、主题词、主主题、表达风格和置信度
- 对单个任务内的全部视频分批执行 AI 分析
- 在 AI 服务不可用或返回异常结构时，自动走本地兜底策略
- 将 AI 处理进度、回退次数和失败信息写入任务日志与任务摘要

## 2. 核心实现

### 2.1 输出结构

新增结构化 schema：

- [analysis.py](E:\code\fullstack\spiderbilibili\backend\app\schemas\analysis.py)

当前固定输出字段：

- `summary`
- `topics`
- `primary_topic`
- `tone`
- `confidence`

该 schema 会对空摘要、空主题词、重复主题词做基础清洗，确保后续落库结果稳定。

### 2.2 AI 客户端

新增服务：

- [ai_client.py](E:\code\fullstack\spiderbilibili\backend\app\services\ai_client.py)

能力包括：

- 支持标准 OpenAI Chat Completions 协议
- 支持自定义 `base_url`
- 支持模型切换
- 支持超时与重试
- 支持 JSON 输出解析
- 支持处理代码块包裹的 JSON

当前读取的环境变量与配置包括：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT_SECONDS`
- `OPENAI_MAX_RETRIES`

### 2.3 单视频分析服务

新增服务：

- [video_ai_service.py](E:\code\fullstack\spiderbilibili\backend\app\services\video_ai_service.py)

主要逻辑：

1. 读取任务下已清洗的 `video_text_content`
2. 结合标题、标签、语言和清洗文本构造 prompt
3. 调用 AI 客户端获取 JSON 结果
4. 对摘要长度、主题词数量和主主题做质量校验
5. 将结果 upsert 到 `ai_summary`

### 2.4 批量分析与 Worker 集成

当前已接入：

- [worker.py](E:\code\fullstack\spiderbilibili\backend\app\worker.py)

执行顺序变为：

1. 执行采集流水线
2. 对当前任务的视频文本进行分批 AI 分析
3. 写入 AI 阶段日志
4. 更新 `crawl_task.analyzed_videos`
5. 将 AI 统计摘要写入 `crawl_task.extra_params.ai_stats`

同时新增 Celery 任务：

- `app.worker.run_ai_analysis_batch`

该任务可单独触发当前任务的 AI 分析链路，便于后续拆分更细粒度的异步编排。

## 3. 质量控制与回退策略

### 3.1 质量控制

当前会检查：

- 摘要不能为空
- 摘要长度不能低于最小阈值
- 主题词数量要满足最小要求
- 主题词会去重、裁剪并补齐
- `primary_topic` 必须落在主题词集合中
- `confidence` 会被归一到 `0-1`

### 3.2 本地兜底

当出现以下情况时会自动回退：

- 未配置 `OPENAI_API_KEY`
- 上游模型请求失败
- 模型返回非 JSON
- JSON 结构通过不了质量控制

回退策略会：

- 使用标题与清洗文本拼接生成摘要
- 使用标签 + `jieba` 关键词抽取生成主题词
- 将 `model_name` 标记为 `heuristic-fallback`
- 在 `raw_response` 中记录 `used_fallback` 和失败原因

## 4. 配置项

阶段 6 新增或扩展了以下系统配置：

- `ai.summary_defaults`
- `ai.batch_defaults`
- `ai.quality_control`

对应初始化位于：

- [bootstrap.py](E:\code\fullstack\spiderbilibili\backend\app\db\bootstrap.py)

## 5. 测试与验证

本阶段新增测试：

- [test_ai_client.py](E:\code\fullstack\spiderbilibili\backend\tests\test_ai_client.py)
- [test_video_ai_service.py](E:\code\fullstack\spiderbilibili\backend\tests\test_video_ai_service.py)

并扩展了 Worker 回归测试：

- [test_worker.py](E:\code\fullstack\spiderbilibili\backend\tests\test_worker.py)

当前验证结果：

- `ruff check backend/app backend/tests` 通过
- `pytest backend/tests` 通过

## 6. 阶段 6 完成清单

已完成：

- 步骤 6.1 AI 输入输出结构设计
- 步骤 6.2 OpenAI 协议客户端封装
- 步骤 6.3 单视频分析与落库
- 步骤 6.4 任务级批量分析接入 Worker
- 步骤 6.5 AI 结果质量控制与回退

下一阶段将进入主题归类与统计分析，把 `ai_summary` 结果归并为 `topic_cluster` 与 `topic_video_relation`。
