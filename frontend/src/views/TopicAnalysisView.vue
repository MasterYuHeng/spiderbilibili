<template>
  <div class="page-stack">
    <section class="page-hero">
      <div>
        <h3>主题分析总览</h3>
      </div>
      <div class="page-hero__aside">
        <span>当前任务范围</span>
        <strong>{{ taskScopeLabel }}</strong>
      </div>
    </section>

    <TaskLifecycleNotice
      v-if="taskProgress"
      :status="taskProgress.status"
      :error-message="taskProgress.error_message"
      :extra-params="taskProgress.extra_params"
      :latest-log-message="taskProgress.latest_log?.message ?? null"
      :current-stage="taskProgress.current_stage"
    />

    <section v-if="analysis" class="stats-grid stats-grid--wide">
      <StatCard label="总视频数" :value="formatNumber(analysis.summary.total_videos)" />
      <StatCard label="平均播放量" :value="formatCompactNumber(analysis.summary.average_view_count)" />
      <StatCard label="平均互动率" :value="formatPercent(analysis.summary.average_engagement_rate, 2)" />
      <StatCard label="高爆发样本" :value="formatNumber(analysis.advanced.explosive_videos.length)" />
      <StatCard label="深度样本" :value="formatNumber(analysis.advanced.deep_videos.length)" />
      <StatCard label="有历史快照的视频" :value="formatNumber(historyCoveredCount)" />
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>指标说明与计算口径</h4>
        </div>
      </div>
      <div v-if="metricDefinitions.length" class="metric-grid">
        <article
          v-for="definition in metricDefinitions"
          :key="definition.key"
          class="metric-card"
        >
          <div class="metric-card__head">
            <strong>{{ definition.name }}</strong>
            <span>{{ definition.category }}</span>
          </div>
          <div class="metric-card__formula">{{ definition.formula }}</div>
          <div class="metric-card__line" :title="definition.meaning">
            <span>含义</span>
            <small>{{ compactMetricText(definition.meaning) }}</small>
          </div>
          <div class="metric-card__line" :title="definition.interpretation">
            <span>解读</span>
            <small>{{ compactMetricText(definition.interpretation) }}</small>
          </div>
          <div v-if="definition.limitations" class="metric-card__line" :title="definition.limitations">
            <span>边界</span>
            <small>{{ compactMetricText(definition.limitations) }}</small>
          </div>
        </article>
      </div>
      <EmptyState
        v-else
        title="指标说明尚未生成"
        description="分析完成后，这里会展示当前页面里主要指标的含义和计算口径。"
      />
    </section>

    <section class="topic-grid">
      <article class="panel-section">
        <div class="panel-section__head">
          <div>
            <h4>主题占比图</h4>
          </div>
          <div class="topic-actions">
            <el-button v-if="selectedTopicName" @click="handleClearTopicSelection">清空高亮</el-button>
            <el-button :type="compareMode ? 'primary' : 'default'" plain @click="enableCompareMode">对比</el-button>
          </div>
        </div>
        <TopicDonutChart
          :topics="analysis?.topics ?? []"
          :active-topic="selectedTopicName || null"
          @select="handleSelectTopic"
        />
      </article>

      <article class="panel-section">
        <div class="panel-section__head">
          <div>
            <h4>主题热度排行</h4>
          </div>
        </div>
        <TopicHeatBarChart
          :topics="analysis?.topics ?? []"
          :active-topic="selectedTopicName || null"
          @select="handleSelectTopic"
        />
      </article>
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>主题分析总表</h4>
        </div>
        <div class="toolbar__actions">
          <el-select v-model="exportDataset" class="toolbar__field">
            <el-option label="主题结果" value="topics" />
            <el-option label="摘要结果" value="summaries" />
          </el-select>
          <el-select v-model="exportFormat" class="toolbar__field">
            <el-option label="Excel" value="excel" />
            <el-option label="CSV" value="csv" />
            <el-option label="JSON" value="json" />
          </el-select>
          <el-button :loading="exporting" @click="handleExport">导出当前结果</el-button>
        </div>
      </div>

      <el-table
        v-loading="loading"
        :data="filteredTopics"
        row-key="id"
        class="app-table"
        @row-click="handleRowClick"
      >
        <el-table-column label="主题" min-width="180">
          <template #default="{ row }">
            <div class="task-title-cell">
              <strong>{{ row.name }}</strong>
              <small>{{ row.keywords.join(' / ') || '暂无关键词' }}</small>
            </div>
          </template>
        </el-table-column>

        <el-table-column label="视频占比" width="120">
          <template #default="{ row }">
            {{ formatPercent(row.video_ratio) }}
          </template>
        </el-table-column>

        <el-table-column label="总热度" width="120">
          <template #default="{ row }">
            {{ formatScore(row.total_heat_score) }}
          </template>
        </el-table-column>

        <el-table-column label="爆发力" width="120">
          <template #default="{ row }">
            {{ formatScore(topicInsightByName[row.name]?.average_burst_score, 2) }}
          </template>
        </el-table-column>

        <el-table-column label="内容深度" width="120">
          <template #default="{ row }">
            {{ formatScore(topicInsightByName[row.name]?.average_depth_score, 2) }}
          </template>
        </el-table-column>

        <el-table-column label="社区扩散" width="140">
          <template #default="{ row }">
            {{ formatScore(topicInsightByName[row.name]?.average_community_score, 2) }}
          </template>
        </el-table-column>

        <el-table-column label="代表视频" min-width="220">
          <template #default="{ row }">
            <a
              v-if="row.representative_video"
              :href="row.representative_video.url"
              target="_blank"
              rel="noreferrer"
            >
              {{ row.representative_video.title }}
            </a>
            <span v-else>--</span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="topic-grid">
      <article class="panel-section">
        <div class="panel-section__head">
          <div v-if="compareMode">
            <h4>主题对比洞察</h4>
          </div>
          <div v-else>
            <h4>主题聚焦</h4>
          </div>
        </div>
        <div v-if="compareMode" class="insight-summary">
          <h5>{{ comparisonHeadline }}</h5>
          <InsightText tag="p" :text="comparisonNarrative" />
          <div class="signal-grid">
            <div class="signal-item">
              <span>对比主题数</span>
              <strong>{{ comparisonSeries.length }}</strong>
            </div>
            <div class="signal-item">
              <span>时间分段数</span>
              <strong>{{ comparisonBuckets.length }}</strong>
            </div>
            <div class="signal-item">
              <span>领跑切换次数</span>
              <strong>{{ comparisonLeaderSwitchCount }}</strong>
            </div>
            <div class="signal-item">
              <span>样本视频数</span>
              <strong>{{ filteredComparisonVideos.length }}</strong>
            </div>
          </div>
          <div v-if="comparisonTopTopicLabels.length" class="tag-cluster">
            <el-tag
              v-for="label in comparisonTopTopicLabels"
              :key="label"
              type="info"
              effect="plain"
            >
              {{ label }}
            </el-tag>
          </div>
          <ul class="insight-list">
            <InsightText
              v-for="point in comparisonSummaryPoints"
              :key="point"
              tag="li"
              :text="point"
            />
          </ul>
        </div>
        <EmptyState
          v-else-if="!selectedTopic && !selectedTopicInsight"
          title="请选择一个主题"
          description="点击上方图表或总表中的主题后，这里会显示当前主题的聚焦分析。"
        />
        <div v-else class="focus-card">
          <div class="focus-card__main">
            <h5>{{ selectedTopic?.name || selectedTopicInsight?.topic_name }}</h5>
            <InsightText
              tag="p"
              :text="selectedTopicInsight?.summary || selectedTopic?.description || '该主题已进入当前分析视野，但暂时缺少更详细的摘要说明。'"
            />
            <div class="tag-cluster">
              <el-tag
                v-for="keyword in selectedTopic?.keywords ?? []"
                :key="keyword"
                type="info"
                effect="plain"
              >
                {{ keyword }}
              </el-tag>
            </div>
            <div class="signal-grid">
              <div class="signal-item">
                <span>爆发力</span>
                <strong>{{ formatScore(selectedTopicInsight?.average_burst_score, 2) }}</strong>
              </div>
              <div class="signal-item">
                <span>内容深度</span>
                <strong>{{ formatScore(selectedTopicInsight?.average_depth_score, 2) }}</strong>
              </div>
              <div class="signal-item">
                <span>社区扩散</span>
                <strong>{{ formatScore(selectedTopicInsight?.average_community_score, 2) }}</strong>
              </div>
              <div class="signal-item">
                <span>历史覆盖率</span>
                <strong>{{ formatPercent(selectedTopicInsight?.historical_coverage_ratio, 1) }}</strong>
              </div>
            </div>
          </div>
          <div class="focus-card__aside">
            <span>主题代表视频</span>
            <strong>
              {{
                selectedTopic?.representative_video?.bvid ||
                selectedTopicInsight?.representative_video?.bvid ||
                '--'
              }}
            </strong>
            <a
              v-if="selectedTopic?.representative_video || selectedTopicInsight?.representative_video"
              :href="
                selectedTopic?.representative_video?.url ||
                selectedTopicInsight?.representative_video?.url ||
                '#'
              "
              target="_blank"
              rel="noreferrer"
            >
              打开代表视频
            </a>
          </div>
        </div>
      </article>

      <article class="panel-section">
        <div class="panel-section__head">
          <div v-if="compareMode">
            <h4>主题领跑切换</h4>
            <p>按时间阶段拆解每一段由谁领跑，以及它在那一段为什么更热。</p>
          </div>
          <div v-else>
            <h4>最新热点主题</h4>
            <p>综合主题热度、近期爆发和社区扩散后，优先给出当前最值得关注的热点主题。</p>
          </div>
        </div>
        <div v-if="compareMode && comparisonLeaderPhases.length" class="phase-list">
          <article
            v-for="phase in comparisonLeaderPhases"
            :key="`${phase.topic_name}-${phase.start_bucket}-${phase.end_bucket}`"
            class="phase-card"
          >
            <div class="phase-card__head">
              <strong>{{ phase.topic_name }}</strong>
              <el-tag size="small" effect="plain">{{ formatPhaseRange(phase.start_bucket, phase.end_bucket) }}</el-tag>
            </div>
            <p>
              在这段时间里连续领跑 {{ phase.bucket_count }} 个时间段，峰值出现在
              {{ phase.peak_bucket }}，热度指数 {{ formatScore(phase.peak_value, 2) }}。
            </p>
          </article>
        </div>
        <EmptyState
          v-else-if="compareMode"
          title="暂无主题领跑阶段"
          description="当前筛选条件下还没有足够的时间切片来识别各主题的阶段性领跑变化。"
        />
        <div v-else-if="latestHotTopic" class="insight-summary">
          <h5>{{ latestHotTopic.topic_name }}</h5>
          <InsightText tag="p" :text="latestHotTopicSummary" />
          <ul class="insight-list">
            <InsightText
              v-for="point in analysis?.advanced.latest_hot_topic.supporting_points ?? []"
              :key="point"
              tag="li"
              :text="point"
            />
          </ul>
        </div>
        <EmptyState
          v-else
          title="热点主题尚未生成"
          description="当前任务完成主题分析后，这里会汇总一个最新热点主题。"
        />
      </article>
    </section>
    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>发布时间窗口</h4>
          <p>下面三块时间演化图都会受这一组时间区间和粒度控制，方便按阶段观察主题变化。</p>
        </div>
      </div>
      <div class="timeline-toolbar">
        <el-date-picker
          v-model="publishedWindow.start"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="起始日期"
          class="toolbar__field"
        />
        <el-date-picker
          v-model="publishedWindow.end"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="截止日期"
          class="toolbar__field"
        />
        <el-select v-model="publishedWindow.granularity" class="toolbar__field">
          <el-option label="按天" value="day" />
          <el-option label="按周" value="week" />
          <el-option label="按月" value="month" />
        </el-select>
      </div>
    </section>

    <section class="topic-grid">
      <article class="panel-section">
        <div class="panel-section__head">
          <div v-if="compareMode">
            <h4>主题热度对比</h4>
            <p>在同一张图里叠加所有主题的热度指数变化，直接观察哪一段时间由谁主导。</p>
          </div>
          <div v-else>
            <h4>热点演化曲线</h4>
            <p>观察当前主题在不同发布时间窗口里的热度指数变化，判断是持续升温、回落还是稳定。</p>
          </div>
          <span
            class="trend-pill"
            :class="compareMode ? 'trend-pill--compare' : `trend-pill--${selectedTrendDirection}`"
          >
            {{ compareMode ? comparisonTrendLabel : trendDirectionLabel(selectedTrendDirection) }}
          </span>
        </div>
        <TopicEvolutionComparisonChart
          v-if="compareMode && comparisonSeries.length && comparisonBuckets.length"
          :buckets="comparisonBuckets"
          :series="comparisonSeries"
        />
        <TopicEvolutionChart v-else-if="evolutionChartPoints.length" :points="evolutionChartPoints" />
        <EmptyState
          v-else
          :title="compareMode ? '暂无对比热度数据' : '暂无时间演化数据'"
          :description="
            compareMode
              ? '当前筛选条件下没有足够的发布时间样本来绘制多主题热度对比曲线。'
              : '当前筛选条件下没有足够的发布时间样本来绘制主题演化曲线。'
          "
        />
      </article>

      <article class="panel-section">
        <div class="panel-section__head">
          <div>
          <h4>内容深度可视化</h4>
          <p>按发布时间观察内容深度、完播代理分和点赞率变化，判断主题内容是否越来越耐看。</p>
          </div>
        </div>
        <DepthTrendChart v-if="depthChartPoints.length" :points="depthChartPoints" />
        <EmptyState
          v-else
          title="暂无深度趋势数据"
          description="当前筛选条件下没有足够样本来绘制内容深度趋势。"
        />
      </article>
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>社区扩散可视化</h4>
          <p>按发布时间观察扩散分、分享率和评论率变化，判断主题是否更容易在社区里发酵。</p>
        </div>
      </div>
      <CommunityTrendChart v-if="communityChartPoints.length" :points="communityChartPoints" />
      <EmptyState
        v-else
        title="暂无扩散趋势数据"
        description="当前筛选条件下没有足够样本来绘制社区扩散趋势。"
      />
    </section>

    <section class="topic-grid">
      <article class="panel-section">
        <div class="panel-section__head">
          <div>
          <h4>爆发视频历史曲线</h4>
          <p>
            结合搜索初始值、当前快照和跨任务历史快照，观察爆发视频的播放、点赞和分享变化过程。
          </p>
          </div>
        </div>
        <div class="timeline-toolbar">
          <el-date-picker
            v-model="historyWindow.start"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
          placeholder="起始时间"
            class="toolbar__field"
          />
          <el-date-picker
            v-model="historyWindow.end"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm:ss"
          placeholder="截止时间"
            class="toolbar__field"
          />
          <el-select v-model="historyWindow.granularity" class="toolbar__field">
          <el-option label="原始快照" value="raw" />
            <el-option label="按天" value="day" />
            <el-option label="按周" value="week" />
          </el-select>
        </div>
        <VideoHistoryChart v-if="historyChartPoints.length" :points="historyChartPoints" />
        <EmptyState
          v-else
        title="暂无爆发视频历史"
        description="当前还没有可用于展示增长曲线的爆发视频样本，或当前时间窗口内没有数据。"
        />
        <div v-if="analysis?.advanced.explosive_videos.length" class="mini-list">
          <button
            v-for="video in analysis.advanced.explosive_videos.slice(0, 5)"
            :key="video.video_id"
            type="button"
            class="mini-list__item mini-list__item--button"
            :class="{ 'is-active': video.video_id === selectedExplosiveVideoId }"
            @click="selectedExplosiveVideoId = video.video_id"
          >
            <span>{{ video.title }}</span>
            <small>
              爆发力 {{ formatScore(video.burst_score, 2) }} / 历史快照 {{ video.historical_snapshot_count }}
            </small>
          </button>
        </div>
        <div class="chart-note">
          自发布以来的完整播放/点赞时间序列当前无法稳定采集，本图使用搜索基线与历史快照代理展示。
        </div>
      </article>

      <article class="panel-section">
        <div class="panel-section__head">
          <div>
            <h4>爆发力分析摘要</h4>
            <p>用最适合追新的视频样本，快速看当下哪些内容正在高速放大。</p>
          </div>
        </div>
        <div v-if="selectedExplosiveVideo" class="insight-summary">
          <h5>{{ selectedExplosiveVideo.title }}</h5>
          <p>
            当前视频爆发力为 {{ formatScore(selectedExplosiveVideo.burst_score, 2) }}，搜索到当前播放增长率为
            {{ formatPercent(selectedExplosiveVideo.search_to_current_view_growth_ratio, 2) }}，发布以来小时均播放为
            {{ formatCompactNumber(selectedExplosiveVideo.views_per_hour_since_publish) }}。
          </p>
          <ul class="insight-list">
            <li>当前主题：{{ selectedExplosiveVideo.topic_name || '未归类主题' }}</li>
            <li>历史快照数：{{ formatNumber(selectedExplosiveVideo.historical_snapshot_count) }}</li>
            <li>历史小时增量：{{ formatCompactNumber(selectedExplosiveVideo.historical_view_velocity_per_hour) }}</li>
          </ul>
        </div>
        <EmptyState
          v-else
        title="暂无爆发视频摘要"
        description="当前任务完成爆发力分析后，这里会展示高爆发视频的重点解读。"
        />
      </article>
    </section>

    <section class="insight-grid insight-grid--triple">
      <article class="panel-section">
        <div class="panel-section__head">
          <div>
          <h4>爆发力排行</h4>
            <p>看哪些主题和视频正在快速放大播放表现。</p>
          </div>
        </div>
        <div v-if="analysis?.advanced.momentum_topics.length" class="mini-list">
          <article
            v-for="topic in analysis.advanced.momentum_topics.slice(0, 5)"
            :key="topic.topic_id"
            class="mini-list__item"
          >
            <button type="button" class="analysis-link-button" @click="focusTopic(topic.topic_name)">
              {{ topic.topic_name }}
            </button>
            <span>爆发力 {{ formatScore(topic.average_burst_score, 2) }}</span>
            <small>均播 {{ formatCompactNumber(topic.average_view_count) }}</small>
          </article>
        </div>
        <div v-if="analysis?.advanced.explosive_videos.length" class="insight-sublist">
          <strong>最强样本</strong>
          <article
            v-for="video in analysis.advanced.explosive_videos.slice(0, 3)"
            :key="video.video_id"
            class="mini-list__item"
          >
            <a :href="video.url" target="_blank" rel="noreferrer">{{ video.title }}</a>
            <small>爆发力 {{ formatScore(video.burst_score, 2) }}</small>
          </article>
        </div>
      </article>

      <article class="panel-section">
        <div class="panel-section__head">
          <div>
          <h4>内容深度排行</h4>
            <p>重点参考三连率、完播代理分和综合互动质量。</p>
          </div>
        </div>
        <div v-if="analysis?.advanced.depth_topics.length" class="mini-list">
          <article
            v-for="topic in analysis.advanced.depth_topics.slice(0, 5)"
            :key="topic.topic_id"
            class="mini-list__item"
          >
            <button type="button" class="analysis-link-button" @click="focusTopic(topic.topic_name)">
              {{ topic.topic_name }}
            </button>
            <span>深度 {{ formatScore(topic.average_depth_score, 2) }}</span>
            <small>点赞率 {{ formatPercent(topic.average_like_view_ratio, 2) }}</small>
          </article>
        </div>
        <div v-if="analysis?.advanced.deep_videos.length" class="insight-sublist">
          <strong>高深度样本</strong>
          <article
            v-for="video in analysis.advanced.deep_videos.slice(0, 3)"
            :key="video.video_id"
            class="mini-list__item"
          >
            <a :href="video.url" target="_blank" rel="noreferrer">{{ video.title }}</a>
            <small>深度 {{ formatScore(video.depth_score, 2) }}</small>
          </article>
        </div>
      </article>

      <article class="panel-section">
        <div class="panel-section__head">
          <div>
          <h4>社区扩散排行</h4>
            <p>重点看分享率、评论率和弹幕密度这些扩散信号。</p>
          </div>
        </div>
        <div v-if="analysis?.advanced.community_topics.length" class="mini-list">
          <article
            v-for="topic in analysis.advanced.community_topics.slice(0, 5)"
            :key="topic.topic_id"
            class="mini-list__item"
          >
            <button type="button" class="analysis-link-button" @click="focusTopic(topic.topic_name)">
              {{ topic.topic_name }}
            </button>
            <span>扩散 {{ formatScore(topic.average_community_score, 2) }}</span>
            <small>分享率 {{ formatPercent(topic.average_share_rate, 2) }}</small>
          </article>
        </div>
        <div v-if="analysis?.advanced.community_videos.length" class="insight-sublist">
          <strong>高扩散样本</strong>
          <article
            v-for="video in analysis.advanced.community_videos.slice(0, 3)"
            :key="video.video_id"
            class="mini-list__item"
          >
            <a :href="video.url" target="_blank" rel="noreferrer">{{ video.title }}</a>
            <small>扩散 {{ formatScore(video.community_score, 2) }}</small>
          </article>
        </div>
      </article>
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>推荐视频</h4>
          <p>直接给出当前搜索结果里最值得先看的视频，以及最新热点主题下的重点样本。</p>
        </div>
      </div>
      <div v-if="analysis?.advanced.recommendations.length" class="recommendation-grid">
        <article
          v-for="recommendation in analysis.advanced.recommendations"
          :key="recommendation.key"
          class="recommendation-card"
        >
          <h5>{{ recommendation.title }}</h5>
          <p>{{ recommendation.description || '面向当前任务的自动推荐结果。' }}</p>
          <div class="mini-list">
            <article
              v-for="video in recommendation.videos.slice(0, 4)"
              :key="video.video_id"
              class="mini-list__item"
            >
              <a :href="video.url" target="_blank" rel="noreferrer">{{ video.title }}</a>
              <small>{{ video.topic_name || '未归类主题' }} / 综合 {{ formatScore(video.composite_score) }}</small>
            </article>
          </div>
        </article>
      </div>
      <EmptyState
        v-else
        title="推荐列表暂未生成"
        description="分析完成后，这里会给出当前搜索结果和热点主题下的推荐视频。"
      />
    </section>

    <section class="panel-section">
      <div class="panel-section__head">
        <div>
          <h4>分析说明</h4>
          <p>这些说明用于帮助理解当前数据边界、快照覆盖情况和分析解读方式。</p>
        </div>
      </div>
      <ul class="insight-list">
        <li v-for="note in analysis?.advanced.data_notes ?? []" :key="note">
          {{ note }}
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ElMessage } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getErrorMessage, isRequestCanceled } from '@/api/client'
import { exportTaskResults, getTaskAnalysis, getTaskProgress } from '@/api/tasks'
import type {
  ExportDataset,
  ExportFormat,
  TaskAnalysisMetricDefinition,
  TaskAnalysisPayload,
  TaskAnalysisTopicInsight,
  TaskAnalysisVideoHistoryPoint,
  TaskAnalysisVideoInsight,
  TaskProgressPayload,
  TaskTopic,
} from '@/api/types'
import CommunityTrendChart from '@/components/charts/CommunityTrendChart.vue'
import DepthTrendChart from '@/components/charts/DepthTrendChart.vue'
import TopicDonutChart from '@/components/charts/TopicDonutChart.vue'
import TopicEvolutionComparisonChart from '@/components/charts/TopicEvolutionComparisonChart.vue'
import TopicEvolutionChart from '@/components/charts/TopicEvolutionChart.vue'
import TopicHeatBarChart from '@/components/charts/TopicHeatBarChart.vue'
import VideoHistoryChart from '@/components/charts/VideoHistoryChart.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import InsightText from '@/components/common/InsightText.vue'
import StatCard from '@/components/common/StatCard.vue'
import TaskLifecycleNotice from '@/components/tasks/TaskLifecycleNotice.vue'
import { useTaskWorkspaceStore } from '@/stores/taskWorkspace'
import {
  formatCompactNumber,
  formatNumber,
  formatPercent,
  formatScore,
  triggerBlobDownload,
} from '@/utils/format'
import { isActiveTaskStatus } from '@/utils/taskStatus'

