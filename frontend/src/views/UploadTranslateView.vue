<template>
  <div class="workspace-view">
    <section class="editor-grid">
      <div class="page-card upload-panel">
        <div class="section-heading">
          <div class="section-kicker">Upload</div>
          <h3>上传</h3>
          <p>支持 `.ppt`、`.pptx` 与 `.pdf`。解析完成后，系统会自动把该课件接入下方的翻译、问答和总结模块。</p>
        </div>

        <el-form label-position="top">
          <el-form-item label="课件文件">
            <label class="file-dropzone">
              <input class="file-input" type="file" accept=".ppt,.pptx,.pdf" @change="onFileChange" />
              <div class="dropzone-label">拖入文件，或点击重新选择</div>
              <div class="dropzone-file">{{ file?.name || "尚未选择文件" }}</div>
            </label>
          </el-form-item>

          <div class="toolbar">
            <el-button type="primary" :loading="uploading" @click="uploadFile">上传并解析</el-button>
            <el-button type="success" :loading="translating" :disabled="!selectedCoursewareId" @click="translateCurrent">
              开始翻译
            </el-button>
          </div>
        </el-form>
      </div>

      <div class="page-card status-panel">
        <div class="section-heading">
          <div class="section-kicker">Status</div>
          <h3>任务状态</h3>
          <p>这里会持续同步当前课件的处理进度。翻译完成后，逐页预览区会自动更新。</p>
        </div>

        <div class="status-chip" :class="statusClass">{{ statusLabel }}</div>

        <div class="status-list">
          <div class="status-item">
            <span>课件标题</span>
            <strong>{{ selectedCoursewareTitle || "等待解析" }}</strong>
          </div>
          <div class="status-item">
            <span>已选文件</span>
            <strong>{{ file?.name || "未选择" }}</strong>
          </div>
          <div class="status-item">
            <span>当前页面</span>
            <strong>{{ currentSlide ? `第 ${currentSlide.slide_no} 页` : "暂无" }}</strong>
          </div>
          <div class="status-item">
            <span>最近更新</span>
            <strong>{{ formatDate(updatedAt) }}</strong>
          </div>
          <div class="status-item">
            <span>翻译进度</span>
            <strong>{{ translationProgress.translated }} / {{ translationProgress.total || slides.length || "-" }}</strong>
          </div>
          <div class="status-item">
            <span>预估剩余时间</span>
            <strong>{{ estimatedTimeRemaining }}</strong>
          </div>
        </div>

        <div class="status-note">
          <strong>当前说明</strong>
          <p>{{ statusDescription }}</p>
          <ul class="status-tips">
            <li v-for="(tip, index) in statusTips" :key="`tip-${index}`">{{ tip }}</li>
          </ul>
        </div>
      </div>
    </section>

    <section id="translate-section" class="page-card compare-panel">
      <div class="panel-head">
        <div>
          <div class="section-kicker">Translation Preview</div>
          <h3>翻译预览</h3>
          <p>左侧查看原始页面，右侧查看中文成品页，同时保留提取文本与备注信息，方便逐页检查。</p>
        </div>

        <div class="panel-actions">
          <el-button :loading="exportingPpt" :disabled="!selectedCoursewareId || coursewareStatus !== 'translated'" @click="downloadTranslatedPpt">
            导出翻译文件
          </el-button>
          <div class="scope-badge">
            <span>当前页</span>
            <strong>{{ currentSlide?.slide_no ?? "-" }} / {{ slides.length || "-" }}</strong>
          </div>
          <div class="slide-jump">
            <el-input-number
              v-model="jumpSlideNo"
              class="slide-jump-input"
              :min="1"
              :max="Math.max(slides.length, 1)"
              :controls="false"
              :step="1"
              :precision="0"
              size="small"
              :disabled="slides.length === 0"
            />
            <el-button size="small" :disabled="slides.length === 0" @click="jumpToSlide">跳转</el-button>
          </div>
          <el-button-group>
            <el-button :disabled="currentSlideIndex <= 0" @click="prevSlide">上一页</el-button>
            <el-button :disabled="currentSlideIndex >= slides.length - 1" @click="nextSlide">下一页</el-button>
          </el-button-group>
        </div>
      </div>

      <div v-if="!currentSlide" class="compare-empty">
        还没有可预览的课件内容。先上传一个课件，或者在右上方切换到现有课件。
      </div>

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
            <div class="copy-content">{{ currentSlide.source_text || "当前页未提取到文本。" }}</div>
          </div>

          <div class="copy-card">
            <div class="copy-label">中文翻译文本</div>
            <div class="copy-content">{{ currentSlide.translated_text || "翻译尚未完成，稍后会自动刷新。" }}</div>
          </div>

          <div class="copy-card full">
            <div class="copy-head">
              <div class="copy-label">讲师备注 / Notes</div>
              <div class="copy-actions">
                <el-button plain size="small" :loading="notesTranslationLoading" :disabled="!currentSlide.notes" @click="translateCurrentNotes">
                  翻译备注
                </el-button>
                <el-checkbox v-model="showTranslatedNotes" :disabled="!canShowTranslatedNotes">显示中文备注</el-checkbox>
              </div>
            </div>
            <div class="copy-content">{{ currentNotesContent || "当前页没有备注信息。" }}</div>
          </div>
        </div>
      </template>
    </section>

    <section id="qa-section" class="page-card qa-panel">
      <div class="panel-head">
        <div>
          <div class="section-kicker">Smart Q&A</div>
          <h3>问答模块</h3>
          <p>默认围绕当前页作答，并参考整份课件中的相关内容；勾选“整体问答”后，则直接基于整份课件回答。</p>
        </div>

        <div class="panel-actions">
          <div class="scope-badge">
            <span>问答范围</span>
            <strong>{{ useGlobalScope ? "整份课件" : currentSlide ? `第 ${currentSlide.slide_no} 页` : "未选择页面" }}</strong>
          </div>
          <el-checkbox v-model="useGlobalScope">整体问答</el-checkbox>
          <el-button plain @click="clearChat">清空对话</el-button>
        </div>
      </div>

      <div class="chat-shell">
        <div v-for="(msg, idx) in messages" :key="idx" class="chat-bubble" :class="msg.role">
          <div class="bubble-head">
            <div class="bubble-role">{{ msg.role === "user" ? "你" : "助教" }}</div>
            <div class="bubble-head-actions">
              <div v-if="msg.scopeLabel" class="bubble-scope">{{ msg.scopeLabel }}</div>
              <el-button v-if="msg.role === 'assistant'" text size="small" class="copy-message-btn" @click="copyMessage(msg.content)">
                复制
              </el-button>
            </div>
          </div>

          <div v-if="msg.role === 'assistant'" class="bubble-content markdown-body" v-html="renderMarkdown(msg.content)"></div>
          <div v-else class="bubble-content">{{ msg.content }}</div>

          <div v-if="msg.citations?.length" class="bubble-citations">
            <span v-for="citation in msg.citations" :key="`${idx}-${citation.slide_no}`" class="citation-chip">
              引用第 {{ citation.slide_no }} 页
            </span>
          </div>
        </div>
      </div>

      <el-input
        v-model="question"
        type="textarea"
        :rows="4"
        maxlength="1000"
        show-word-limit
        @keydown="handleQuestionKeydown"
        placeholder="例如：这一页为什么要引入 Attention 机制？"
      />

      <div class="toolbar">
        <el-button type="primary" :loading="qaLoading" @click="submitQuestion">发送问题</el-button>
      </div>
    </section>

    <section id="summary-section" class="page-card summary-panel">
      <div class="panel-head">
        <div>
          <div class="section-kicker">Deck Summary</div>
          <h3>课件总结</h3>
          <p>适合在逐页阅读后做整体回顾，把关键知识点、术语和课程结构统一收束起来。</p>
        </div>

        <div class="toolbar">
          <el-button type="primary" :loading="summaryLoading" @click="generateSummary">生成整体总结</el-button>
          <el-tag v-if="summary" type="success" round>已生成</el-tag>
        </div>
      </div>

      <el-empty v-if="!summary" description="还没有生成整份课件总结" />

      <div v-else class="summary-layout">
        <section class="summary-card warm">
          <div class="card-kicker">Chapter Snapshot</div>
          <h4>章节摘要</h4>
          <p class="summary-text">{{ summary.chapter_summary }}</p>
        </section>

        <section class="summary-card cool">
          <div class="card-kicker">Key Points</div>
          <h4>重点清单</h4>
          <ul class="points">
            <li v-for="(item, idx) in summary.key_points" :key="idx">{{ item }}</li>
          </ul>
        </section>

        <section class="summary-card full">
          <div class="card-kicker">Glossary</div>
          <h4>术语对照</h4>
          <el-table :data="summary.term_pairs" border class="summary-table">
            <el-table-column prop="en" label="英文术语" min-width="220" />
            <el-table-column prop="zh" label="中文释义" min-width="220" />
          </el-table>
        </section>

        <section class="summary-card full">
          <div class="card-kicker">Study Suggestions</div>
          <h4>学习建议</h4>
          <el-empty v-if="!summary.learning_suggestions?.length" description="暂未生成学习建议" />
          <ul v-else class="points">
            <li v-for="(item, idx) in summary.learning_suggestions" :key="`suggestion-${idx}`">{{ item }}</li>
          </ul>
        </section>

        <section class="summary-card full mind-map-card">
          <div class="card-kicker">Mind Map</div>
          <h4>课程思维导图</h4>
          <div class="mind-map-shell">
            <ul class="mind-map-root">
              <MindMapNode :node="summary.mind_map" />
            </ul>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import MarkdownIt from "markdown-it";
