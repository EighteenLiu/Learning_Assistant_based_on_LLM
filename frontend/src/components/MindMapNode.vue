<template>
  <div ref="mapRef" class="knowledge-map" @wheel.prevent="onWheel">
    <div class="knowledge-map__toolbar">
      <button type="button" title="放大" @click="zoomIn">+</button>
      <button type="button" title="缩小" @click="zoomOut">-</button>
      <button type="button" title="重置视图" @click="resetView">1:1</button>
      <button type="button" :title="isFullscreen ? '退出全屏' : '全屏查看'" @click="toggleFullscreen">
        {{ isFullscreen ? "退出" : "全屏" }}
      </button>
    </div>

    <svg
      class="knowledge-map__canvas"
      ref="svgRef"
      :viewBox="viewBox"
      role="img"
      aria-label="课程思维导图"
      @pointerdown="startPan"
      @pointermove="movePan"
      @pointerup="stopPan"
      @pointerleave="stopPan"
    >
      <defs>
        <linearGradient id="mindMapRootGradient" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#236a72" />
          <stop offset="55%" stop-color="#4e6fa8" />
          <stop offset="100%" stop-color="#8469a9" />
        </linearGradient>
        <linearGradient id="mindMapNodeGradient" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#ffffff" />
          <stop offset="100%" stop-color="#eef7f4" />
        </linearGradient>
        <linearGradient id="mindMapBranchGradient" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#fffaf0" />
          <stop offset="100%" stop-color="#f1f0ff" />
        </linearGradient>
        <linearGradient id="mindMapLeafGradient" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#fffdf9" />
          <stop offset="100%" stop-color="#f8efe3" />
        </linearGradient>
        <filter id="mindMapShadow" x="-20%" y="-30%" width="140%" height="160%">
          <feDropShadow dx="0" dy="12" stdDeviation="10" flood-color="#253341" flood-opacity="0.18" />
        </filter>
      </defs>

      <g :transform="canvasTransform">
        <path
          v-for="edge in edges"
          :key="edge.id"
          class="knowledge-map__edge"
          :class="`knowledge-map__edge--depth-${Math.min(edge.depth, 3)}`"
          :d="edge.path"
        />

        <g
          v-for="item in layoutNodes"
          :key="item.id"
          class="knowledge-map__node"
          :class="[
            `knowledge-map__node--depth-${Math.min(item.depth, 3)}`,
            { 'knowledge-map__node--collapsed': item.collapsed },
          ]"
          :transform="`translate(${item.x - item.width / 2}, ${item.y - item.height / 2})`"
          role="button"
          tabindex="0"
          @click="handleNodeClick(item)"
          @keydown.enter.prevent="toggleNode(item)"
          @keydown.space.prevent="toggleNode(item)"
          @pointerdown.stop="startNodeDrag($event, item)"
        >
          <rect
            class="knowledge-map__glow"
            :width="item.width"
            :height="item.height"
            rx="20"
          />
          <rect
            :width="item.width"
            :height="item.height"
            rx="18"
            :class="item.depth === 0 ? 'knowledge-map__rect knowledge-map__rect--root' : 'knowledge-map__rect'"
          />
          <circle
            v-if="item.depth > 0"
            class="knowledge-map__dot"
            :cx="item.depth === 1 ? 18 : 16"
            :cy="item.height / 2"
            :r="item.depth === 1 ? 4.5 : 3.5"
          />
          <text
            class="knowledge-map__text"
            :class="`knowledge-map__text--depth-${Math.min(item.depth, 3)}`"
            :x="item.depth === 0 ? item.width / 2 : 34"
            :y="item.textY"
            :text-anchor="item.depth === 0 ? 'middle' : 'start'"
          >
            <tspan
              v-for="(line, lineIndex) in item.lines"
              :key="`${item.id}-line-${lineIndex}`"
              :x="item.depth === 0 ? item.width / 2 : 34"
              :dy="lineIndex === 0 ? 0 : 21"
            >
              {{ line }}
            </tspan>
          </text>
          <g
            v-if="item.childCount"
            class="knowledge-map__badge"
            :transform="`translate(${item.width - 22}, 22)`"
          >
            <circle r="14" />
            <text text-anchor="middle" dominant-baseline="central">{{ item.collapsed ? "+" : item.childCount }}</text>
          </g>
        </g>
      </g>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";

export interface MindMapNodeData {
  title: string;
  children?: MindMapNodeData[];
}