type PublishedGranularity = 'day' | 'week' | 'month'
type HistoryGranularity = 'raw' | 'day' | 'week'

interface TopicEvolutionChartPoint {
  bucket: string
  topic_heat_index: number
  total_heat_score: number
  video_count: number
}

interface TopicComparisonSeries {
  topic_name: string
  values: number[]
  total_heat_index: number
  peak_bucket: string
  peak_value: number
  dominant_bucket_count: number
  direction: 'rising' | 'cooling' | 'stable'
}

interface TopicLeaderPoint {
  bucket: string
  topic_name: string
  value: number
}

interface TopicLeaderPhase {
  topic_name: string
  start_bucket: string
  end_bucket: string
  bucket_count: number
  peak_bucket: string
  peak_value: number
}

interface DepthChartPoint {
  bucket: string
  average_depth_score: number
  average_completion_proxy_score: number
  average_like_view_ratio: number
}

interface CommunityChartPoint {
  bucket: string
  average_community_score: number
  average_share_view_ratio: number
  average_reply_view_ratio: number
}

interface HistoryChartPoint {
  label: string
  view_count: number
  like_count: number
  share_count: number
}

const route = useRoute()
const workspaceStore = useTaskWorkspaceStore()

const taskId = computed(() => String(route.params.taskId))
const analysis = ref<TaskAnalysisPayload | null>(null)
const taskProgress = ref<TaskProgressPayload | null>(null)
const loading = ref(false)
const exporting = ref(false)
const selectedTopicName = ref('')
const compareMode = ref(false)
const selectedExplosiveVideoId = ref('')
const latestProgressLogId = ref('')

