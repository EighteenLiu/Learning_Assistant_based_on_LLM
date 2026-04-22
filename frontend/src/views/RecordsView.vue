<template>
  <div class="records-page">
    <section class="records-shell" :class="{ collapsed: sidebarCollapsed }">
      <aside v-if="!sidebarCollapsed" class="page-card records-sidebar" @click.stop>
        <div class="sidebar-toggle-wrap">
          <el-button plain size="small" class="sidebar-toggle-btn" @click="sidebarCollapsed = true">
            《
          </el-button>
        </div>

        <div class="sidebar-head">
          <div class="records-kicker">PPT Archive</div>
          <h2>历史课件</h2>
          <p>左侧选择课件，右侧继续查看内容、问答和总结。</p>
          <el-button type="primary" @click="goWorkbench">工作台</el-button>
        </div>

        <div v-if="!coursewares.length" class="sidebar-empty">暂无课件</div>
        <div v-else class="sidebar-list">
          <button
            v-for="item in coursewares"
            :key="item.id"
            type="button"
            class="courseware-item"
            :class="{ active: item.id === selectedCoursewareId }"
            @click="selectCourseware(item.id)"
          >
            <strong>{{ item.title }}</strong>
            <span>路 #{{ item.id }} 路 {{ formatCoursewareDuration(item) }}</span>
          </button>
        </div>
      </aside>
      <button
        v-if="sidebarCollapsed"
        type="button"
        class="sidebar-collapsed-handle"
        @click.stop="sidebarCollapsed = false"
      >
        》
      </button>
      <div v-if="!sidebarCollapsed" class="sidebar-backdrop" @click="sidebarCollapsed = true"></div>

      <main class="records-main">
        <section class="page-card current-panel">
          <div class="current-head">
            <div>
              <div class="records-kicker">Current PPT</div>
              <h3>{{ currentCoursewareTitle }}</h3>
              <p>当前课件记录已同步，可直接在此继续问答与总结。</p>
            </div>
            <el-button type="primary" @click="pinToWorkbench">置于工作台</el-button>
          </div>

          <div class="records-stats">
            <div class="record-stat-card">
              <span>已解析页数</span>
              <strong>{{ slides.length }}</strong>
            </div>
            <div class="record-stat-card">
              <span>问答记录</span>
              <strong>{{ qaRecords.length }}</strong>
            </div>
            <div class="record-stat-card">
              <span>总结记录</span>
              <strong>{{ summaryRecords.length }}</strong>
            </div>
            <div class="record-stat-card">
              <span>翻译用时</span>
              <strong>{{ currentCoursewareDuration }}</strong>
            </div>
          </div>
        </section>

        <section class="page-card compare-panel">
          <div class="panel-head">
            <div>
              <div class="panel-kicker">Translation Preview</div>
              <h3>中英 PPT 对照</h3>
            </div>

            <div class="panel-actions">
              <div class="scope-badge">
                <span>当前页</span>
                <strong>{{ currentSlide?.slide_no ?? "-" }} / {{ slides.length || "-" }}</strong>
              </div>
              <el-input-number
                v-model="previewJumpNo"
                class="preview-jump-input"
                :min="1"
                :max="Math.max(slides.length, 1)"
                :controls="false"
                :step="1"
                :precision="0"
                size="small"
                :disabled="!slides.length"
              />
              <el-button size="small" :disabled="!slides.length" @click="jumpPreviewSlide">跳转</el-button>
              <el-button-group>
                <el-button :disabled="!slides.length || currentSlideIndex <= 0" @click="prevSlide">上一页</el-button>
                <el-button :disabled="!slides.length || currentSlideIndex >= slides.length - 1" @click="nextSlide">下一页</el-button>
              </el-button-group>
            </div>
          </div>

          <div v-if="!currentSlide" class="compare-empty">当前课件暂无可预览页面。</div>
          <template v-else>
            <div class="compare-grid">
              <article class="preview-card">
                <div class="preview-title">英文原始页</div>
                <div class="slide-canvas" :style="canvasStyle(currentSlide.source_layout, currentSlide.source_text)">
                  <img v-if="currentSlide.source_image_url" class="slide-image" :src="currentSlide.source_image_url" alt="原始课件页" />
                  <div v-else class="image-fallback">当前页没有生成原始截图。</div>
                </div>
              </article>

              <article class="preview-card">
                <div class="preview-title">中文翻译页</div>
                <div class="slide-canvas translated-stage" :style="canvasStyle(currentSlide.translated_layout, currentSlide.translated_text)">
                  <img v-if="translatedPreviewUrl" class="slide-image" :src="translatedPreviewUrl" alt="中文翻译页" />
                  <div
                    v-if="translatedPreviewUrl"
                    v-for="block in imageOcrBlocks"
                    :key="`img-ocr-${currentSlide.slide_no}-${block.block_id}`"
                    class="slide-block image-ocr-overlay"
                    :style="blockStyle(block)"
                  >
                    {{ block.text }}
                  </div>
                  <template v-else>
                    <div class="translated-background"></div>
                    <div
                      v-for="block in translatedBlocks"
                      :key="`zh-${currentSlide.slide_no}-${block.block_id}`"
                      class="slide-block"
                      :class="{ title: block.is_title }"
                      :style="blockStyle(block)"
                    >
                      {{ block.text }}
                    </div>
                  </template>
                </div>
              </article>
            </div>

            <div class="copy-grid">
              <div class="copy-card">
                <div class="copy-label">英文提取文本</div>
                <div class="copy-content">{{ currentSlide.source_text || "No source text." }}</div>
              </div>
              <div class="copy-card">
                <div class="copy-label">中文翻译文本</div>
                <div class="copy-content">{{ currentSlide.translated_text || "Translation in progress." }}</div>
              </div>
            </div>
          </template>
        </section>
        <section class="records-content-grid">
          <article class="page-card record-panel">
            <div class="panel-head">
              <div>
                <div class="panel-kicker">Continue Asking</div>
                <h3>继续问答</h3>
              </div>
            </div>

            <div class="qa-controls">
              <el-select
                v-model="currentSlideNo"
                class="slide-select"
                placeholder="选择页码"
                :disabled="useGlobalScope || slides.length === 0"
              >
                <el-option
                  v-for="slide in slides"
                  :key="slide.slide_no"
                  :label="`第 ${slide.slide_no} 页${slide.title ? ` · ${slide.title}` : ''}`"
                  :value="slide.slide_no"
                />
              </el-select>
              <el-checkbox v-model="useGlobalScope">基于整份课件问答</el-checkbox>
              <el-button plain @click="resetConversation">重置当前对话</el-button>
            </div>

            <div class="chat-shell">
              <div
                v-for="(msg, idx) in messages"
                :key="`${msg.role}-${idx}-${msg.timestamp || idx}`"
                class="chat-bubble"
                :class="msg.role"
              >
                <div class="bubble-head">
                  <div class="bubble-meta">
                    <span class="bubble-role">{{ msg.role === "user" ? "你" : "学习助教" }}</span>
                    <span v-if="msg.scopeLabel" class="bubble-scope">{{ msg.scopeLabel }}</span>
                  </div>
                  <span v-if="msg.timestamp" class="bubble-time">{{ msg.timestamp }}</span>
                </div>

                <div
                  v-if="msg.role === 'assistant'"
                  class="bubble-content markdown-body"
                  v-html="renderMarkdown(msg.content)"
                ></div>
                <div v-else class="bubble-content">{{ msg.content }}</div>

                <div v-if="msg.citations?.length" class="bubble-citations">
                  <button
                    v-for="citation in msg.citations"
                    :key="`${idx}-${citation.slide_no}-${citation.snippet}`"
                    class="citation-chip"
                    type="button"
                    @click="focusSlide(citation.slide_no)"
                  >
                    引用第 {{ citation.slide_no }} 页
                  </button>
                </div>
              </div>
            </div>

            <el-input
              v-model="question"
              type="textarea"
              :rows="4"
              maxlength="1000"
              show-word-limit
              placeholder="例如：第 8 页里的结论是如何推导出来的？"
              @keydown="handleQuestionKeydown"
            />

            <div class="toolbar">
              <el-button type="primary" :loading="qaLoading" @click="submitQuestion">发送问题</el-button>
            </div>
          </article>

          <article class="page-card record-panel">
            <div class="panel-head">
              <div>
                <div class="panel-kicker">Knowledge Snapshot</div>
                <h3>总结</h3>
              </div>
              <el-button type="primary" :loading="summaryLoading" @click="generateSummary">重新生成总结</el-button>
            </div>

            <template v-if="latestSummary">
              <div class="summary-highlight">
                <span>最近总结时间</span>
                <strong>{{ formatTime(latestSummary.created_at) }}</strong>
              </div>

              <div class="summary-blurb">{{ latestSummary.chapter_summary }}</div>

              <div class="summary-points">
                <div v-for="(point, index) in latestSummary.key_points" :key="`${latestSummary.id}-${index}`" class="point-chip">
                  {{ point }}
                </div>
              </div>
            </template>

            <el-empty v-else description="当前课件还没有总结记录，可先生成一次总结。" />
          </article>
        </section>

        <section v-if="latestSummary" class="page-card knowledge-card full-width-knowledge">
          <div class="knowledge-head">
            <div>
              <div class="panel-kicker">Glossary</div>
              <h4>术语表</h4>
            </div>
            <span class="knowledge-count">{{ latestSummary.term_pairs?.length || 0 }} 条</span>
          </div>
          <el-empty v-if="!latestSummary.term_pairs?.length" description="当前总结还没有术语表" />
          <el-table v-else :data="latestSummary.term_pairs" border class="summary-table">
            <el-table-column prop="en" label="英文术语" min-width="260" />
            <el-table-column prop="zh" label="中文释义" min-width="260" />
          </el-table>
        </section>

        <section v-if="latestSummary" class="page-card knowledge-card full-width-knowledge">
          <div class="knowledge-head">
            <div>
              <div class="panel-kicker">Study Suggestions</div>
              <h4>学习建议</h4>
            </div>
            <span class="knowledge-count">{{ latestSummary.learning_suggestions?.length || 0 }} 条</span>
          </div>
          <el-empty v-if="!latestSummary.learning_suggestions?.length" description="当前总结还没有学习建议" />
          <ul v-else class="learning-list">
            <li v-for="(item, index) in latestSummary.learning_suggestions" :key="`learning-${index}`">{{ item }}</li>
          </ul>
        </section>

        <section v-if="latestSummary" class="page-card knowledge-card full-width-knowledge">
          <div class="knowledge-head">
            <div>
              <div class="panel-kicker">Mind Map</div>
              <h4>课程思维导图</h4>
            </div>
          </div>
          <div class="mind-map-shell">
            <ul class="mind-map-root">
              <MindMapNode :node="latestSummary.mind_map" />
            </ul>
          </div>
        </section>
      </main>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import MarkdownIt from "markdown-it";
