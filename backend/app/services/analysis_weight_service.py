from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.task import (
    TaskAnalysisMetricDefinitionRead,
    TaskAnalysisMetricWeightComponentRead,
    TaskAnalysisMetricWeightConfigRead,
)

DEFAULT_NORMALIZATION_NOTE = (
    "用户填写的是相对权重，系统会自动归一化到当前指标口径后参与计算。"
)
ENGAGEMENT_NORMALIZATION_NOTE = (
    "用户填写的是相对权重，系统会自动归一化，并保持综合互动率与原口径同量级。"
)


@dataclass(frozen=True, slots=True)
class MetricComponentSpec:
    key: str
    label: str


@dataclass(frozen=True, slots=True)
class MetricSpec:
    key: str
    name: str
    category: str
    meaning: str
    interpretation: str
    limitations: str | None
    normalization_note: str | None
    components: tuple[MetricComponentSpec, ...]
    default_weights: dict[str, float]


METRIC_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="burst_score",
        name="爆发力",
        category="增长动能",
        meaning="衡量视频在当前观察窗口内的涨速和升温能力，适合追热点和判断是否继续发酵。",
        interpretation="分值越高，说明视频越可能处于快速放大阶段。",
        limitations="当视频缺少搜索基线或历史快照时，部分分量会按 0 处理。",
        normalization_note=DEFAULT_NORMALIZATION_NOTE,
        components=(
            MetricComponentSpec("search_growth", "搜索初始播放到当前播放增长率归一化"),
            MetricComponentSpec("publish_velocity", "发布以来小时均播放归一化"),
            MetricComponentSpec("history_velocity", "历史快照小时增速归一化"),
        ),
        default_weights={
            "search_growth": 0.45,
            "publish_velocity": 0.35,
            "history_velocity": 0.20,
        },
    ),
    MetricSpec(
        key="depth_score",
        name="内容深度",
        category="互动质量",
        meaning="衡量用户是否愿意进一步点赞、投币、收藏和持续互动，适合判断内容是否值得深入看。",
        interpretation="分值越高，说明内容不只是被看到，还更容易被认真消费和认可。",
        limitations="完播代理分不是官方完播率，只是用收藏、投币、评论、弹幕等信号近似。",
        normalization_note=DEFAULT_NORMALIZATION_NOTE,
        components=(
            MetricComponentSpec("like_ratio", "点赞率归一化"),
            MetricComponentSpec("coin_ratio", "投币率归一化"),
            MetricComponentSpec("favorite_ratio", "收藏率归一化"),
            MetricComponentSpec("completion_proxy_score", "完播代理分归一化"),
            MetricComponentSpec("engagement_rate", "综合互动率归一化"),
        ),
        default_weights={
            "like_ratio": 0.30,
            "coin_ratio": 0.20,
            "favorite_ratio": 0.20,
            "completion_proxy_score": 0.20,
            "engagement_rate": 0.10,
        },
    ),
    MetricSpec(
        key="community_score",
        name="社区扩散",
        category="传播扩散",
        meaning="衡量视频是否容易引发转发、讨论和弹幕互动，适合判断吃瓜传播和社区发酵能力。",
        interpretation="分值越高，说明视频越容易在社区里形成讨论和二次传播。",
        limitations="当前未采集私域传播和站外扩散，结果主要反映站内公开互动。",
        normalization_note=DEFAULT_NORMALIZATION_NOTE,
        components=(
            MetricComponentSpec("share_ratio", "分享率归一化"),
            MetricComponentSpec("reply_ratio", "评论率归一化"),
            MetricComponentSpec("danmaku_ratio", "弹幕率归一化"),
            MetricComponentSpec("engagement_rate", "综合互动率归一化"),
        ),
        default_weights={
            "share_ratio": 0.40,
            "reply_ratio": 0.25,
            "danmaku_ratio": 0.20,
            "engagement_rate": 0.15,
        },
    ),
    MetricSpec(
        key="completion_proxy_score",
        name="完播代理分",
        category="互动质量",
        meaning="用更重度的互动行为近似衡量观众是否看得更完整、更投入。",
        interpretation="分值越高，通常意味着视频更容易让观众停留并愿意给出深层反馈。",
        limitations="这不是平台后台的真实完播率，仅适合横向比较和趋势观察。",
        normalization_note=DEFAULT_NORMALIZATION_NOTE,
        components=(
            MetricComponentSpec("favorite_ratio", "收藏率"),
            MetricComponentSpec("coin_ratio", "投币率"),
            MetricComponentSpec("reply_ratio", "评论率"),
            MetricComponentSpec("danmaku_ratio", "弹幕率"),
        ),
        default_weights={
            "favorite_ratio": 0.35,
            "coin_ratio": 0.30,
            "reply_ratio": 0.20,
            "danmaku_ratio": 0.15,
        },
    ),
    MetricSpec(
        key="engagement_rate",
        name="综合互动率",
        category="基础比率",
        meaning="衡量每次播放平均能换来多少公开互动。",
        interpretation="分值越高，说明视频不只是被动曝光，而是更容易触发互动。",
        limitations="这是平台内公开互动的代理聚合结果，不包含站外传播。",
        normalization_note=ENGAGEMENT_NORMALIZATION_NOTE,
        components=(
            MetricComponentSpec("like_ratio", "点赞率"),
            MetricComponentSpec("coin_ratio", "投币率"),
            MetricComponentSpec("favorite_ratio", "收藏率"),
            MetricComponentSpec("share_ratio", "分享率"),
            MetricComponentSpec("reply_ratio", "评论率"),
            MetricComponentSpec("danmaku_ratio", "弹幕率"),
        ),
        default_weights={
            "like_ratio": 1.0,
            "coin_ratio": 1.0,
            "favorite_ratio": 1.0,
            "share_ratio": 1.0,
            "reply_ratio": 1.0,
            "danmaku_ratio": 1.0,
        },
    ),
    MetricSpec(
        key="topic_heat_index",
        name="主题热度指数",
        category="主题演化",
        meaning="用于观察某个主题在时间线上的综合热度变化。",
        interpretation="适合看某个主题是在升温、回落还是保持稳定。",
        limitations="这是分析页的主题级综合指数，不等同于 B 站官方榜单口径。",
        normalization_note=DEFAULT_NORMALIZATION_NOTE,
        components=(
            MetricComponentSpec("total_heat_score", "主题总热度"),
            MetricComponentSpec("average_burst_score", "当期平均爆发力"),
            MetricComponentSpec("average_community_score", "当期平均社区扩散"),
        ),
        default_weights={
            "total_heat_score": 1.0,
            "average_burst_score": 1.0,
            "average_community_score": 1.0,
        },
    ),
)