const publishedWindow = reactive<{ start: string; end: string; granularity: PublishedGranularity }>({
  start: '',
  end: '',
  granularity: 'day',
})

const historyWindow = reactive<{ start: string; end: string; granularity: HistoryGranularity }>({
  start: '',
  end: '',
  granularity: 'raw',
})

let timer: number | null = null
let pollInFlight = false
let progressController: AbortController | null = null
let analysisController: AbortController | null = null

const exportDataset = computed({
  get: () =>
    (workspaceStore.exportDataset === 'videos' ? 'topics' : workspaceStore.exportDataset) as ExportDataset,
  set: (value: ExportDataset) => {
    workspaceStore.setExportDataset(value)
  },
})

const exportFormat = computed({
  get: () => workspaceStore.exportFormat as ExportFormat,
  set: (value: ExportFormat) => {
    workspaceStore.setExportFormat(value)
  },
})

const fallbackTopicInsights = computed<TaskAnalysisTopicInsight[]>(() => {
  const items = [
    ...(analysis.value?.advanced.momentum_topics ?? []),
    ...(analysis.value?.advanced.depth_topics ?? []),
    ...(analysis.value?.advanced.community_topics ?? []),
  ]
  const map = new Map<string, TaskAnalysisTopicInsight>()
  items.forEach((item) => {
    if (!map.has(item.topic_id)) {
      map.set(item.topic_id, item)
    }
  })
  return Array.from(map.values())
})