import MindMapNode from "../components/MindMapNode.vue";
import { http } from "../api/client";
import type { CoursewareItem, SlideItem, SlideLayout, SlideLayoutBlock } from "../types";

interface Citation {
  slide_no: number;
  snippet: string;
}

interface QARecordItem {
  id: number;
  question: string;
  answer: string;
  citations: Citation[];
  created_at: string;
}

interface SummaryRecordItem {
  id: number;
  chapter_summary: string;
  key_points: string[];
  term_pairs: Array<{ en: string; zh: string }>;
  learning_suggestions: string[];
  mind_map: {
    title: string;
    children?: Array<any>;
  };
  created_at: string;
}

interface ChatMessageItem {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  scopeLabel?: string;
  timestamp?: string;
}

const router = useRouter();
const selectionEventName = "courseware-selection-changed";
const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: false,
});

const qaLoading = ref(false);
const summaryLoading = ref(false);
const sidebarCollapsed = ref(false);
const coursewares = ref<CoursewareItem[]>([]);
const selectedCoursewareId = ref<number | undefined>(
  localStorage.getItem("selected_courseware_id")
    ? Number(localStorage.getItem("selected_courseware_id"))
    : undefined
);
const qaRecords = ref<QARecordItem[]>([]);
const summaryRecords = ref<SummaryRecordItem[]>([]);
const slides = ref<SlideItem[]>([]);
const currentSlideNo = ref<number | undefined>(undefined);
const previewJumpNo = ref<number | null>(null);
const useGlobalScope = ref(true);
const question = ref("");
const messages = ref<ChatMessageItem[]>([]);