interface LayoutNode {
  id: string;
  title: string;
  depth: number;
  x: number;
  y: number;
  width: number;
  height: number;
  lines: string[];
  textY: number;
  childCount: number;
  collapsed: boolean;
  source: MindMapNodeData;
}

interface LayoutEdge {
  id: string;
  depth: number;
  path: string;
}

const props = defineProps<{
  node: MindMapNodeData;
}>();

const collapsedIds = ref<Set<string>>(new Set());
const nodeOffsets = ref<Record<string, { x: number; y: number }>>({});
const zoom = ref(1);
const pan = ref({ x: 0, y: 0 });
const dragStart = ref<{ x: number; y: number; panX: number; panY: number } | null>(null);
const nodeDragStart = ref<{
  id: string;
  x: number;
  y: number;
  offsetX: number;
  offsetY: number;
  moved: boolean;
} | null>(null);
const suppressClick = ref(false);
const mapRef = ref<HTMLElement | null>(null);
const svgRef = ref<SVGSVGElement | null>(null);
const isFullscreen = ref(false);

const center = { x: 620, y: 360 };
const baseViewBox = { x: 0, y: 0, width: 1240, height: 720 };

// 实现数据规范化和结构构建，让调用方获得稳定的输出。
const normalizeTitle = (value: unknown, fallback = "课程全景") => {
  const title = String(value || "").replace(/\s+/g, " ").trim();
  return title || fallback;
};

// 实现 measureNode 对应的核心处理，封装输入转换、状态更新或结果返回。
const measureNode = (title: string, depth: number) => {
  const width = depth === 0 ? 250 : depth === 1 ? 210 : 180;
  const estimatedLines = Math.min(3, Math.max(1, Math.ceil(title.length / (depth === 0 ? 13 : 11))));
  return {
    width,
    height: Math.max(depth === 0 ? 76 : 60, estimatedLines * 22 + 28),
  };
};

// 实现 wrapTitle 对应的核心处理，封装输入转换、状态更新或结果返回。
const wrapTitle = (title: string, depth: number) => {
  const limit = depth === 0 ? 12 : depth === 1 ? 10 : 9;
  const normalized = normalizeTitle(title);
  const lines: string[] = [];
  for (let index = 0; index < normalized.length; index += limit) {
    lines.push(normalized.slice(index, index + limit));
    if (lines.length >= 3) {
      break;
    }
  }
  if (normalized.length > limit * 3 && lines.length) {
    lines[lines.length - 1] = `${lines[lines.length - 1].slice(0, Math.max(1, limit - 1))}...`;
  }
  return lines.length ? lines : ["主题"];
};

// 实现 clamp 对应的核心处理，封装输入转换、状态更新或结果返回。
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));

// 实现 polarPoint 对应的核心处理，封装输入转换、状态更新或结果返回。
const polarPoint = (originX: number, originY: number, angle: number, radius: number) => ({
  x: originX + Math.cos(angle) * radius,
  y: originY + Math.sin(angle) * radius,
});

// 实现 branchAngles 对应的核心处理，封装输入转换、状态更新或结果返回。
const branchAngles = (count: number, parentAngle = 0, depth = 1) => {
  if (count <= 1) {
    return [parentAngle];
  }
  if (depth === 1) {
    const start = (-155 * Math.PI) / 180;
    const end = (155 * Math.PI) / 180;
    return Array.from({ length: count }, (_, index) => start + ((end - start) * index) / (count - 1));
  }
  const spread = clamp((34 + count * 16) * (Math.PI / 180), 0.62, depth === 2 ? 1.72 : 1.28);
  const start = parentAngle - spread / 2;
  return Array.from({ length: count }, (_, index) => start + (spread * index) / (count - 1));
};

// 实现 applyManualOffset 对应的核心处理，封装输入转换、状态更新或结果返回。
const applyManualOffset = (id: string, x: number, y: number) => {
  const offset = nodeOffsets.value[id] || { x: 0, y: 0 };
  return {
    x: x + offset.x,
    y: y + offset.y,
  };
};