const allTopicInsights = computed<TaskAnalysisTopicInsight[]>(() => {
  const items = analysis.value?.advanced.topic_insights ?? []
  return items.length ? items : fallbackTopicInsights.value
})

const allVideoInsights = computed<TaskAnalysisVideoInsight[]>(() => {
  const items = analysis.value?.advanced.video_insights ?? []
  if (items.length) {
    return items
  }

  const fallback = [
    ...(analysis.value?.advanced.explosive_videos ?? []),
    ...(analysis.value?.advanced.deep_videos ?? []),
    ...(analysis.value?.advanced.community_videos ?? []),
  ]
  const map = new Map<string, TaskAnalysisVideoInsight>()
  fallback.forEach((item) => {
    if (!map.has(item.video_id)) {
      map.set(item.video_id, item)
    }
  })
  return Array.from(map.values())
})

const metricDefinitions = computed<TaskAnalysisMetricDefinition[]>(() => {
  return analysis.value?.advanced.metric_definitions ?? []
})

const topicInsightByName = computed<Record<string, TaskAnalysisTopicInsight>>(() => {
  return allTopicInsights.value.reduce<Record<string, TaskAnalysisTopicInsight>>((accumulator, item) => {
    accumulator[item.topic_name] = item
    return accumulator
  }, {})
})