const currentCourseware = computed(
  () => coursewares.value.find((item) => item.id === selectedCoursewareId.value) || null
);
const currentCoursewareTitle = computed(() => currentCourseware.value?.title || "尚未选择课件");
const currentSlide = computed(() => slides.value.find((item) => item.slide_no === currentSlideNo.value));
const currentSlideIndex = computed(() =>
  Math.max(
    slides.value.findIndex((item) => item.slide_no === currentSlideNo.value),
    0
  )
);
const translatedPreviewUrl = computed(() => currentSlide.value?.processed_image_url || "");
const translatedBlocks = computed(() => {
  const blocks = currentSlide.value?.translated_layout?.blocks ?? [];
  if (blocks.length) {
    return blocks;
  }
  return [
    {
      block_id: 1,
      text: currentSlide.value?.translated_text || "",
      x: 0.08,
      y: 0.12,
      w: 0.84,
      h: 0.72,
      is_title: true,
    },
  ].filter((item) => item.text);
});
const imageOcrBlocks = computed(() =>
  translatedBlocks.value.filter((block) => block.kind === "image_ocr" && String(block.text || "").trim())
);
const latestSummary = computed(() => summaryRecords.value[0] || null);
const qaScopeLabel = computed(() => {
  if (useGlobalScope.value) {
    return "整份课件";
  }
  if (currentSlideNo.value) {
    const slide = slides.value.find((item) => item.slide_no === currentSlideNo.value);
    return slide?.title ? `第 ${slide.slide_no} 页 · ${slide.title}` : `第 ${currentSlideNo.value} 页`;
  }
  return "未选择页码";
});