import MindMapNode from "../components/MindMapNode.vue";
import { http } from "../api/client";
import type { CoursewareItem, SlideItem, SlideLayout, SlideLayoutBlock } from "../types";

const emit = defineEmits<{
  "courseware-updated": [];
}>();

interface Citation {
  slide_no: number;
  snippet: string;
}

interface ChatMessageItem {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  scopeLabel?: string;
}

interface SummaryPayload {
  chapter_summary: string;
  key_points: string[];
  term_pairs: Array<{ en: string; zh: string }>;
  learning_suggestions: string[];
  mind_map: {
    title: string;
    children?: Array<any>;
  };
}

const selectionEventName = "courseware-selection-changed";
const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: true,
  typographer: false,
});

const file = ref<File | null>(null);
const uploading = ref(false);
const translating = ref(false);
const qaLoading = ref(false);
const summaryLoading = ref(false);
const notesTranslationLoading = ref(false);
const exportingPpt = ref(false);
const slides = ref<SlideItem[]>([]);
const currentSlideIndex = ref(0);
const jumpSlideNo = ref<number | null>(null);
const selectedCoursewareId = ref<number | undefined>(undefined);
const selectedCoursewareTitle = ref("");
const coursewareStatus = ref<CoursewareItem["status"] | "idle">("idle");
const lastErrorMessage = ref("");
const updatedAt = ref<string>("");
const translationProgress = ref({ total: 0, translated: 0, rendered: 0 });
const translationStartedAt = ref<number | null>(null);
const question = ref("");
const useGlobalScope = ref(true);
const showTranslatedNotes = ref(false);
const summary = ref<SummaryPayload | null>(null);
const messages = ref<ChatMessageItem[]>([
  {
    role: "assistant",
    content: "选择课件后即可提问。默认会围绕当前页回答；勾选“整体问答”后，会改为基于整份课件回答。",
  },
]);