const filteredTopics = computed(() => {
  if (!analysis.value) {
    return []
  }
  if (!selectedTopicName.value) {
    return analysis.value.topics
  }
  return analysis.value.topics.filter((topic) => topic.name === selectedTopicName.value)
})

const selectedTopic = computed<TaskTopic | null>(() => {
  if (!analysis.value || !selectedTopicName.value) {
    return null
  }
  return analysis.value.topics.find((topic) => topic.name === selectedTopicName.value) ?? null
})

const latestHotTopic = computed(() => analysis.value?.advanced.latest_hot_topic.topic ?? null)

const latestHotTopicSummary = computed(() => {
  return analysis.value?.advanced.latest_hot_topic.reason || '主题分析完成后会在这里汇总一个当前最值得优先关注的热点主题。'
})

const selectedTopicInsight = computed<TaskAnalysisTopicInsight | null>(() => {
  if (compareMode.value) {
    return null
  }
  if (!selectedTopicName.value) {
    return latestHotTopic.value
  }
  return topicInsightByName.value[selectedTopicName.value] ?? null
})

const selectedTopicVideos = computed<TaskAnalysisVideoInsight[]>(() => {
  if (compareMode.value) {
    return allVideoInsights.value
  }
  const topicName = selectedTopicInsight.value?.topic_name || selectedTopicName.value
  if (!topicName) {
    return allVideoInsights.value
  }
  return allVideoInsights.value.filter((item) => item.topic_name === topicName)
})

const selectedExplosiveVideo = computed<TaskAnalysisVideoInsight | null>(() => {
  const items = analysis.value?.advanced.explosive_videos ?? []
  if (!items.length) {
    return null
  }
  return items.find((item) => item.video_id === selectedExplosiveVideoId.value) ?? items[0]
})

const historyCoveredCount = computed(() => {
  return allVideoInsights.value.filter((item) => item.historical_snapshot_count > 1).length
})

const taskOptions = computed<Record<string, unknown>>(() => {
  const extraParams = taskProgress.value?.extra_params
  if (!extraParams || typeof extraParams !== 'object') {
    return {}
  }
  const raw = extraParams.task_options
  return raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
})

const taskScopeLabel = computed(() => {
  const scope = String(taskOptions.value.search_scope || 'site')
  if (scope === 'partition') {
    return `固定分区：${String(taskOptions.value.partition_name || taskOptions.value.partition_tid || '未命名分区')}`
  }
  return 'B 站全站'
})

const filteredPublishedVideos = computed(() => {
  return selectedTopicVideos.value.filter((video) =>
    isWithinRange(video.published_at, publishedWindow.start, publishedWindow.end, false),
  )
})

const filteredComparisonVideos = computed(() => {
  return allVideoInsights.value.filter(
    (video) =>
      Boolean(video.topic_name) &&
      isWithinRange(video.published_at, publishedWindow.start, publishedWindow.end, false),
  )
})

const comparisonPublishedBuckets = computed(() => {
  return buildPublishedBuckets(filteredComparisonVideos.value, publishedWindow.granularity)
})

const comparisonBuckets = computed(() => {
  return comparisonPublishedBuckets.value.map((bucket) => bucket.label)
})

const comparisonSeries = computed<TopicComparisonSeries[]>(() => {
  const bucketTopicMaps = comparisonPublishedBuckets.value.map((bucket) => {
    const groups = new Map<string, TaskAnalysisVideoInsight[]>()
    bucket.videos.forEach((video) => {
      if (!video.topic_name) {
        return
      }
      const current = groups.get(video.topic_name) ?? []
      current.push(video)
      groups.set(video.topic_name, current)
    })
    return groups
  })

  const topicOrder = [
    ...(analysis.value?.topics.map((topic) => topic.name) ?? []),
    ...allVideoInsights.value.map((video) => video.topic_name).filter((topicName): topicName is string => Boolean(topicName)),
  ].filter((topicName, index, items) => items.indexOf(topicName) === index)

  return topicOrder
    .map((topicName) => {
      const values = bucketTopicMaps.map((groups) => calculateTopicHeatIndex(groups.get(topicName) ?? []))
      const totalHeatIndex = round(sum(values))
      const peakValue = Math.max(...values, 0)
      const peakIndex = values.findIndex((value) => value === peakValue)
      return {
        topic_name: topicName,
        values,
        total_heat_index: totalHeatIndex,
        peak_bucket: peakIndex >= 0 ? comparisonBuckets.value[peakIndex] || '--' : '--',
        peak_value: round(peakValue),
        dominant_bucket_count: 0,
        direction: inferTrendDirection(
          values.map((value, index) => ({
            bucket: comparisonBuckets.value[index] || '',
            topic_heat_index: value,
            total_heat_score: value,
            video_count: 1,
          })),
        ),
      }
    })
    .filter((item) => item.total_heat_index > 0)
    .sort((left, right) => right.total_heat_index - left.total_heat_index)
})

const comparisonLeaders = computed<TopicLeaderPoint[]>(() => {
  return comparisonBuckets.value
    .map((bucket, index) => {
      const ranked = comparisonSeries.value
        .map((item) => ({
          topic_name: item.topic_name,
          value: item.values[index] ?? 0,
        }))
        .filter((item) => item.value > 0)
        .sort((left, right) => right.value - left.value)
      if (!ranked.length) {
        return null
      }
      return {
        bucket,
        topic_name: ranked[0].topic_name,
        value: ranked[0].value,
      }
    })
    .filter((item): item is TopicLeaderPoint => Boolean(item))
})

const comparisonLeaderPhases = computed<TopicLeaderPhase[]>(() => {
  return comparisonLeaders.value.reduce<TopicLeaderPhase[]>((phases, leader) => {
    const current = phases[phases.length - 1]
    if (current && current.topic_name === leader.topic_name) {
      current.end_bucket = leader.bucket
      current.bucket_count += 1
      if (leader.value >= current.peak_value) {
        current.peak_value = leader.value
        current.peak_bucket = leader.bucket
      }
      return phases
    }
    phases.push({
      topic_name: leader.topic_name,
      start_bucket: leader.bucket,
      end_bucket: leader.bucket,
      bucket_count: 1,
      peak_bucket: leader.bucket,
      peak_value: leader.value,
    })
    return phases
  }, [])
})

const comparisonLeaderSwitchCount = computed(() => {
  return Math.max(comparisonLeaderPhases.value.length - 1, 0)
})