const formatDuration = (totalSeconds?: number | null) => {
  const sec = Math.max(Math.floor(Number(totalSeconds || 0)), 0);
  const hours = Math.floor(sec / 3600);
  const minutes = Math.floor((sec % 3600) / 60);
  const seconds = sec % 60;
  if (hours > 0) return `${hours}小时${minutes}分钟`;
  if (minutes > 0) return `${minutes}分钟${seconds}秒`;
  return `${seconds}秒`;
};

const formatCoursewareDuration = (courseware?: CoursewareItem | null) => {
  if (!courseware || courseware.translation_duration_seconds == null) {
    return "暂无";
  }
  return formatDuration(courseware.translation_duration_seconds);
};

const currentCoursewareDuration = computed(() => formatCoursewareDuration(currentCourseware.value));
const formatTime = (value: string) => new Date(value).toLocaleString("zh-CN");
const renderMarkdown = (content: string) => markdown.render(content || "");

const getDefaultMessages = (): ChatMessageItem[] => [
  {
    role: "assistant",
    content: "这里会自动带上当前课件已有的问答上下文。你可以按页继续提问，也可以切换为整份课件统一问答。",
  },
];

const normalizeCitations = (citations: any): Citation[] => {
  if (!Array.isArray(citations)) {
    return [];
  }
  return citations
    .map((item) => ({
      slide_no: Number(item?.slide_no || 0),
      snippet: String(item?.snippet || ""),
    }))
    .filter((item) => item.slide_no > 0);
};

const normalizeMindMap = (node: any, fallbackTitle = "课程全景"): SummaryRecordItem["mind_map"] => {
  if (!node || typeof node !== "object") {
    return { title: fallbackTitle, children: [] };
  }
  const title = String(node.title || "").trim() || fallbackTitle;
  const children = Array.isArray(node.children)
    ? node.children.slice(0, 10).map((child: any) => normalizeMindMap(child, "主题"))
    : [];
  return { title, children };
};

const normalizeSummaryRecord = (record: any): SummaryRecordItem => ({
  id: Number(record?.id || Date.now()),
  chapter_summary: String(record?.chapter_summary || "总结已生成。"),
  key_points: Array.isArray(record?.key_points) ? record.key_points.map((item: any) => String(item)) : [],
  term_pairs: Array.isArray(record?.term_pairs)
    ? record.term_pairs
        .map((item: any) => ({
          en: String(item?.en || ""),
          zh: String(item?.zh || ""),
        }))
        .filter((item: { en: string; zh: string }) => item.en || item.zh)
    : [],
  learning_suggestions: Array.isArray(record?.learning_suggestions)
    ? record.learning_suggestions.map((item: any) => String(item || "").trim()).filter((item: string) => item)
    : [],
  mind_map: normalizeMindMap(record?.mind_map, currentCoursewareTitle.value || "课程全景"),
  created_at: String(record?.created_at || new Date().toISOString()),
});



const canvasStyle = (layout?: SlideLayout, text?: string) => {
  const pageWidth = Number(layout?.page_width) || 16;
  const pageHeight = Number(layout?.page_height) || 9;
  const hasText = Boolean((layout?.blocks?.length ?? 0) || text);
  return {
    aspectRatio: `${pageWidth} / ${pageHeight}`,
    opacity: hasText ? 1 : 0.7,
  };
};