METRIC_SPEC_BY_KEY = {spec.key: spec for spec in METRIC_SPECS}


def get_default_metric_weight_map() -> dict[str, dict[str, float]]:
    return {
        spec.key: {key: float(value) for key, value in spec.default_weights.items()}
        for spec in METRIC_SPECS
    }


def resolve_metric_weight_map(
    extra_params: dict[str, Any] | None,
) -> dict[str, dict[str, float]]:
    defaults = get_default_metric_weight_map()
    payload = extra_params if isinstance(extra_params, dict) else {}
    persisted = payload.get("analysis_metric_weights")
    metrics = persisted.get("metrics") if isinstance(persisted, dict) else None

    resolved = get_default_metric_weight_map()
    if not isinstance(metrics, dict):
        return resolved

    for spec in METRIC_SPECS:
        current = metrics.get(spec.key)
        if not isinstance(current, dict):
            continue
        weights: dict[str, float] = {}
        for component in spec.components:
            raw_value = current.get(component.key)
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError):
                numeric_value = defaults[spec.key][component.key]
            weights[component.key] = max(numeric_value, 0.0)
        if sum(weights.values()) <= 0:
            continue
        resolved[spec.key] = weights
    return resolved


def build_metric_weight_storage_payload(
    raw_weights: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    storage: dict[str, dict[str, float]] = {}
    for spec in METRIC_SPECS:
        metric_weights = raw_weights.get(spec.key) or {}
        storage[spec.key] = {
            component.key: round(float(metric_weights.get(component.key, 0.0)), 6)
            for component in spec.components
        }
    return storage


def get_effective_metric_weights(metric_key: str, raw_weights: dict[str, float]) -> dict[str, float]:
    spec = METRIC_SPEC_BY_KEY[metric_key]
    positive_values = {
        component.key: max(float(raw_weights.get(component.key, 0.0)), 0.0)
        for component in spec.components
    }
    weight_total = sum(positive_values.values())
    if weight_total <= 0:
        return dict(spec.default_weights)

    default_total = sum(spec.default_weights.values())
    return {
        key: round((value / weight_total) * default_total, 6)
        for key, value in positive_values.items()
    }


def calculate_metric_score(
    metric_key: str,
    component_values: dict[str, float | None],
    raw_weights: dict[str, float],
) -> float:
    effective_weights = get_effective_metric_weights(metric_key, raw_weights)
    return sum(
        effective_weights[component.key] * float(component_values.get(component.key) or 0.0)
        for component in METRIC_SPEC_BY_KEY[metric_key].components
    )


def build_metric_definitions(
    raw_weight_map: dict[str, dict[str, float]],
) -> list[TaskAnalysisMetricDefinitionRead]:
    definitions: list[TaskAnalysisMetricDefinitionRead] = []
    for spec in METRIC_SPECS:
        effective_weights = get_effective_metric_weights(
            spec.key,
            raw_weight_map.get(spec.key, spec.default_weights),
        )
        definitions.append(
            TaskAnalysisMetricDefinitionRead(
                key=spec.key,
                name=spec.name,
                category=spec.category,
                meaning=spec.meaning,
                formula=_build_formula(spec, effective_weights),
                interpretation=spec.interpretation,
                limitations=spec.limitations,
            )
        )
    return definitions


def build_metric_weight_configs(
    raw_weight_map: dict[str, dict[str, float]],
) -> list[TaskAnalysisMetricWeightConfigRead]:
    configs: list[TaskAnalysisMetricWeightConfigRead] = []
    for spec in METRIC_SPECS:
        raw_weights = raw_weight_map.get(spec.key, spec.default_weights)
        effective_weights = get_effective_metric_weights(spec.key, raw_weights)
        configs.append(
            TaskAnalysisMetricWeightConfigRead(
                metric_key=spec.key,
                metric_name=spec.name,
                category=spec.category,
                normalization_note=spec.normalization_note,
                formula=_build_formula(spec, effective_weights),
                customized=any(
                    abs(raw_weights.get(component.key, 0.0) - spec.default_weights[component.key]) > 1e-9
                    for component in spec.components
                ),
                components=[
                    TaskAnalysisMetricWeightComponentRead(
                        key=component.key,
                        label=component.label,
                        weight=round(float(raw_weights.get(component.key, 0.0)), 6),
                        default_weight=round(spec.default_weights[component.key], 6),
                        effective_weight=round(effective_weights[component.key], 6),
                    )
                    for component in spec.components
                ],
            )
        )
    return configs


def get_metric_spec(metric_key: str) -> MetricSpec | None:
    return METRIC_SPEC_BY_KEY.get(metric_key)


def _build_formula(spec: MetricSpec, effective_weights: dict[str, float]) -> str:
    parts = [
        f"{effective_weights[component.key]:.2f} * {component.label}"
        for component in spec.components
    ]
    return " + ".join(parts)