const comparisonTrendLabel = computed(() => {
  if (!comparisonLeaderPhases.value.length) {
    return '暂无对比'
  }
  if (comparisonLeaderSwitchCount.value === 0) {
    return '领跑稳定'
  }
  return `领跑切换 ${comparisonLeaderSwitchCount.value} 次`
})

const comparisonHeadline = computed(() => {
  if (!comparisonLeaderPhases.value.length) {
    return '当前时间窗内还没有形成清晰的主题领跑关系'
  }
  const first = comparisonLeaderPhases.value[0]
  const latest = comparisonLeaderPhases.value[comparisonLeaderPhases.value.length - 1]
  if (first.topic_name === latest.topic_name) {
    return `${first.topic_name} 在当前时间窗内保持持续领跑`
  }
  return `${first.topic_name} 率先起势，随后热度重心转向 ${latest.topic_name}`
})

const comparisonNarrative = computed(() => {
  if (!comparisonLeaderPhases.value.length) {
    return '当前筛选条件下的视频发布时间样本不足，建议拉长时间窗或调整粒度后再观察热点演化。'
  }
  const first = comparisonLeaderPhases.value[0]
  const latest = comparisonLeaderPhases.value[comparisonLeaderPhases.value.length - 1]
  const middleTopics = comparisonLeaderPhases.value
    .slice(1, -1)
    .map((phase) => phase.topic_name)
    .filter((topicName, index, items) => items.indexOf(topicName) === index)

  if (comparisonLeaderSwitchCount.value === 0) {
    return `${first.topic_name} 从 ${formatPhaseRange(first.start_bucket, first.end_bucket)} 一直保持最高热度，说明这个主题在当前搜索词下的吸引力更稳定。`
  }

  const middleText = middleTopics.length ? `，中间还穿插过 ${middleTopics.join('、')} 的阶段性抬头` : ''
  return `${first.topic_name} 到 ${latest.topic_name} 的领跑切换${middleText}，说明用户兴趣已经从早期关注点逐步扩散到新的内容方向。`
})

const comparisonSummaryPoints = computed(() => {
  if (!comparisonSeries.value.length) {
    return ['当前筛选条件下还没有足够的主题样本，暂时无法生成可靠的热点对比结论。']
  }

  const highestPeak = [...comparisonSeries.value].sort((left, right) => right.peak_value - left.peak_value)[0]
  const strongestRise = [...comparisonSeries.value]
    .map((item) => ({
      ...item,
      growth: item.values.length >= 2 ? item.values[item.values.length - 1] - item.values[0] : 0,
    }))
    .sort((left, right) => right.growth - left.growth)[0]
  const latestLeader = comparisonLeaderPhases.value[comparisonLeaderPhases.value.length - 1]

  const points = [
    highestPeak
      ? `${highestPeak.topic_name} 在 ${highestPeak.peak_bucket} 达到全局最高峰值，说明那一段时间它是最强的流量中心。`
      : '',
    latestLeader
      ? `${latestLeader.topic_name} 在最近阶段保持领先，适合作为当前继续追踪和补抓的重点主题。`
      : '',
    strongestRise && strongestRise.growth > 0
      ? `${strongestRise.topic_name} 的后段热度抬升最明显，说明它是近期最值得警惕的增量方向。`
      : '',
    comparisonLeaderSwitchCount.value > 0
      ? `在当前时间窗内一共发生了 ${comparisonLeaderSwitchCount.value} 次领跑切换，热点并不是单线程发展，而是在多个主题之间轮动。`
      : '当前热点格局相对稳定，尚未出现明显的主题接力。',
  ]

  return points.filter(Boolean)
})

const comparisonTopTopicLabels = computed(() => {
  return comparisonSeries.value
    .slice(0, 5)
    .map((item) => `${item.topic_name} / 峰值 ${formatScore(item.peak_value, 1)}`)
})

const evolutionChartPoints = computed<TopicEvolutionChartPoint[]>(() => {
  const buckets = buildPublishedBuckets(filteredPublishedVideos.value, publishedWindow.granularity)
  return buckets.map((bucket) => {
    return {
      bucket: bucket.label,
      video_count: bucket.videos.length,
      total_heat_score: round(sum(bucket.videos.map((video) => video.heat_score))),
      topic_heat_index: calculateTopicHeatIndex(bucket.videos),
    }
  })
})

const selectedTrendDirection = computed(() => inferTrendDirection(evolutionChartPoints.value))

const depthChartPoints = computed<DepthChartPoint[]>(() => {
  const buckets = buildPublishedBuckets(filteredPublishedVideos.value, publishedWindow.granularity)
  return buckets.map((bucket) => ({
    bucket: bucket.label,
    average_depth_score: round(average(bucket.videos.map((video) => video.depth_score || 0))),
    average_completion_proxy_score: round(average(bucket.videos.map((video) => video.completion_proxy_score || 0))),
    average_like_view_ratio: average(bucket.videos.map((video) => video.like_view_ratio || 0)),
  }))
})

const communityChartPoints = computed<CommunityChartPoint[]>(() => {
  const buckets = buildPublishedBuckets(filteredPublishedVideos.value, publishedWindow.granularity)
  return buckets.map((bucket) => ({
    bucket: bucket.label,
    average_community_score: round(average(bucket.videos.map((video) => video.community_score || 0))),
    average_share_view_ratio: average(bucket.videos.map((video) => video.share_view_ratio || 0)),
    average_reply_view_ratio: average(bucket.videos.map((video) => video.reply_view_ratio || 0)),
  }))
})

const historyChartPoints = computed<HistoryChartPoint[]>(() => {
  if (!selectedExplosiveVideo.value) {
    return []
  }
  return buildHistoryChartPoints(
    selectedExplosiveVideo.value.history,
    historyWindow.start,
    historyWindow.end,
    historyWindow.granularity,
  )
})

function round(value: number) {
  return Number(value.toFixed(4))
}

function sum(values: number[]) {
  return values.reduce((total, value) => total + value, 0)
}

function average(values: number[]) {
  if (!values.length) {
    return 0
  }
  return sum(values) / values.length
}

function calculateTopicHeatIndex(videos: TaskAnalysisVideoInsight[]) {
  if (!videos.length) {
    return 0
  }
  const totalHeatScore = sum(videos.map((video) => video.heat_score))
  const averageBurstScore = average(videos.map((video) => video.burst_score || 0))
  const averageCommunityScore = average(videos.map((video) => video.community_score || 0))
  return round(totalHeatScore + averageBurstScore + averageCommunityScore)
}

function parseDateValue(value: string | null | undefined, endOfDay = false): Date | null {
  if (!value) {
    return null
  }
  const normalized = value.includes('T')
    ? value
    : value.includes(' ')
      ? value.replace(' ', 'T')
      : `${value}T00:00:00`
  const parsed = new Date(normalized)
  if (Number.isNaN(parsed.getTime())) {
    return null
  }
  if (endOfDay && !value.includes(':')) {
    parsed.setHours(23, 59, 59, 999)
  }
  return parsed
}

function isWithinRange(value: string | null | undefined, start: string, end: string, treatUndatedAsPass: boolean) {
  const parsed = parseDateValue(value)
  if (!parsed) {
    return treatUndatedAsPass
  }
  const startDate = parseDateValue(start)
  const endDate = parseDateValue(end, true)
  if (startDate && parsed < startDate) {
    return false
  }
  if (endDate && parsed > endDate) {
    return false
  }
  return true
}

