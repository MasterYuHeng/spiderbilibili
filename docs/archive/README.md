# 归档文档说明

## 1. 文档定位

`docs/archive/` 用于存放仍有追溯价值、但已经不适合作为项目级主文档继续维护的历史资料。

主文档优先级始终如下：

1. `docs/codex/` 固定协作文档
2. `docs/00-05` 项目运行期主文档
3. `docs/LOCAL_SETUP.md` / `docs/DOCKER_SETUP.md` 操作指南
4. `docs/archive/` 历史专题与过程记录

## 2. 适合归档的内容

- 单一专题的冻结规格、专题 PRD、实施计划
- 已完成阶段的专项回归记录
- 仍可能被引用，但不应继续与主文档并列竞争入口位置的历史文档

## 3. 当前归档主题

### 3.1 `keyword-synonym-expansion/`

当前包含：

- `SPEC_KEYWORD_SYNONYM_EXPANSION_PHASE0.md`
- `PRD_KEYWORD_SYNONYM_EXPANSION.md`
- `IMPLEMENTATION_PLAN_KEYWORD_SYNONYM_EXPANSION.md`
- `REGRESSION_PHASE14_KEYWORD_SYNONYM_EXPANSION.md`

使用方式：

- 项目级口径先看 `docs/00-05`
- 需要追溯该增强能力的冻结字段、详细实施步骤或回归证据时，再读取本目录

## 4. 后续归档规则

- 新专题默认先更新 `docs/00-04`，确认项目级口径稳定后，再决定是否保留专题文档。
- 专题失去主文档地位后，统一迁入 `docs/archive/<feature-slug>/`。
- 归档时优先保留原始文档内容，只在文件头补充必要的“归档说明”，避免破坏历史可追溯性。