const currentSlide = computed(() => slides.value[currentSlideIndex.value]);
const translatedPreviewUrl = computed(() => currentSlide.value?.processed_image_url || "");
const currentNotesContent = computed(() => {
  if (!currentSlide.value) {
    return "";
  }
  if (showTranslatedNotes.value && currentSlide.value.translated_notes) {
    return currentSlide.value.translated_notes;
  }
  return currentSlide.value.notes || "";
});
const canShowTranslatedNotes = computed(() => Boolean(currentSlide.value?.translated_notes));
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

const processedSlides = computed(() => Math.max(Number(translationProgress.value.translated || 0), 0));

const formatDuration = (totalSeconds: number) => {
  const sec = Math.max(Math.floor(totalSeconds), 0);
  const hours = Math.floor(sec / 3600);
  const minutes = Math.floor((sec % 3600) / 60);
  const seconds = sec % 60;
  if (hours > 0) return `${hours}小时${minutes}分钟`;
  if (minutes > 0) return `${minutes}分钟${seconds}秒`;
  return `${seconds}秒`;
};

const estimatedTimeRemaining = computed(() => {
  if (coursewareStatus.value !== "translating") {
    return "-";
  }
  if (!translationStartedAt.value) {
    return "估算中";
  }
  const done = processedSlides.value;
  const total = Number(translationProgress.value.total || 0);
  const pending = Math.max(total - done, 0);
  if (pending <= 0) {
    return "即将完成";
  }
  if (done <= 0) {
    return "估算中";
  }
  const elapsedSeconds = Math.max((Date.now() - translationStartedAt.value) / 1000, 1);
  const speed = done / elapsedSeconds;
  if (speed <= 0.01) {
    return "估算中";
  }
  return formatDuration(pending / speed);
});

const statusLabel = computed(() => {
  const statusMap: Record<string, string> = {
    idle: "等待开始",
    uploaded: "已上传，待翻译",
    translating: "翻译进行中",
    translated: "翻译完成",
    failed: "翻译失败",
  };
  return statusMap[coursewareStatus.value] || "等待开始";
});

const statusClass = computed(() => {
  const status = coursewareStatus.value;
  if (status === "translated") return "is-success";
  if (status === "translating") return "is-warning";
  if (status === "failed") return "is-danger";
  return "is-neutral";
});

const statusDescription = computed(() => {
  if (coursewareStatus.value === "translating") {
    return "系统正在后台逐页翻译并生成中文预览图。若页面中断或轮询停止，可再次点击“开始翻译”继续显示进度。";
  }
  if (coursewareStatus.value === "translated") {
    return "翻译已经完成。现在可以逐页检查提取与翻译内容，并继续使用下方的问答和总结模块。";
  }
  if (coursewareStatus.value === "failed") {
    if (lastErrorMessage.value) {
      return `本次翻译任务执行失败：${lastErrorMessage.value}`;
    }
    return "本次翻译任务执行失败。可以点击“开始翻译”重新发起，系统会尽量从当前进度继续。";
  }
  if (coursewareStatus.value === "uploaded") {
    return "课件已成功解析，下一步可以直接开始翻译。";
  }
  return "选择现有课件或上传新课件后，这里会显示更详细的任务进度。";
});

const statusTips = computed(() => {
  const translatedCount = Number(translationProgress.value.translated || 0);
  const totalCount = Number(translationProgress.value.total || slides.value.length || 0);

  if (coursewareStatus.value === "translating") {
    return [
      "翻译在后台执行，切换页面后再回来也可以继续查看。",
      "如果进度长时间不变，可点击“开始翻译”继续轮询，不会清空已完成页。",
      estimatedTimeRemaining.value === "估算中"
        ? "系统会在处理了更多页面后给出更稳定的剩余时间估算。"
        : `当前预估剩余时间：${estimatedTimeRemaining.value}。`,
    ];
  }

  if (coursewareStatus.value === "failed") {
    return [
      translatedCount > 0
        ? `本次已完成 ${translatedCount} / ${totalCount || "-"} 页，可点击“开始翻译”继续后续页面。`
        : "可点击“开始翻译”重试当前课件。",
      "若多次失败，建议检查 API Key、模型配置和网络连接后再试。",
    ];
  }

  if (coursewareStatus.value === "translated") {
    return [
      "可使用“当前页”跳转快速抽查关键页面。",
      "如需覆盖更新翻译内容，可再次点击“开始翻译”。",
    ];
  }

  if (coursewareStatus.value === "uploaded") {
    return [
      "课件解析完成后可直接开始翻译。",
      "页数较多时可先启动翻译，再在下方预览区边处理边检查。",
    ];
  }

  return ["请先上传或选择一个课件，然后点击“开始翻译”启动任务。"];
});