const blockStyle = (block: SlideLayoutBlock) => ({
  left: `${(block.x || 0) * 100}%`,
  top: `${(block.y || 0) * 100}%`,
  width: `${(block.w || 0) * 100}%`,
  height: `${(block.h || 0) * 100}%`,
});

const buildScopeLabelFromRecord = (record: QARecordItem) => {
  const uniqueSlides = [...new Set((record.citations || []).map((item) => item.slide_no).filter(Boolean))];
  if (uniqueSlides.length === 1) {
    return `历史记录 · 第 ${uniqueSlides[0]} 页`;
  }
  if (uniqueSlides.length > 1) {
    return `历史记录 · 涉及 ${uniqueSlides.length} 页`;
  }
  return "历史记录";
};

const hydrateMessages = () => {
  const recentRecords = [...qaRecords.value].slice(0, 8).reverse();
  if (!recentRecords.length) {
    messages.value = getDefaultMessages();
    return;
  }
  messages.value = [
    ...getDefaultMessages(),
    ...recentRecords.flatMap((item) => [
      {
        role: "user" as const,
        content: item.question,
        scopeLabel: buildScopeLabelFromRecord(item),
        timestamp: formatTime(item.created_at),
      },
      {
        role: "assistant" as const,
        content: item.answer,
        citations: item.citations,
        scopeLabel: buildScopeLabelFromRecord(item),
        timestamp: formatTime(item.created_at),
      },
    ]),
  ];
};

const goWorkbench = async () => {
  await router.push("/dashboard/upload");
};

const pinToWorkbench = async () => {
  if (selectedCoursewareId.value) {
    localStorage.setItem("selected_courseware_id", String(selectedCoursewareId.value));
    window.dispatchEvent(new CustomEvent(selectionEventName, { detail: selectedCoursewareId.value }));
  }
  await router.push("/dashboard/upload#qa-section");
};

const fetchCoursewares = async () => {
  const { data } = await http.get<CoursewareItem[]>("/coursewares");
  coursewares.value = data;
  if (!selectedCoursewareId.value && data.length) {
    selectedCoursewareId.value = data[0].id;
    localStorage.setItem("selected_courseware_id", String(data[0].id));
  }
};

const loadAll = async () => {
  const selected = selectedCoursewareId.value;
  if (!selected) {
    qaRecords.value = [];
    summaryRecords.value = [];
    slides.value = [];
    currentSlideNo.value = undefined;
    messages.value = getDefaultMessages();
    return;
  }
  try {
    const [{ data: recordsData }, { data: slidesData }] = await Promise.all([
      http.get(`/coursewares/${selected}/records`),
      http.get<SlideItem[]>(`/coursewares/${selected}/slides`),
    ]);
    qaRecords.value = Array.isArray(recordsData?.qa_records)
      ? recordsData.qa_records.map((item: any) => ({
          id: Number(item?.id || 0),
          question: String(item?.question || ""),
          answer: String(item?.answer || ""),
          citations: normalizeCitations(item?.citations),
          created_at: String(item?.created_at || new Date().toISOString()),
        }))
      : [];
    summaryRecords.value = Array.isArray(recordsData?.summary_records)
      ? recordsData.summary_records.map((item: any) => normalizeSummaryRecord(item))
      : [];
    slides.value = Array.isArray(slidesData) ? slidesData : [];
    currentSlideNo.value = slides.value[0]?.slide_no;
    useGlobalScope.value = true;
    previewJumpNo.value = currentSlideNo.value ?? null;
    hydrateMessages();
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "加载历史学习内容失败");
  }
};

const selectCourseware = async (coursewareId: number) => {
  selectedCoursewareId.value = coursewareId;
  localStorage.setItem("selected_courseware_id", String(coursewareId));
  window.dispatchEvent(new CustomEvent(selectionEventName, { detail: coursewareId }));
  await loadAll();
};

const focusSlide = (slideNo: number) => {
  if (!slideNo) {
    return;
  }
  currentSlideNo.value = slideNo;
  previewJumpNo.value = slideNo;
};

const prevSlide = () => {
  if (!slides.value.length || currentSlideIndex.value <= 0) {
    return;
  }
  const target = slides.value[currentSlideIndex.value - 1];
  if (target) {
    focusSlide(target.slide_no);
  }
};

