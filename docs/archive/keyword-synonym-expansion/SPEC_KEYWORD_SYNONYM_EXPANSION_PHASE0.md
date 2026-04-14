# 关键词同义补充功能阶段 0 冻结规格

> 归档说明：本文件已在 2026-04-14 文档治理后移入归档目录，保留为专题冻结规格参考。当前项目级主文档以 `../../00-requirement-interpretation.md`、`../../01-prd.md`、`../../03-implementation-roadmap.md`、`../../04-current-state.md` 为准。

## 1. 文档目的

本文件用于冻结“关键词同义补充”功能的字段命名、状态枚举、`extra_params` 结构、视频结果字段和关键口径。  
从本文件落地后，后续数据库、后端接口、前端页面、导出和测试都必须以本文件为唯一准绳。

## 2. 不变的核心架构

以下核心架构保持不变：

- 用户仍然只创建一个任务
- 任务主关键词仍然使用原始关键词
- 扩词只增强搜索抓取，不拆成多个分析任务
- 主题分析、热门 UP 主分析、任务报告仍然是一套
- 原有任务状态机、执行链路、分析链路不改主结构

## 3. 冻结命名

## 3.1 创建任务请求字段

新增字段固定为：

- `enable_keyword_synonym_expansion: boolean | null`
- `keyword_synonym_count: 1 | 2 | 3 | 5 | null`

解释：

- `enable_keyword_synonym_expansion = true` 表示开启扩词
- `keyword_synonym_count` 表示期望补充的同义词个数

规则：

- 当 `crawl_mode != "keyword"` 时，这两个字段必须被规范化为：
  - `enable_keyword_synonym_expansion = false`
  - `keyword_synonym_count = null`
- 当 `enable_keyword_synonym_expansion = false` 时：
  - `keyword_synonym_count = null`

## 3.2 视频结果字段

任务视频结果必须新增并统一使用以下字段：

- `matched_keywords: string[]`
- `primary_matched_keyword: string | null`
- `keyword_match_count: number`

字段含义：

- `matched_keywords`
  - 当前视频在搜索阶段命中的全部搜索词
  - 包括原始关键词和扩展关键词
- `primary_matched_keyword`
  - 当前视频的主命中词
  - 优先取原始关键词；若未命中原始关键词，则取最佳命中词
- `keyword_match_count`
  - 当前视频命中的搜索词数量
  - 计算方式为 `matched_keywords.length`

## 4. 任务主关键词口径

- `crawl_task.keyword` 始终保存原始关键词
- 不把同义词写入 `crawl_task.keyword`
- 任务列表、任务详情标题、工作区上下文、重试入口、报告标题都继续显示原始关键词

示例：

- 用户输入：`和平精英`
- 扩词结果：`吃鸡`
- `crawl_task.keyword` 仍然是：`和平精英`

## 5. 扩词状态枚举

扩词状态固定为以下 5 个值：

- `skipped`
- `pending`
- `success`
- `fallback`
- `failed`

状态定义：

- `skipped`
  - 当前任务未启用扩词
- `pending`
  - 任务已启用扩词，但尚未实际执行扩词
- `success`
  - 扩词成功，且生成了至少一个合法同义词
- `fallback`
  - 扩词执行过，但因为 AI 不可用、AI 返回空结果、结果清洗后为空等原因，回退为仅原始关键词抓取
- `failed`
  - 仅用于记录扩词阶段出现了明确错误且未完成标准扩词结果写入的异常状态
  - 该状态本身不能阻断主任务，主任务仍需回退到原关键词抓取

## 6. extra_params 冻结结构

`extra_params` 中与本功能相关的结构固定如下。

```json
{
  "task_options": {
    "crawl_mode": "keyword",
    "search_scope": "site",
    "partition_tid": null,
    "partition_name": null,
    "published_within_days": null,
    "requested_video_limit": 50,
    "max_pages": 5,
    "hot_author_total_count": 5,
    "topic_hot_author_count": 1,
    "hot_author_video_limit": 10,
    "hot_author_summary_basis": "time",
    "enable_proxy": false,
    "source_ip_strategy": "local_sleep",
    "enable_keyword_synonym_expansion": true,
    "keyword_synonym_count": 2
  },
  "keyword_expansion": {
    "source_keyword": "和平精英",
    "enabled": true,
    "requested_synonym_count": 2,
    "generated_synonyms": ["吃鸡", "鸡友"],
    "expanded_keywords": ["和平精英", "吃鸡", "鸡友"],
    "status": "success",
    "model_name": "gpt-4.1-mini",
    "error_message": null,
    "generated_at": "2026-04-13T12:00:00Z"
  },
  "crawl_stats": {
    "search_keyword_count": 3,
    "expanded_keyword_count": 2,
    "search_keywords_used": ["和平精英", "吃鸡", "鸡友"]
  }
}
```

## 6.1 task_options 固定字段

新增以下字段：

- `enable_keyword_synonym_expansion`
- `keyword_synonym_count`

规则：

- 必须进入 `task_options`
- 不允许单独散落到别的一级键中

## 6.2 keyword_expansion 固定字段

固定字段如下：