// 实现数据规范化和结构构建，让调用方获得稳定的输出。
const buildLayout = () => {
  const nodes: LayoutNode[] = [];
  const edges: LayoutEdge[] = [];

  const visit = (
    node: MindMapNodeData,
    id: string,
    depth: number,
    x: number,
    y: number,
    angle: number,
    parent?: LayoutNode,
  ) => {
    const positioned = applyManualOffset(id, x, y);
    const title = normalizeTitle(node?.title, depth === 0 ? "课程全景" : "主题");
    const children = Array.isArray(node?.children) ? node.children.filter(Boolean).slice(0, depth === 0 ? 12 : 7) : [];
    const collapsed = collapsedIds.value.has(id);
    const size = measureNode(title, depth);
    const lines = wrapTitle(title, depth);
    const current: LayoutNode = {
      id,
      title,
      depth,
      x: positioned.x,
      y: positioned.y,
      width: size.width,
      height: size.height,
      lines,
      textY: size.height / 2 - ((lines.length - 1) * 21) / 2 + 5,
      childCount: children.length,
      collapsed,
      source: node,
    };
    nodes.push(current);

    if (parent) {
      const controlDistance = depth === 1 ? 110 : 78;
      const c1 = polarPoint(parent.x, parent.y, angle, controlDistance);
      const c2 = polarPoint(positioned.x, positioned.y, angle + Math.PI, controlDistance);
      edges.push({
        id: `${parent.id}->${id}`,
        depth,
        path: `M ${parent.x} ${parent.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${positioned.x} ${positioned.y}`,
      });
    }

    if (collapsed || depth >= 3 || !children.length) {
      return;
    }

    const radius = depth === 0 ? 335 : depth === 1 ? 255 : 205;
    const angles = branchAngles(children.length, angle, depth + 1);
    children.forEach((child, index) => {
      const childAngle = angles[index];
      const point = polarPoint(positioned.x, positioned.y, childAngle, radius + (index % 2) * 28);
      visit(child, `${id}-${index}`, depth + 1, point.x, point.y, childAngle, current);
    });
  };

  visit(props.node, "root", 0, center.x, center.y, 0);
  return { nodes, edges };
};

const layout = computed(buildLayout);
const layoutNodes = computed(() => layout.value.nodes);
const edges = computed(() => layout.value.edges);

const viewBoxBounds = computed(() => {
  const padding = 140;
  const bounds = layoutNodes.value.reduce(
    (acc, item) => ({
      minX: Math.min(acc.minX, item.x - item.width / 2),
      minY: Math.min(acc.minY, item.y - item.height / 2),
      maxX: Math.max(acc.maxX, item.x + item.width / 2),
      maxY: Math.max(acc.maxY, item.y + item.height / 2),
    }),
    {
      minX: baseViewBox.x,
      minY: baseViewBox.y,
      maxX: baseViewBox.width,
      maxY: baseViewBox.height,
    },
  );
  return {
    x: bounds.minX - padding,
    y: bounds.minY - padding,
    width: bounds.maxX - bounds.minX + padding * 2,
    height: bounds.maxY - bounds.minY + padding * 2,
  };
});

const viewBox = computed(() => {
  const bounds = viewBoxBounds.value;
  return `${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`;
});

const canvasTransform = computed(() => `translate(${pan.value.x} ${pan.value.y}) scale(${zoom.value})`);

// 实现 toggleNode 对应的核心处理，封装输入转换、状态更新或结果返回。
const toggleNode = (item: LayoutNode) => {
  if (!item.childCount) {
    return;
  }
  const next = new Set(collapsedIds.value);
  if (next.has(item.id)) {
    next.delete(item.id);
  } else {
    next.add(item.id);
  }
  collapsedIds.value = next;
};

// 实现 handleNodeClick 对应的核心处理，封装输入转换、状态更新或结果返回。
const handleNodeClick = (item: LayoutNode) => {
  if (suppressClick.value) {
    suppressClick.value = false;
    return;
  }
  toggleNode(item);
};

// 实现 zoomIn 对应的核心处理，封装输入转换、状态更新或结果返回。
const zoomIn = () => {
  zoom.value = clamp(Number((zoom.value + 0.12).toFixed(2)), 0.62, 1.65);
};

// 实现 zoomOut 对应的核心处理，封装输入转换、状态更新或结果返回。
const zoomOut = () => {
  zoom.value = clamp(Number((zoom.value - 0.12).toFixed(2)), 0.62, 1.65);
};

// 实现 resetView 对应的核心处理，封装输入转换、状态更新或结果返回。
const resetView = () => {
  zoom.value = 1;
  pan.value = { x: 0, y: 0 };
  nodeOffsets.value = {};
};

// 实现 syncFullscreenState 对应的核心处理，封装输入转换、状态更新或结果返回。
const syncFullscreenState = () => {
  isFullscreen.value = document.fullscreenElement === mapRef.value;
};