function startOfBucket(date: Date, granularity: PublishedGranularity | HistoryGranularity) {
  const normalized = new Date(date)
  normalized.setMilliseconds(0)
  normalized.setSeconds(0)
  normalized.setMinutes(0)
  normalized.setHours(0)
  if (granularity === 'week') {
    const day = normalized.getDay()
    const offset = day === 0 ? 6 : day - 1
    normalized.setDate(normalized.getDate() - offset)
    return normalized
  }
  if (granularity === 'month') {
    normalized.setDate(1)
    return normalized
  }
  return normalized
}

function formatBucketLabel(date: Date, granularity: PublishedGranularity | HistoryGranularity) {
  if (granularity === 'month') {
    return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit' }).format(date)
  }
  if (granularity === 'week') {
    return `${new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(date)} 当周`
  }
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit' }).format(date)
}

function buildPublishedBuckets(videos: TaskAnalysisVideoInsight[], granularity: PublishedGranularity) {
  const grouped = new Map<string, { date: Date; label: string; videos: TaskAnalysisVideoInsight[] }>()
  videos.forEach((video) => {
    const publishedAt = parseDateValue(video.published_at)
    if (!publishedAt) {
      return
    }
    const bucketDate = startOfBucket(publishedAt, granularity)
    const key = bucketDate.toISOString()
    const current = grouped.get(key) ?? { date: bucketDate, label: formatBucketLabel(bucketDate, granularity), videos: [] }
    current.videos.push(video)
    grouped.set(key, current)
  })
  return Array.from(grouped.values()).sort((left, right) => left.date.getTime() - right.date.getTime())
}

function formatHistoryPointLabel(point: TaskAnalysisVideoHistoryPoint) {
  if (point.label === 'search_baseline') {
    return '搜索基线'
  }
  if (!point.captured_at) {
    return point.label || '历史快照'
  }
  const parsed = parseDateValue(point.captured_at)
  if (!parsed) {
    return point.label || '历史快照'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}

function buildHistoryChartPoints(
  history: TaskAnalysisVideoHistoryPoint[],
  start: string,
  end: string,
  granularity: HistoryGranularity,
) {
  const filtered = history.filter((point) =>
    isWithinRange(point.captured_at, start, end, point.label === 'search_baseline'),
  )
  if (!filtered.length) {
    return []
  }
  if (granularity === 'raw') {
    return filtered.map((point) => ({
      label: formatHistoryPointLabel(point),
      view_count: point.view_count,
      like_count: point.like_count,
      share_count: point.share_count,
    }))
  }
  const grouped = new Map<string, { date: Date; label: string; point: TaskAnalysisVideoHistoryPoint }>()
  const baselines: HistoryChartPoint[] = []
  filtered.forEach((point) => {
    const capturedAt = parseDateValue(point.captured_at)
    if (!capturedAt) {
      baselines.push({
        label: formatHistoryPointLabel(point),
        view_count: point.view_count,
        like_count: point.like_count,
        share_count: point.share_count,
      })
      return
    }
    const bucketDate = startOfBucket(capturedAt, granularity)
    const key = bucketDate.toISOString()
    const current = grouped.get(key)
    if (!current || capturedAt >= current.date) {
      grouped.set(key, { date: capturedAt, label: formatBucketLabel(bucketDate, granularity), point })
    }
  })
  const groupedPoints = Array.from(grouped.values())
    .sort((left, right) => left.date.getTime() - right.date.getTime())
    .map((item) => ({
      label: item.label,
      view_count: item.point.view_count,
      like_count: item.point.like_count,
      share_count: item.point.share_count,
    }))
  return [...baselines, ...groupedPoints]
}

function inferTrendDirection(points: TopicEvolutionChartPoint[]): TopicComparisonSeries['direction'] {
  if (points.length < 2) {
    return 'stable'
  }
  const first = points[0].topic_heat_index
  const latest = points[points.length - 1].topic_heat_index
  const delta = latest - first
  const threshold = Math.max(0.08, Math.abs(first) * 0.15)
  if (delta > threshold) {
    return 'rising'
  }
  if (delta < -threshold) {
    return 'cooling'
  }
  return 'stable'
}

function trendDirectionLabel(direction: string | undefined) {
  switch (direction) {
    case 'rising':
      return '持续升温'
    case 'cooling':
      return '热度回落'
    default:
      return '走势稳定'
  }
}

function formatPhaseRange(startBucket: string, endBucket: string) {
  return startBucket === endBucket ? startBucket : `${startBucket} - ${endBucket}`
}

function toDateInputValue(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function toDateTimeInputValue(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  const second = String(date.getSeconds()).padStart(2, '0')
  return `${year}-${month}-${day} ${hour}:${minute}:${second}`
}

function compactMetricText(text: string) {
  return text
    .replace(/\s+/g, ' ')
    .split(/[。；]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .join('；')
}

function syncPublishedWindow() {
  const datedVideos = allVideoInsights.value
    .map((video) => parseDateValue(video.published_at))
    .filter((value): value is Date => value instanceof Date)
    .sort((left, right) => left.getTime() - right.getTime())
  if (!datedVideos.length) {
    publishedWindow.start = ''
    publishedWindow.end = ''
    return
  }
  publishedWindow.start = publishedWindow.start || toDateInputValue(datedVideos[0])
  publishedWindow.end = publishedWindow.end || toDateInputValue(datedVideos[datedVideos.length - 1])
}

function syncHistoryWindow() {
  const history = selectedExplosiveVideo.value?.history ?? []
  const datedPoints = history
    .map((point) => parseDateValue(point.captured_at))
    .filter((value): value is Date => value instanceof Date)
    .sort((left, right) => left.getTime() - right.getTime())
  if (!datedPoints.length) {
    historyWindow.start = ''
    historyWindow.end = ''
    return
  }
  historyWindow.start = historyWindow.start || toDateTimeInputValue(datedPoints[0])
  historyWindow.end = historyWindow.end || toDateTimeInputValue(datedPoints[datedPoints.length - 1])
}

function handleClearTopicSelection() {
  compareMode.value = false
  selectedTopicName.value = ''
}

function enableCompareMode() {
  compareMode.value = true
  selectedTopicName.value = ''
}

function focusTopic(topicName: string) {
  compareMode.value = false
  selectedTopicName.value = topicName
}

function handleSelectTopic(topicName: string) {
  compareMode.value = false
  selectedTopicName.value = selectedTopicName.value === topicName ? '' : topicName
}

function handleRowClick(row: TaskTopic) {
  handleSelectTopic(row.name)
}

function shouldPoll(status: TaskProgressPayload['status'] | undefined): boolean {
  return isActiveTaskStatus(status)
}

function clearTimer() {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
}

function replaceController(current: AbortController | null): AbortController {
  current?.abort()
  return new AbortController()
}

function abortPendingRequests() {
  progressController?.abort()
  analysisController?.abort()
  progressController = null
  analysisController = null
}

function syncPolling() {
  clearTimer()
  if (!shouldPoll(taskProgress.value?.status)) {
    return
  }
  timer = window.setInterval(() => {
    void pollTaskProgress()
  }, 8000)
}

function syncSelections() {
  if (!analysis.value) {
    selectedTopicName.value = ''
    selectedExplosiveVideoId.value = ''
    return
  }
  if (!selectedTopicName.value && !compareMode.value && analysis.value.advanced.latest_hot_topic.topic?.topic_name) {
    selectedTopicName.value = analysis.value.advanced.latest_hot_topic.topic.topic_name
  }
  if (!selectedExplosiveVideoId.value && analysis.value.advanced.explosive_videos.length) {
    selectedExplosiveVideoId.value = analysis.value.advanced.explosive_videos[0].video_id
  }
}

async function fetchAnalysis() {
  const controller = replaceController(analysisController)
  analysisController = controller
  loading.value = true
  try {
    workspaceStore.setCurrentTaskId(taskId.value)
    const response = await getTaskAnalysis(taskId.value, { signal: controller.signal })
    if (analysisController !== controller) {
      return
    }
    analysis.value = response
    syncSelections()
    syncPublishedWindow()
    syncHistoryWindow()
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '加载主题分析失败。'))
    }
  } finally {
    if (analysisController === controller) {
      analysisController = null
      loading.value = false
    }
  }
}