const getSelectedCoursewareId = () => {
  const stored = localStorage.getItem("selected_courseware_id");
  return stored ? Number(stored) : undefined;
};

const formatDate = (value: string) => {
  if (!value) return "暂无";
  return new Date(value).toLocaleString("zh-CN");
};

const onFileChange = (event: Event) => {
  const target = event.target as HTMLInputElement;
  file.value = target.files?.[0] || null;
};

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

const renderMarkdown = (content: string) => markdown.render(content || "");

const normalizeMindMap = (node: any, fallbackTitle = "课程全景"): SummaryPayload["mind_map"] => {
  if (!node || typeof node !== "object") {
    return { title: fallbackTitle, children: [] };
  }
  const title = String(node.title || "").trim() || fallbackTitle;
  const children = Array.isArray(node.children)
    ? node.children.slice(0, 10).map((item: any) => normalizeMindMap(item, "主题"))
    : [];
  return { title, children };
};

const normalizeSummaryPayload = (payload: any): SummaryPayload => ({
  chapter_summary: String(payload?.chapter_summary || "总结已生成。"),
  key_points: Array.isArray(payload?.key_points) ? payload.key_points.map((item: any) => String(item)) : [],
  term_pairs: Array.isArray(payload?.term_pairs)
    ? payload.term_pairs
        .map((item: any) => ({
          en: String(item?.en || ""),
          zh: String(item?.zh || ""),
        }))
        .filter((item: { en: string; zh: string }) => item.en || item.zh)
    : [],
  learning_suggestions: Array.isArray(payload?.learning_suggestions)
    ? payload.learning_suggestions.map((item: any) => String(item || "").trim()).filter((item: string) => item)
    : [],
  mind_map: normalizeMindMap(payload?.mind_map, selectedCoursewareTitle.value || "课程全景"),
});

const resetLearningPanels = () => {
  summary.value = null;
  question.value = "";
  useGlobalScope.value = true;
  showTranslatedNotes.value = false;
  messages.value = [
    {
      role: "assistant",
      content: "选择课件后即可提问。默认会围绕当前页回答；勾选“整体问答”后，会改为基于整份课件回答。",
    },
  ];
};

const refreshCoursewareStatus = async (coursewareId: number) => {
  try {
    const { data } = await http.get(`/coursewares/${coursewareId}/status`);
    coursewareStatus.value = data.status;
    if (data.status !== "translating") {
      translationStartedAt.value = null;
    }
    selectedCoursewareTitle.value = data.title || "";
    lastErrorMessage.value = data.last_error || "";
    updatedAt.value = data.updated_at || "";
    translationProgress.value = {
      total: Number(data?.total_slides ?? slides.value.length ?? 0),
      translated: Number(data?.translated_slides ?? 0),
      rendered: Number(data?.rendered_slides ?? 0),
    };
    return data;
  } catch {
    coursewareStatus.value = "idle";
    translationStartedAt.value = null;
    selectedCoursewareTitle.value = "";
    lastErrorMessage.value = "";
    updatedAt.value = "";
    translationProgress.value = {
      total: slides.value.length,
      translated: 0,
      rendered: 0,
    };
    return null;
  }
};

const loadSlides = async (coursewareId: number) => {
  const prevSlideNo = currentSlide.value?.slide_no;
  const { data } = await http.get<SlideItem[]>(`/coursewares/${coursewareId}/slides`);
  slides.value = data;
  if (prevSlideNo != null) {
    const idx = slides.value.findIndex((slide) => slide.slide_no === prevSlideNo);
    currentSlideIndex.value = idx >= 0 ? idx : 0;
  } else {
    currentSlideIndex.value = 0;
  }
  jumpSlideNo.value = currentSlide.value?.slide_no ?? null;
};

const ensureVisibleTranslatedSlide = () => {
  const current = currentSlide.value;
  const currentReady = Boolean(
    current?.translation_done ||
      current?.translated_text?.trim() ||
      (current?.translated_layout?.blocks?.length ?? 0)
  );
  if (currentReady) {
    return;
  }
  const nextReadyIndex = slides.value.findIndex(
    (slide) =>
      Boolean(
        slide.translation_done ||
          slide.translated_text?.trim() ||
          (slide.translated_layout?.blocks?.length ?? 0)
      )
  );
  if (nextReadyIndex >= 0) {
    currentSlideIndex.value = nextReadyIndex;
  }
};

const hydrateCurrentCourseware = async () => {
  selectedCoursewareId.value = getSelectedCoursewareId();
  if (!selectedCoursewareId.value) {
    slides.value = [];
    coursewareStatus.value = "idle";
    translationStartedAt.value = null;
    selectedCoursewareTitle.value = "";
    lastErrorMessage.value = "";
    updatedAt.value = "";
    resetLearningPanels();
    return;
  }

  resetLearningPanels();
  await Promise.all([loadSlides(selectedCoursewareId.value), refreshCoursewareStatus(selectedCoursewareId.value)]);
};

const prevSlide = () => {
  if (currentSlideIndex.value > 0) {
    currentSlideIndex.value -= 1;
  }
};