const nextSlide = () => {
  if (!slides.value.length || currentSlideIndex.value >= slides.value.length - 1) {
    return;
  }
  const target = slides.value[currentSlideIndex.value + 1];
  if (target) {
    focusSlide(target.slide_no);
  }
};


const jumpPreviewSlide = () => {
  if (!slides.value.length) {
    return;
  }
  const targetNo = Number(previewJumpNo.value);
  if (!Number.isFinite(targetNo) || targetNo <= 0) {
    ElMessage.warning("请输入有效页码");
    return;
  }
  const exists = slides.value.some((slide) => slide.slide_no === targetNo);
  if (!exists) {
    ElMessage.warning(`未找到第 ${targetNo} 页`);
    return;
  }
  focusSlide(targetNo);
};

const resetConversation = () => {
  question.value = "";
  hydrateMessages();
};

const handleQuestionKeydown = (event: KeyboardEvent) => {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
    return;
  }
  event.preventDefault();
  if (!qaLoading.value) {
    void submitQuestion();
  }
};

const submitQuestion = async () => {
  const selected = selectedCoursewareId.value;
  if (!selected) {
    ElMessage.warning("请先选择课件");
    return;
  }
  if (!question.value.trim()) {
    ElMessage.warning("请输入问题内容");
    return;
  }
  if (!useGlobalScope.value && !currentSlideNo.value) {
    ElMessage.warning("请先选择要提问的页码");
    return;
  }

  const content = question.value.trim();
  const scopeLabel = useGlobalScope.value ? "整份课件" : qaScopeLabel.value;
  messages.value.push({
    role: "user",
    content,
    scopeLabel,
    timestamp: new Date().toLocaleString("zh-CN"),
  });
  question.value = "";
  qaLoading.value = true;

  try {
    const history = messages.value
      .slice(0, -1)
      .filter((item) => item.role === "user" || item.role === "assistant")
      .map((item) => ({ role: item.role, content: item.content }));
    const { data } = await http.post(`/coursewares/${selected}/qa`, {
      question: content,
      slide_no: useGlobalScope.value ? undefined : currentSlideNo.value,
      use_global_scope: useGlobalScope.value,
      history,
    });
    qaRecords.value = [
      {
        id: Number(data?.id || Date.now()),
        question: content,
        answer: String(data?.answer || ""),
        citations: normalizeCitations(data?.citations),
        created_at: String(data?.created_at || new Date().toISOString()),
      },
      ...qaRecords.value,
    ];
    messages.value.push({
      role: "assistant",
      content: String(data?.answer || ""),
      citations: normalizeCitations(data?.citations),
      scopeLabel,
      timestamp: formatTime(String(data?.created_at || new Date().toISOString())),
    });
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "提问失败");
  } finally {
    qaLoading.value = false;
  }
};

const generateSummary = async () => {
  const selected = selectedCoursewareId.value;
  if (!selected) {
    ElMessage.warning("请先选择课件");
    return;
  }

  summaryLoading.value = true;
  try {
    const { data } = await http.post(`/coursewares/${selected}/summary`, {});
    summaryRecords.value = [normalizeSummaryRecord(data), ...summaryRecords.value];
    ElMessage.success("新的整体总结已生成");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "生成总结失败");
  } finally {
    summaryLoading.value = false;
  }
};

const handleSelectionEvent = async () => {
  const stored = localStorage.getItem("selected_courseware_id");
  selectedCoursewareId.value = stored ? Number(stored) : undefined;
  await loadAll();
};

watch(
  slides,
  (value) => {
    if (!value.length) {
      currentSlideNo.value = undefined;
      previewJumpNo.value = null;
      return;
    }
    if (!value.some((item) => item.slide_no === currentSlideNo.value)) {
      currentSlideNo.value = value[0].slide_no;
    }
    previewJumpNo.value = currentSlideNo.value ?? null;
  },
  { immediate: true }
);

watch(currentSlideNo, (value) => {
  if (!value) {
    return;
  }
  previewJumpNo.value = value;
});

onMounted(async () => {
  window.addEventListener(selectionEventName, handleSelectionEvent as EventListener);
  try {
    await fetchCoursewares();
    await loadAll();
  } catch {
    ElMessage.error("历史记录页面初始化失败");
  }
});

onUnmounted(() => {
  window.removeEventListener(selectionEventName, handleSelectionEvent as EventListener);
});
</script>

<style scoped>
.records-page {
  display: grid;
  gap: 20px;
}