// 实现 toggleFullscreen 对应的核心处理，封装输入转换、状态更新或结果返回。
const toggleFullscreen = async () => {
  if (!mapRef.value) {
    return;
  }
  if (document.fullscreenElement === mapRef.value) {
    await document.exitFullscreen();
    return;
  }
  await mapRef.value.requestFullscreen();
};

// 实现 onWheel 对应的核心处理，封装输入转换、状态更新或结果返回。
const onWheel = (event: WheelEvent) => {
  const delta = event.deltaY > 0 ? -0.08 : 0.08;
  zoom.value = clamp(Number((zoom.value + delta).toFixed(2)), 0.62, 1.65);
};

// 实现 startPan 对应的核心处理，封装输入转换、状态更新或结果返回。
const startPan = (event: PointerEvent) => {
  if (nodeDragStart.value) {
    return;
  }
  dragStart.value = {
    x: event.clientX,
    y: event.clientY,
    panX: pan.value.x,
    panY: pan.value.y,
  };
};

// 实现 clientDeltaToCanvas 对应的核心处理，封装输入转换、状态更新或结果返回。
const clientDeltaToCanvas = (dx: number, dy: number) => {
  const rect = svgRef.value?.getBoundingClientRect();
  if (!rect) {
    return { x: dx / zoom.value, y: dy / zoom.value };
  }
  return {
    x: (dx * viewBoxBounds.value.width) / rect.width / zoom.value,
    y: (dy * viewBoxBounds.value.height) / rect.height / zoom.value,
  };
};

// 实现 startNodeDrag 对应的核心处理，封装输入转换、状态更新或结果返回。
const startNodeDrag = (event: PointerEvent, item: LayoutNode) => {
  const offset = nodeOffsets.value[item.id] || { x: 0, y: 0 };
  nodeDragStart.value = {
    id: item.id,
    x: event.clientX,
    y: event.clientY,
    offsetX: offset.x,
    offsetY: offset.y,
    moved: false,
  };
  const target = event.currentTarget as SVGGraphicsElement;
  target.setPointerCapture?.(event.pointerId);
};

// 实现 movePan 对应的核心处理，封装输入转换、状态更新或结果返回。
const movePan = (event: PointerEvent) => {
  if (nodeDragStart.value) {
    const delta = clientDeltaToCanvas(event.clientX - nodeDragStart.value.x, event.clientY - nodeDragStart.value.y);
    const moved = Math.abs(delta.x) + Math.abs(delta.y) > 3;
    nodeDragStart.value.moved = nodeDragStart.value.moved || moved;
    nodeOffsets.value = {
      ...nodeOffsets.value,
      [nodeDragStart.value.id]: {
        x: nodeDragStart.value.offsetX + delta.x,
        y: nodeDragStart.value.offsetY + delta.y,
      },
    };
    return;
  }
  if (!dragStart.value) {
    return;
  }
  pan.value = {
    x: dragStart.value.panX + (event.clientX - dragStart.value.x) / zoom.value,
    y: dragStart.value.panY + (event.clientY - dragStart.value.y) / zoom.value,
  };
};

// 实现 stopPan 对应的核心处理，封装输入转换、状态更新或结果返回。
const stopPan = () => {
  if (nodeDragStart.value?.moved) {
    suppressClick.value = true;
  }
  nodeDragStart.value = null;
  dragStart.value = null;
};

onMounted(() => {
  document.addEventListener("fullscreenchange", syncFullscreenState);
});

onUnmounted(() => {
  document.removeEventListener("fullscreenchange", syncFullscreenState);
});
</script>