const nextSlide = () => {
  if (currentSlideIndex.value < slides.value.length - 1) {
    currentSlideIndex.value += 1;
  }
};

const jumpToSlide = () => {
  if (!slides.value.length) {
    return;
  }
  const targetNo = Number(jumpSlideNo.value);
  if (!Number.isFinite(targetNo) || targetNo <= 0) {
    ElMessage.warning("请输入有效页码");
    return;
  }
  const targetIndex = slides.value.findIndex((slide) => slide.slide_no === targetNo);
  if (targetIndex < 0) {
    ElMessage.warning(`未找到第 ${targetNo} 页，请确认页码范围`);
    return;
  }
  currentSlideIndex.value = targetIndex;
};

const translateCurrentNotes = async () => {
  const selected = getSelectedCoursewareId();
  const slide = currentSlide.value;
  if (!selected || !slide) {
    ElMessage.warning("请先选择课件页面");
    return;
  }
  if (!slide.notes?.trim()) {
    ElMessage.warning("当前页没有备注可翻译");
    return;
  }

  notesTranslationLoading.value = true;
  try {
    const { data } = await http.post(`/coursewares/${selected}/slides/${slide.slide_no}/translate-notes`);
    const target = slides.value.find((item) => item.slide_no === slide.slide_no);
    if (target) {
      target.translated_notes = data.translated_notes || "";
    }
    showTranslatedNotes.value = true;
    ElMessage.success("备注翻译完成");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "备注翻译失败");
  } finally {
    notesTranslationLoading.value = false;
  }
};

const uploadFile = async () => {
  if (!file.value) {
    ElMessage.warning("请先选择课件文件");
    return;
  }

  uploading.value = true;
  const formData = new FormData();
  formData.append("file", file.value);

  try {
    const { data } = await http.post("/coursewares/upload", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    localStorage.setItem("selected_courseware_id", String(data.courseware_id));
    selectedCoursewareId.value = data.courseware_id;
    selectedCoursewareTitle.value = data.title || "";
    coursewareStatus.value = "uploaded";
    translationStartedAt.value = null;
    lastErrorMessage.value = "";
    updatedAt.value = new Date().toISOString();
    translationProgress.value = { total: Number(data.slide_count || 0), translated: 0, rendered: 0 };
    resetLearningPanels();
    await loadSlides(data.courseware_id);
    emit("courseware-updated");
    window.dispatchEvent(new CustomEvent(selectionEventName, { detail: data.courseware_id }));
    ElMessage.success(`上传成功，已解析 ${data.slide_count} 页内容`);
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "上传失败");
  } finally {
    uploading.value = false;
  }
};

const translateCurrent = async () => {
  const selected = getSelectedCoursewareId();
  if (!selected) {
    ElMessage.warning("请先上传或选择一个课件");
    return;
  }

  translating.value = true;
  coursewareStatus.value = "translating";
  lastErrorMessage.value = "";
  translationStartedAt.value = Date.now();

  try {
    const forceSuffix = coursewareStatus.value === "translated" ? "?force=1" : "";
    await http.post(`/coursewares/${selected}/translate${forceSuffix}`);

    const startedAt = Date.now();
    const pollIntervalMs = 1500;
    const initialStatus = await refreshCoursewareStatus(selected);
    const totalSlides = Number(initialStatus?.total_slides ?? slides.value.length ?? 0);
    const timeoutMs = Math.min(
      Math.max(totalSlides * 45000, 20 * 60 * 1000),
      4 * 60 * 60 * 1000
    );
    let lastLoadedTranslated = Number(initialStatus?.translated_slides ?? -1);

    while (Date.now() - startedAt < timeoutMs) {
      const statusData = await refreshCoursewareStatus(selected);
      const currentStatus = (statusData?.status as CoursewareItem["status"] | undefined) || coursewareStatus.value;
      const translatedSlides = Number(statusData?.translated_slides ?? 0);
      const shouldRefreshSlides = translatedSlides > lastLoadedTranslated || currentStatus === "translated";
      if (shouldRefreshSlides) {
        await loadSlides(selected);
        lastLoadedTranslated = translatedSlides;
        if (currentStatus === "translating") {
          ensureVisibleTranslatedSlide();
        }
      }

      if (currentStatus === "translated") {
        await loadSlides(selected);
        translationStartedAt.value = null;
        emit("courseware-updated");
        ElMessage.success("翻译完成，预览内容已刷新");
        return;
      }

      if (currentStatus === "failed") {
        translationStartedAt.value = null;
        const failedReason = String(statusData?.last_error || "").trim();
        throw new Error(failedReason || "翻译任务失败");
      }

      await new Promise((resolve) => setTimeout(resolve, pollIntervalMs));
    }

    throw new Error("翻译超时，请稍后重试");
  } catch (error: any) {
    const message = error?.response?.data?.detail || error?.message || "翻译失败";
    if (message.includes("翻译超时")) {
      await refreshCoursewareStatus(selected);
      if (coursewareStatus.value === "translating") {
        ElMessage.warning("任务仍在后台继续执行，请稍后重试或再次点击开始翻译继续轮询");
        return;
      }
    }
    if (coursewareStatus.value === "failed") {
      ElMessage.error(message);
      return;
    }
    ElMessage.error(message);
  } finally {
    translating.value = false;
  }
};