async function fetchTaskProgress() {
  const controller = replaceController(progressController)
  progressController = controller
  try {
    const response = await getTaskProgress(taskId.value, { signal: controller.signal })
    if (progressController !== controller) {
      return
    }
    taskProgress.value = response
    latestProgressLogId.value = response.latest_log?.id ?? latestProgressLogId.value
    syncPolling()
  } catch (error) {
    if (isRequestCanceled(error)) {
      return
    }
    throw error
  } finally {
    if (progressController === controller) {
      progressController = null
    }
  }
}

async function pollTaskProgress() {
  if (pollInFlight) {
    return
  }
  pollInFlight = true
  try {
    const previousLogId = latestProgressLogId.value
    const previousStatus = taskProgress.value?.status
    await fetchTaskProgress()
    const currentLogId = taskProgress.value?.latest_log?.id ?? ''
    const currentStatus = taskProgress.value?.status
    if (currentLogId !== previousLogId || currentStatus !== previousStatus) {
      await fetchAnalysis()
    }
  } catch (error) {
    if (!isRequestCanceled(error)) {
      ElMessage.error(getErrorMessage(error, '更新任务进度失败。'))
    }
    clearTimer()
  } finally {
    pollInFlight = false
  }
}

async function handleExport() {
  exporting.value = true
  try {
    const artifact = await exportTaskResults(taskId.value, exportDataset.value, exportFormat.value, {
      topic: selectedTopicName.value || null,
    })
    triggerBlobDownload(artifact.blob, artifact.filename)
    ElMessage.success('导出已开始下载。')
  } catch (error) {
    ElMessage.error(getErrorMessage(error, '导出失败，请稍后重试。'))
  } finally {
    exporting.value = false
  }
}

watch(taskId, () => {
  abortPendingRequests()
  selectedTopicName.value = ''
  compareMode.value = false
  selectedExplosiveVideoId.value = ''
  publishedWindow.start = ''
  publishedWindow.end = ''
  historyWindow.start = ''
  historyWindow.end = ''
  analysis.value = null
  taskProgress.value = null
  latestProgressLogId.value = ''
  void Promise.all([fetchTaskProgress(), fetchAnalysis()])
})

watch(
  allVideoInsights,
  () => {
    syncPublishedWindow()
  },
  { deep: true },
)

watch(
  selectedExplosiveVideo,
  () => {
    historyWindow.start = ''
    historyWindow.end = ''
    syncHistoryWindow()
  },
  { deep: true },
)

onMounted(() => {
  analysis.value = null
  taskProgress.value = null
  latestProgressLogId.value = ''
  void Promise.all([fetchTaskProgress(), fetchAnalysis()])
})

onBeforeUnmount(() => {
  clearTimer()
  abortPendingRequests()
})
</script>

<style scoped>
.stats-grid--wide {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.metric-grid,
.signal-grid,
.recommendation-grid,
.insight-grid {
  display: grid;
  gap: 12px;
}

.metric-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.metric-card,
.signal-item,
.recommendation-card {
  border: 1px solid rgba(100, 72, 46, 0.12);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.55);
}

.metric-card {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.metric-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.metric-card__head span,
.metric-card small,
.signal-item span,
.recommendation-card p,
.insight-summary p,
.mini-list__item small,
.chart-note {
  color: var(--muted);
}

.metric-card__formula {
  padding: 8px 10px;
  border-radius: 12px;
  background: rgba(255, 248, 241, 0.8);
  color: var(--text);
  line-height: 1.5;
  font-weight: 600;
}

.metric-card__line {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.metric-card__line span {
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}

.metric-card__line small {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.signal-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 8px;
}

.signal-item {
  padding: 10px 12px;
}

.signal-item strong,
.recommendation-card h5,
.insight-summary h5 {
  display: block;
  margin-top: 6px;
}

.timeline-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.topic-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
}

.chart-note {
  margin-top: 12px;
  line-height: 1.7;
}

.trend-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(189, 91, 32, 0.1);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
}

.trend-pill--rising {
  background: rgba(42, 111, 67, 0.12);
  color: #266245;
}

.trend-pill--cooling {
  background: rgba(181, 115, 29, 0.12);
  color: #945715;
}

.trend-pill--compare {
  background: rgba(75, 111, 173, 0.12);
  color: #2f5588;
}

.insight-summary,
.insight-sublist {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.phase-list {
  display: grid;
  gap: 12px;
}

.phase-card {
  border: 1px solid rgba(100, 72, 46, 0.12);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.55);
  padding: 14px;
}

.phase-card__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.phase-card p {
  margin: 0;
  color: var(--muted);
  line-height: 1.7;
}

.insight-summary h5,
.recommendation-card h5 {
  margin: 0;
}

.insight-summary p,
.recommendation-card p {
  margin: 0;
  line-height: 1.7;
}

.insight-list {
  margin: 0;
  padding-left: 18px;
  color: var(--text);
  display: grid;
  gap: 10px;
}

.mini-list__item--button,
.analysis-link-button {
  border: 0;
  background: transparent;
  text-align: left;
  color: inherit;
  padding: 0;
  cursor: pointer;
}

.mini-list__item--button {
  width: 100%;
}

.mini-list__item--button.is-active {
  color: var(--accent);
}

.analysis-link-button {
  font-weight: 700;
}

.recommendation-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.recommendation-card {
  padding: 14px;
}

.insight-grid--triple {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

@media (max-width: 1280px) {
  .stats-grid--wide,
  .metric-grid,
  .insight-grid--triple,
  .recommendation-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .stats-grid--wide,
  .metric-grid,
  .signal-grid,
  .insight-grid--triple,
  .recommendation-grid {
    grid-template-columns: 1fr;
  }

  .timeline-toolbar {
    flex-direction: column;
  }
}
</style>