.records-shell {
  position: relative;
  display: block;
  min-height: 520px;
}

.records-kicker,
.panel-kicker {
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted);
}

.records-sidebar {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 30;
  width: min(320px, calc(100vw - 28px));
  display: grid;
  align-content: start;
  gap: 14px;
  max-height: calc(100vh - 120px);
  overflow: hidden;
  box-shadow: 0 20px 42px rgba(58, 43, 31, 0.2);
}

.sidebar-backdrop {
  position: absolute;
  inset: 0;
  z-index: 20;
  background: rgba(0, 0, 0, 0);
}

.sidebar-collapsed-handle {
  position: absolute;
  top: 12px;
  left: 8px;
  z-index: 31;
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 10px;
  color: #4b3f34;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 10px 20px rgba(58, 43, 31, 0.18);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}

.sidebar-toggle-wrap {
  display: flex;
  justify-content: flex-end;
}

.sidebar-toggle-btn {
  width: 32px;
  height: 32px;
  min-width: 32px;
  padding: 0;
  font-size: 16px;
  line-height: 1;
  letter-spacing: 0;
}

.sidebar-head h2 {
  margin: 8px 0 0;
  font-size: 30px;
}

.sidebar-head p {
  margin: 12px 0 14px;
  color: var(--muted);
  line-height: 1.75;
}

.sidebar-empty {
  color: var(--muted);
  line-height: 1.75;
}

.sidebar-list {
  display: grid;
  gap: 10px;
  overflow-y: auto;
  padding-right: 4px;
}

.courseware-item {
  border: 1px solid rgba(122, 104, 86, 0.14);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.76);
  padding: 12px;
  text-align: left;
  display: grid;
  gap: 6px;
  cursor: pointer;
}

.courseware-item strong {
  display: block;
  line-height: 1.55;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.courseware-item span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.courseware-item.active {
  border-color: rgba(184, 92, 56, 0.38);
  background: linear-gradient(180deg, rgba(255, 247, 238, 0.9), rgba(255, 255, 255, 0.95));
}

.records-main {
  position: relative;
  z-index: 1;
  display: grid;
  gap: 16px;
}

.current-panel,
.compare-panel,
.record-panel {
  display: grid;
  gap: 14px;
}

.current-head,
.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.scope-badge {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(122, 104, 86, 0.16);
  color: var(--muted);
}

.scope-badge span {
  margin-right: 8px;
}

.scope-badge strong {
  color: var(--text);
}

.preview-jump-input {
  width: 94px;
}

.compare-empty {
  padding: 22px 18px;
  text-align: center;
  border-radius: 14px;
  color: var(--muted);
  border: 1px dashed rgba(122, 104, 86, 0.28);
  background: linear-gradient(180deg, rgba(255, 252, 247, 0.76), rgba(255, 255, 255, 0.9));
}

.compare-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.preview-card,
.copy-card {
  border: 1px solid rgba(122, 104, 86, 0.14);
  background: linear-gradient(180deg, rgba(255, 253, 249, 0.96), rgba(249, 244, 237, 0.92));
}

.preview-card {
  padding: 14px;
  border-radius: 16px;
}

.preview-title {
  margin-bottom: 10px;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-soft);
}

.slide-canvas {
  position: relative;
  overflow: hidden;
  min-height: 260px;
  border-radius: 14px;
  border: 1px solid rgba(122, 104, 86, 0.14);
  background: linear-gradient(180deg, rgba(247, 243, 236, 0.94), rgba(236, 230, 220, 0.84));
}

.translated-stage {
  background:
    radial-gradient(circle at top right, rgba(212, 168, 95, 0.18), transparent 28%),
    linear-gradient(180deg, rgba(255, 253, 249, 0.98), rgba(249, 244, 237, 0.96));
}

.translated-background {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(135deg, rgba(255, 247, 238, 0.76), rgba(255, 255, 255, 0.9)),
    radial-gradient(circle at bottom left, rgba(81, 98, 76, 0.12), transparent 34%);
}

.slide-image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: fill;
}

.image-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  text-align: center;
  color: var(--muted);
  background: rgba(255, 255, 255, 0.84);
}

.slide-block {
  position: absolute;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  padding: 6px 8px;
  border-radius: 12px;
  color: var(--text);
  background: rgba(255, 255, 255, 0.72);
  box-shadow: var(--shadow-soft);
  font-size: 14px;
  z-index: 1;
}