<style scoped>
.knowledge-map {
  position: relative;
  width: 100%;
  min-width: 760px;
  height: clamp(460px, 58vh, 660px);
  overflow: hidden;
  border-radius: 20px;
  border: 1px solid rgba(109, 128, 137, 0.18);
  background:
    radial-gradient(circle at 18% 22%, rgba(35, 106, 114, 0.13), transparent 22%),
    radial-gradient(circle at 82% 78%, rgba(132, 105, 169, 0.12), transparent 24%),
    linear-gradient(rgba(63, 83, 89, 0.07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(63, 83, 89, 0.07) 1px, transparent 1px),
    linear-gradient(135deg, rgba(250, 252, 249, 0.98), rgba(241, 246, 244, 0.96));
  background-size: auto, auto, 28px 28px, 28px 28px, auto;
}

.knowledge-map:fullscreen {
  width: 100vw;
  height: 100vh;
  min-width: 0;
  border: 0;
  border-radius: 0;
}

.knowledge-map__toolbar {
  position: absolute;
  top: 14px;
  right: 14px;
  z-index: 2;
  display: inline-flex;
  gap: 6px;
  padding: 6px;
  border-radius: 12px;
  border: 1px solid rgba(109, 128, 137, 0.18);
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(12px);
  box-shadow: 0 12px 28px rgba(39, 54, 61, 0.1);
}

.knowledge-map__toolbar button {
  min-width: 34px;
  height: 32px;
  padding: 0 10px;
  border: 0;
  border-radius: 9px;
  color: #31434a;
  background: rgba(234, 241, 239, 0.92);
  font-weight: 700;
  cursor: pointer;
}

.knowledge-map__toolbar button:hover {
  background: #dcebe6;
}

.knowledge-map__canvas {
  width: 100%;
  height: 100%;
  cursor: grab;
  touch-action: none;
}

.knowledge-map__canvas:active {
  cursor: grabbing;
}

.knowledge-map__edge {
  fill: none;
  stroke: rgba(35, 106, 114, 0.72);
  stroke-width: 4;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.knowledge-map__edge--depth-2 {
  stroke: rgba(98, 95, 158, 0.62);
  stroke-width: 3;
}

.knowledge-map__edge--depth-3 {
  stroke: rgba(183, 124, 64, 0.5);
  stroke-width: 2.4;
  stroke-dasharray: 8 8;
}

.knowledge-map__node {
  filter: url("#mindMapShadow");
  cursor: pointer;
  outline: none;
}

.knowledge-map__node:hover .knowledge-map__rect,
.knowledge-map__node:focus-visible .knowledge-map__rect {
  stroke-width: 2.4;
  transform: translateY(-1px);
}

.knowledge-map__glow {
  fill: rgba(255, 255, 255, 0.34);
  opacity: 0;
  transform: translate(0, 0);
}

.knowledge-map__node:hover .knowledge-map__glow {
  opacity: 1;
}

.knowledge-map__rect {
  fill: url("#mindMapNodeGradient");
  stroke: rgba(35, 106, 114, 0.28);
  stroke-width: 1.5;
}

.knowledge-map__rect--root {
  fill: url("#mindMapRootGradient");
  stroke: rgba(255, 255, 255, 0.68);
  stroke-width: 1.8;
}

.knowledge-map__node--depth-1 .knowledge-map__rect {
  fill: url("#mindMapNodeGradient");
  stroke: rgba(35, 106, 114, 0.36);
}

.knowledge-map__node--depth-2 .knowledge-map__rect {
  fill: url("#mindMapBranchGradient");
  stroke: rgba(98, 95, 158, 0.34);
}

.knowledge-map__node--depth-3 .knowledge-map__rect {
  fill: url("#mindMapLeafGradient");
  stroke: rgba(183, 124, 64, 0.32);
}

.knowledge-map__dot {
  fill: #2f7d82;
}

.knowledge-map__node--depth-2 .knowledge-map__dot {
  fill: #6960a8;
}

.knowledge-map__node--depth-3 .knowledge-map__dot {
  fill: #b77c40;
}

.knowledge-map__text {
  color: #2e3e43;
  fill: currentColor;
  font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: 0;
  pointer-events: none;
}

.knowledge-map__text--depth-0 {
  color: #fff;
  font-size: 17px;
  font-weight: 800;
}

.knowledge-map__text--depth-1 {
  color: #25474b;
  font-weight: 760;
}

.knowledge-map__text--depth-2 {
  color: #4a416f;
}

.knowledge-map__text--depth-3 {
  color: #705030;
  font-size: 14px;
}

.knowledge-map__badge circle {
  fill: rgba(255, 255, 255, 0.95);
  stroke: rgba(47, 85, 91, 0.14);
}

.knowledge-map__badge text {
  fill: #2f4b4f;
  font-size: 12px;
  font-weight: 800;
  pointer-events: none;
}

.knowledge-map__node--depth-0 .knowledge-map__badge text {
  fill: #25474b;
}

.knowledge-map__node--collapsed .knowledge-map__rect {
  stroke-dasharray: 7 6;
}

@media (max-width: 820px) {
  .knowledge-map {
    min-width: 620px;
    height: 500px;
  }
}
</style>