const downloadTranslatedPpt = async () => {
  const selected = getSelectedCoursewareId();
  if (!selected) {
    ElMessage.warning("请先上传或选择课件");
    return;
  }
  if (coursewareStatus.value !== "translated") {
    ElMessage.warning("请在翻译完成后再导出");
    return;
  }

  try {
    await ElMessageBox.confirm(
      "导出后的文件可能存在英汉文字交叠、字迹不清或个别排版偏移。建议导出后快速检查关键页面并按需微调。是否继续导出？",
      "导出提示",
      {
        confirmButtonText: "继续导出",
        cancelButtonText: "取消",
        type: "warning",
      }
    );
  } catch {
    return;
  }

  exportingPpt.value = true;
  try {
    const response = await http.get(`/coursewares/${selected}/export-translated-ppt`, {
      responseType: "blob",
    });
    const disposition = String(response.headers?.["content-disposition"] || "");
    const utf8Match = disposition.match(/filename\*=UTF-8''([^;]+)/i);
    const plainMatch = disposition.match(/filename="?([^\";]+)"?/i);
    const rawFilename = utf8Match?.[1] || plainMatch?.[1] || `courseware_${selected}_translated`;
    const filename = decodeURIComponent(rawFilename);
    const expectedMime = filename.toLowerCase().endsWith(".pdf")
      ? "application/pdf"
      : "application/vnd.openxmlformats-officedocument.presentationml.presentation";
    const serverBlob = response.data as Blob;
    const blob =
      serverBlob?.type && serverBlob.type !== "application/xml" && serverBlob.type !== "text/xml"
        ? serverBlob
        : new Blob([serverBlob], { type: expectedMime });

    const link = document.createElement("a");
    const href = URL.createObjectURL(blob);
    link.href = href;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(href);
    ElMessage.success("翻译文件导出成功");
  } catch (error: any) {
    let detail = "导出失败";
    const payload = error?.response?.data;
    if (payload instanceof Blob) {
      try {
        const text = await payload.text();
        const parsed = JSON.parse(text);
        detail = parsed?.detail || detail;
      } catch {
        detail = detail;
      }
    } else {
      detail = error?.response?.data?.detail || detail;
    }
    ElMessage.error(detail);
  } finally {
    exportingPpt.value = false;
  }
};

const clearChat = () => {
  messages.value = [
    {
      role: "assistant",
      content: "对话已清空。现在可以重新提问，我会继续根据当前设置的范围回答。",
    },
  ];
};

const copyMessage = async (content: string) => {
  try {
    await navigator.clipboard.writeText(content || "");
    ElMessage.success("回复内容已复制");
  } catch {
    ElMessage.error("复制失败，请重试");
  }
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
  const selected = Number(localStorage.getItem("selected_courseware_id"));
  if (!selected) {
    ElMessage.warning("请先在右上方选择课件");
    return;
  }
  if (!question.value.trim()) {
    ElMessage.warning("请输入问题内容");
    return;
  }
  if (!useGlobalScope.value && !currentSlide.value) {
    ElMessage.warning("当前没有可用页面");
    return;
  }

  const q = question.value.trim();
  const scopeLabel = useGlobalScope.value ? "整份课件" : `第 ${currentSlide.value?.slide_no} 页`;
  messages.value.push({ role: "user", content: q, scopeLabel });
  question.value = "";
  qaLoading.value = true;

  try {
    const history = messages.value
      .slice(0, -1)
      .filter((item) => item.role === "user" || item.role === "assistant")
      .map((item) => ({ role: item.role, content: item.content }));

    const { data } = await http.post(`/coursewares/${selected}/qa`, {
      question: q,
      slide_no: useGlobalScope.value ? undefined : currentSlide.value?.slide_no,
      use_global_scope: useGlobalScope.value,
      history,
    });
    messages.value.push({
      role: "assistant",
      content: data.answer,
      citations: data.citations,
      scopeLabel,
    });
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "提问失败");
  } finally {
    qaLoading.value = false;
  }
};

const generateSummary = async () => {
  const selected = Number(localStorage.getItem("selected_courseware_id"));
  if (!selected) {
    ElMessage.warning("请先在右上方选择课件");
    return;
  }
  summaryLoading.value = true;
  try {
    const { data } = await http.post(`/coursewares/${selected}/summary`, {});
    summary.value = normalizeSummaryPayload(data);
    ElMessage.success("整体总结生成完成");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "生成总结失败");
  } finally {
    summaryLoading.value = false;
  }
};

const handleCoursewareChange = async () => {
  try {
    await hydrateCurrentCourseware();
  } catch {
    ElMessage.error("课件内容加载失败");
  }
};

onMounted(async () => {
  window.addEventListener(selectionEventName, handleCoursewareChange as EventListener);
  await handleCoursewareChange();
});

watch(currentSlide, (slide) => {
  jumpSlideNo.value = slide?.slide_no ?? null;
  if (!slide?.translated_notes) {
    showTranslatedNotes.value = false;
  }
});

onUnmounted(() => {
  window.removeEventListener(selectionEventName, handleCoursewareChange as EventListener);
});
</script>

<style scoped>
.workspace-view {
  display: grid;
  gap: 22px;
}

.section-kicker,
.card-kicker {
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 700;
}

.editor-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.92fr) minmax(360px, 1.08fr);
  gap: 20px;
}