.slide-block.image-ocr-overlay {
  z-index: 2;
  background: rgba(255, 252, 240, 0.88);
  border: 1px solid rgba(176, 134, 72, 0.28);
}

.slide-block.title {
  font-size: 16px;
  font-weight: 700;
}

.copy-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.copy-card {
  padding: 14px;
  border-radius: 14px;
}

.copy-label {
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 0.04em;
}

.copy-content {
  margin-top: 8px;
  white-space: pre-wrap;
  line-height: 1.75;
}

.current-head h3,
.panel-head h3 {
  margin: 8px 0 0;
  font-size: 26px;
}

.current-head p {
  margin: 10px 0 0;
  color: var(--muted);
  line-height: 1.75;
}

.records-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
}

.record-stat-card {
  padding: 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(122, 104, 86, 0.14);
}

.record-stat-card span {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--muted);
}

.records-content-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 1fr);
  gap: 16px;
}

.qa-controls {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
}

.slide-select {
  min-width: min(360px, 100%);
}

.chat-shell {
  min-height: 340px;
  max-height: 560px;
  overflow-y: auto;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(122, 104, 86, 0.14);
  background:
    radial-gradient(circle at top right, rgba(81, 98, 76, 0.08), transparent 24%),
    linear-gradient(180deg, rgba(255, 252, 247, 0.94), rgba(251, 247, 240, 0.98));
}

.chat-bubble {
  max-width: min(92%, 820px);
  padding: 14px 16px;
  border-radius: 18px;
  margin-bottom: 12px;
  box-shadow: var(--shadow-soft);
}

.chat-bubble.assistant {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(122, 104, 86, 0.12);
}

.chat-bubble.user {
  margin-left: auto;
  color: #ffffff;
  background: linear-gradient(135deg, #b85c38, #8f3f22);
}

.bubble-head,
.bubble-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.bubble-head {
  justify-content: space-between;
  margin-bottom: 8px;
}

.bubble-role,
.bubble-time {
  font-size: 12px;
  opacity: 0.82;
}

.bubble-scope {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.2);
}

.chat-bubble.assistant .bubble-scope {
  background: rgba(245, 239, 228, 0.92);
  color: #64584d;
}

.bubble-content,
.summary-blurb {
  white-space: pre-wrap;
  line-height: 1.85;
}

.markdown-body {
  white-space: normal;
}

.markdown-body :deep(p) {
  margin: 0 0 12px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.bubble-citations,
.summary-points {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.citation-chip,
.point-chip {
  padding: 6px 10px;
  border-radius: 999px;
  border: 0;
  font-size: 12px;
}

.citation-chip {
  cursor: pointer;
  background: rgba(255, 255, 255, 0.84);
  color: var(--text-soft);
}

.point-chip {
  background: rgba(245, 239, 228, 0.92);
  color: #5f5349;
}

.summary-highlight {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 247, 238, 0.94), rgba(255, 255, 255, 0.92));
  border: 1px solid rgba(184, 92, 56, 0.14);
}

.summary-highlight span {
  color: var(--muted);
}

.knowledge-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(122, 104, 86, 0.14);
  background: linear-gradient(180deg, rgba(255, 253, 249, 0.98), rgba(248, 243, 236, 0.94));
}

.full-width-knowledge {
  width: 100%;
}

.knowledge-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 10px;
}

.knowledge-head h4 {
  margin: 6px 0 0;
  font-size: 22px;
}

.knowledge-count {
  padding: 8px 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  color: var(--muted);
  font-size: 12px;
}

.summary-table {
  border-radius: 12px;
  overflow: hidden;
}

.learning-list {
  margin: 0;
  padding-left: 20px;
  line-height: 1.85;
}

.learning-list li + li {
  margin-top: 8px;
}

.mind-map-shell {
  overflow-x: auto;
  padding: 8px 0 2px;
}

.mind-map-root {
  display: flex;
  justify-content: center;
  min-width: fit-content;
  margin: 0;
  padding: 0 8px;
}

@media (max-width: 1180px) {
  .records-content-grid,
  .compare-grid,
  .copy-grid {
    grid-template-columns: 1fr;
  }

  .records-sidebar {
    top: 8px;
    left: 8px;
    width: min(320px, calc(100vw - 16px));
    max-height: none;
  }
}

@media (max-width: 768px) {
  .slide-select {
    min-width: 100%;
  }

  .slide-canvas {
    min-height: 210px;
  }
}
</style>