- `source_keyword: string`
- `enabled: boolean`
- `requested_synonym_count: number`
- `generated_synonyms: string[]`
- `expanded_keywords: string[]`
- `status: "skipped" | "pending" | "success" | "fallback" | "failed"`
- `model_name: string | null`
- `error_message: string | null`
- `generated_at: string | null`

字段规则：

- `source_keyword`
  - 永远等于原始关键词
- `generated_synonyms`
  - 只包含新生成的同义词，不包含原始关键词
- `expanded_keywords`
  - 必须总是包含原始关键词
  - 顺序固定为：原始关键词在前，扩词结果在后
- `requested_synonym_count`
  - 永远记录用户提交的目标扩词个数
- `model_name`
  - 记录实际产出扩词结果的模型名
  - fallback 或 skipped 时可为 `null`
- `generated_at`
  - 仅在执行过扩词动作后填写

## 6.3 crawl_stats 固定字段

与扩词相关的抓取统计固定新增：

- `search_keyword_count: number`
- `expanded_keyword_count: number`
- `search_keywords_used: string[]`

字段规则：

- `search_keyword_count = search_keywords_used.length`
- `expanded_keyword_count = generated_synonyms.length`
- `search_keywords_used` 必须与实际执行抓取的搜索词一致

## 7. 状态与回退规则

## 7.1 创建任务时

若未启用扩词：

- `keyword_expansion.status = "skipped"`
- `generated_synonyms = []`
- `expanded_keywords = [原始关键词]`

若启用扩词：

- `keyword_expansion.status = "pending"`
- `generated_synonyms = []`
- `expanded_keywords = [原始关键词]`

## 7.2 执行扩词时

若 AI 成功返回合法同义词：

- `status = "success"`
- `generated_synonyms` 为清洗后的同义词
- `expanded_keywords = [原始关键词, ...generated_synonyms]`

若 AI 返回空结果、格式错误、不可用，或清洗后无合法结果：

- `status = "fallback"`
- `generated_synonyms = []`
- `expanded_keywords = [原始关键词]`
- `error_message` 填充原因

若执行扩词时出现明确异常且被捕获记录：

- `status = "failed"`
- 但任务主链路仍需自动回退为 `expanded_keywords = [原始关键词]`

## 8. 重试与恢复口径

## 8.1 resume

同一任务 `resume` 时：

- 直接复用该任务已有的 `keyword_expansion`
- 不重新调用扩词模型

## 8.2 retry

克隆重试任务时：

- 复制原任务的 `task_options`
- 若原任务 `keyword_expansion.status = "success"`：
  - 新任务复制整份 `keyword_expansion`
- 若原任务状态为 `fallback`、`failed`、`pending`：
  - 新任务重置为待执行扩词
  - 即：
    - `generated_synonyms = []`
    - `expanded_keywords = [原始关键词]`
    - `status = "pending"`
    - `model_name = null`
    - `error_message = null`
    - `generated_at = null`

## 9. 多关键词抓取与视频命中规则

## 9.1 最终搜索词列表

最终搜索词列表固定使用：

- `expanded_keywords`

执行顺序固定为：

1. 原始关键词
2. 扩展关键词，按 `generated_synonyms` 顺序依次追加

## 9.2 多视频去重规则

若多个搜索词命中同一 `bvid`：

- 保留一条候选视频
- `matched_keywords` 合并去重
- `keyword_match_count = matched_keywords.length`
- `primary_matched_keyword` 规则：
  - 若命中原始关键词，则优先为原始关键词
  - 否则取最佳搜索结果名次对应的命中词

## 10. 评分口径

评分口径固定如下：

- `VideoScoreService` 仍围绕原始关键词 `task.keyword` 打分
- 不因同义词命中而切换评分主词

也就是说：

- 扩词增强的是召回
- 评分口径保持原有任务主题中心

## 11. 前端展示口径

## 11.1 创建页

固定字段：

- `enable_keyword_synonym_expansion`
- `keyword_synonym_count`

固定行为：

- 仅关键词模式展示
- 默认关闭
- 默认数量为 `1`

## 11.2 详情页

必须展示：

- 原始关键词
- 扩词状态
- 生成同义词
- 最终搜索词
- 失败回退说明

## 11.3 视频结果页

必须展示：

- `matched_keywords`
- `primary_matched_keyword`
- `keyword_match_count`

## 11.4 报告页

必须展示搜索口径说明：

- 原始关键词
- 实际搜索词列表
- 扩词状态

## 12. 不允许的偏离

后续开发中，不允许出现以下偏离：

- 把同义词写进 `crawl_task.keyword`
- 再新增第二套扩词状态命名
- 再新增第二套 `extra_params.keyword_expansion` 字段结构
- 只在日志里记录扩词，不做持久化
- 视频结果页没有视频级命中来源字段
- 为同义词拆分多个任务或多个分析报告

## 13. 阶段 0 完成标准

满足以下条件，即视为阶段 0 完成：

- 字段命名已冻结
- 状态枚举已冻结
- `extra_params` 结构已冻结
- 视频结果字段已冻结
- PRD 和实施计划已回写并统一引用本规格