.section-heading h3,
.panel-head h3 {
  margin: 10px 0 0;
  font-size: 29px;
  line-height: 1.04;
  letter-spacing: -0.03em;
}

.section-heading p,
.panel-head p {
  margin: 14px 0 0;
  color: var(--muted);
  line-height: 1.88;
  max-width: 70ch;
}

.upload-panel,
.status-panel,
.compare-panel,
.qa-panel,
.summary-panel {
  position: relative;
}

.upload-panel::before,
.status-panel::before,
.compare-panel::before,
.qa-panel::before,
.summary-panel::before {
  content: "";
  position: absolute;
  top: 0;
  left: 26px;
  right: 26px;
  height: 4px;
  border-radius: 999px;
  background: linear-gradient(90deg, rgba(201, 107, 44, 0.8), rgba(22, 106, 109, 0.38), transparent 84%);
}

.upload-panel {
  background:
    radial-gradient(circle at right top, rgba(201, 107, 44, 0.12), transparent 26%),
    linear-gradient(180deg, rgba(255, 252, 247, 0.92), rgba(251, 245, 238, 0.88));
}

.status-panel {
  background:
    radial-gradient(circle at right top, rgba(22, 106, 109, 0.09), transparent 26%),
    linear-gradient(180deg, rgba(251, 254, 253, 0.94), rgba(244, 248, 247, 0.88));
}

.file-dropzone {
  position: relative;
  display: block;
  border: 1px dashed rgba(184, 92, 56, 0.5);
  border-radius: 26px;
  padding: 26px 24px;
  background:
    radial-gradient(circle at right top, rgba(184, 92, 56, 0.14), transparent 30%),
    radial-gradient(circle at left bottom, rgba(22, 106, 109, 0.08), transparent 28%),
    linear-gradient(180deg, rgba(255, 247, 238, 0.92), rgba(255, 253, 249, 0.98));
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.88);
  transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease;
}

.file-dropzone:hover {
  transform: translateY(-1px);
  border-color: rgba(184, 92, 56, 0.7);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.94),
    0 16px 28px rgba(184, 92, 56, 0.08);
}

.file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.dropzone-label {
  font-size: 17px;
  font-weight: 700;
}

.dropzone-file {
  margin-top: 12px;
  color: var(--muted);
  line-height: 1.7;
  font-size: 14px;
}

.status-panel {
  display: flex;
  flex-direction: column;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  margin-top: 20px;
  padding: 11px 18px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 700;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45);
}

.status-chip.is-neutral {
  color: #5f5349;
  background: rgba(234, 225, 214, 0.84);
}

.status-chip.is-warning {
  color: #8f3f22;
  background: rgba(243, 213, 191, 0.9);
}

.status-chip.is-success {
  color: #3f533b;
  background: rgba(219, 227, 213, 0.92);
}

.status-chip.is-danger {
  color: #7f1d1d;
  background: rgba(254, 226, 226, 0.92);
}

.status-list {
  margin-top: 20px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.status-item {
  display: grid;
  gap: 12px;
  padding: 14px 15px;
  border-radius: 18px;
  border: 1px solid rgba(122, 104, 86, 0.1);
  background: rgba(255, 255, 255, 0.72);
  line-height: 1.6;
  min-height: 92px;
}

.status-item span {
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  font-weight: 700;
}

.status-item strong {
  text-align: left;
  font-size: 17px;
  line-height: 1.45;
}

.status-note {
  margin-top: 20px;
  padding: 20px;
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 252, 247, 0.96), rgba(248, 242, 233, 0.88));
  border: 1px solid rgba(122, 104, 86, 0.12);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.status-note strong {
  display: block;
  margin-bottom: 10px;
}

.status-note p {
  margin: 0;
  color: var(--muted);
  line-height: 1.85;
}

.status-tips {
  margin: 12px 0 0;
  padding-left: 18px;
  color: var(--text-soft);
  line-height: 1.75;
}

.status-tips li + li {
  margin-top: 6px;
}

.compare-panel,
.qa-panel,
.summary-panel {
  display: grid;
  gap: 20px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  flex-wrap: wrap;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(98, 115, 136, 0.12);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.scope-badge {
  padding: 12px 14px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(247, 250, 252, 0.78));
  border: 1px solid rgba(122, 104, 86, 0.14);
  color: var(--muted);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.scope-badge span {
  margin-right: 8px;
}

.scope-badge strong {
  color: var(--text);
}

.slide-jump {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.slide-jump-input {
  width: 96px;
}

.compare-empty {
  padding: 44px 24px;
  text-align: center;
  border-radius: 26px;
  color: var(--muted);
  border: 1px dashed rgba(122, 104, 86, 0.28);
  background:
    radial-gradient(circle at top, rgba(201, 107, 44, 0.06), transparent 32%),
    linear-gradient(180deg, rgba(255, 252, 247, 0.76), rgba(255, 255, 255, 0.9));
}

.compare-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.preview-card,
.copy-card,
.summary-card {
  border: 1px solid rgba(122, 104, 86, 0.14);
  background: linear-gradient(180deg, rgba(255, 253, 249, 0.96), rgba(249, 244, 237, 0.92));
}

.preview-card {
  padding: 18px;
  border-radius: 24px;
  box-shadow: 0 16px 28px rgba(17, 32, 49, 0.05);
}

.preview-title {
  margin-bottom: 14px;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-soft);
}

.slide-canvas {
  position: relative;
  overflow: hidden;
  min-height: 420px;
  border-radius: 20px;
  border: 1px solid rgba(122, 104, 86, 0.12);
  background: linear-gradient(180deg, rgba(247, 243, 236, 0.94), rgba(236, 230, 220, 0.84));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.84);
}

.translated-stage {
  background:
    radial-gradient(circle at top right, rgba(212, 168, 95, 0.18), transparent 28%),
    radial-gradient(circle at left bottom, rgba(22, 106, 109, 0.08), transparent 28%),
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
  border-radius: 14px;
  color: var(--text);
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 10px 22px rgba(17, 32, 49, 0.08);
  font-size: 14px;
  z-index: 1;
  border: 1px solid rgba(98, 115, 136, 0.08);
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
  gap: 16px;
}

.copy-card {
  padding: 20px;
  border-radius: 22px;
  box-shadow: 0 12px 22px rgba(17, 32, 49, 0.04);
}

.copy-card.full,
.summary-card.full {
  grid-column: 1 / -1;
}

.copy-label {
  font-size: 13px;
  color: var(--muted);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
}

.copy-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.copy-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.copy-content,
.summary-text {
  white-space: pre-wrap;
  line-height: 1.9;
}

.chat-shell {
  min-height: 44vh;
  max-height: 64vh;
  overflow-y: auto;
  padding: 20px;
  border-radius: 26px;
  border: 1px solid rgba(122, 104, 86, 0.12);
  background:
    radial-gradient(circle at top right, rgba(81, 98, 76, 0.08), transparent 24%),
    radial-gradient(circle at left bottom, rgba(201, 107, 44, 0.05), transparent 28%),
    linear-gradient(180deg, rgba(255, 252, 247, 0.94), rgba(251, 247, 240, 0.98));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.88);
}

.chat-bubble {
  max-width: min(88%, 900px);
  padding: 15px 17px;
  border-radius: 22px;
  margin-bottom: 14px;
  box-shadow: 0 14px 28px rgba(17, 32, 49, 0.07);
}

.chat-bubble.assistant {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(122, 104, 86, 0.12);
}

.chat-bubble.user {
  margin-left: auto;
  color: #ffffff;
  background: linear-gradient(135deg, #c96b2c, #9f4217);
}

.bubble-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.bubble-head-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.bubble-role {
  font-size: 12px;
  opacity: 0.8;
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

.bubble-content {
  white-space: pre-wrap;
  line-height: 1.8;
}

.markdown-body {
  white-space: normal;
}

.copy-message-btn {
  padding: 0 6px;
  min-height: auto;
  color: var(--text-soft);
}

.markdown-body :deep(p) {
  margin: 0 0 12px;
}

.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(code) {
  padding: 0.14em 0.4em;
  border-radius: 8px;
  font-family: "Cascadia Code", "Consolas", monospace;
  font-size: 0.92em;
  background: rgba(236, 230, 220, 0.9);
}

.markdown-body :deep(pre) {
  margin: 12px 0;
  padding: 14px 16px;
  overflow-x: auto;
  border-radius: 16px;
  background: #2c261f;
}

.markdown-body :deep(pre code) {
  padding: 0;
  color: #f8efe2;
  background: transparent;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 8px 0 12px;
  padding-left: 22px;
}

.markdown-body :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 0 8px 14px;
  border-left: 4px solid rgba(184, 92, 56, 0.38);
  color: var(--text-soft);
}

.bubble-citations {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.citation-chip {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: rgba(255, 255, 255, 0.82);
  color: var(--text-soft);
}

.summary-layout {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.summary-card {
  padding: 24px;
  border-radius: 24px;
  box-shadow: 0 14px 28px rgba(17, 32, 49, 0.05);
}

.summary-card.warm {
  background:
    radial-gradient(circle at top right, rgba(212, 168, 95, 0.18), transparent 28%),
    linear-gradient(180deg, rgba(255, 248, 238, 0.94), rgba(255, 253, 249, 0.98));
}

.summary-card.cool {
  background:
    radial-gradient(circle at top right, rgba(81, 98, 76, 0.14), transparent 28%),
    linear-gradient(180deg, rgba(245, 249, 242, 0.94), rgba(255, 253, 249, 0.98));
}

.summary-card.full {
  background: linear-gradient(180deg, rgba(255, 253, 249, 0.98), rgba(248, 243, 236, 0.94));
}

.summary-card h4 {
  margin: 8px 0 12px;
  font-size: 22px;
}

.points {
  margin: 0;
  padding-left: 18px;
}

.points li {
  margin-bottom: 10px;
  line-height: 1.8;
}

.summary-table {
  border-radius: 16px;
  overflow: hidden;
}

.mind-map-card {
  overflow: hidden;
}

.mind-map-shell {
  overflow-x: auto;
  padding: 12px 0 4px;
}

.mind-map-root {
  display: flex;
  justify-content: center;
  min-width: fit-content;
  margin: 0;
  padding: 0 8px;
}

@media (max-width: 1080px) {
  .editor-grid,
  .compare-grid,
  .copy-grid,
  .summary-layout {
    grid-template-columns: 1fr;
  }

  .status-list {
    grid-template-columns: 1fr;
  }

  .slide-canvas {
    min-height: 320px;
  }
}
</style>
