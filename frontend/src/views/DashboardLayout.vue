<template>
  <div class="dashboard-shell">
    <header class="page-card dashboard-topbar">
      <div class="topbar-main">
        <div class="topbar-kicker">AI Courseware Studio</div>
        <h1 class="topbar-title">双语课件智能学习平台</h1>
        <p class="topbar-subtitle">
          以一体化的智能工作台，重塑课件从解析、翻译、研读到复盘的完整体验，让每一份内容都能以更专业、更流畅的方式被理解、沉淀与再利用。
        </p>
      </div>

      <div class="topbar-actions">
        <div class="topbar-buttons">
          <div class="quick-links">
            <el-button plain @click="router.push('/dashboard/upload')">工作台</el-button>
            <el-button plain @click="router.push('/dashboard/records')">历史记录</el-button>
          </div>

          <el-dropdown trigger="click" @command="handleUserCommand">
            <button class="user-center" type="button">
              <span class="user-avatar">{{ username.slice(0, 1).toUpperCase() }}</span>
              <span class="user-meta">
                <strong>{{ username }}</strong>
                <small>{{ isRecordsRoute ? "历史学习中心" : "学习工作台" }}</small>
              </span>
            </button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="upload">工作台</el-dropdown-item>
                <el-dropdown-item command="records">历史记录</el-dropdown-item>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>

        <div class="courseware-strip">
          <div class="control-card">
            <span class="control-label">切换课件</span>
            <el-select
              v-model="selectedCoursewareId"
              class="courseware-select"
              placeholder="请选择课件"
              clearable
              filterable
              @change="syncCourseware"
            >
              <el-option
                v-for="item in coursewares"
                :key="item.id"
                :label="`${item.title} · #${item.id}`"
                :value="item.id"
              />
            </el-select>
          </div>

          <div class="topbar-meta">
            <div class="meta-card">
              <span>当前课件</span>
              <strong>{{ currentCoursewareTitle }}</strong>
            </div>
            <div class="meta-card compact">
              <span>课件总数</span>
              <strong>{{ coursewares.length }}</strong>
            </div>
          </div>
        </div>
      </div>
    </header>

    <main class="dashboard-main">
      <router-view v-slot="{ Component, route }">
        <transition name="fade-slide" mode="out-in">
          <keep-alive :include="['upload']">
            <component :is="Component" :key="route.fullPath" @courseware-updated="fetchCoursewares" />
          </keep-alive>
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { http } from "../api/client";
import type { CoursewareItem } from "../types";

const router = useRouter();
const route = useRoute();
const username = localStorage.getItem("username") || "访客";
const selectionEventName = "courseware-selection-changed";
const coursewares = ref<CoursewareItem[]>([]);
const selectedCoursewareId = ref<number | undefined>(
  localStorage.getItem("selected_courseware_id")
    ? Number(localStorage.getItem("selected_courseware_id"))
    : undefined
);

const isRecordsRoute = computed(() => route.path === "/dashboard/records");

const currentCoursewareTitle = computed(() => {
  const current = coursewares.value.find((item) => item.id === selectedCoursewareId.value);
  return current?.title || "尚未选择课件";
});

const emitSelectionChanged = () => {
  window.dispatchEvent(
    new CustomEvent(selectionEventName, {
      detail: selectedCoursewareId.value ?? null,
    })
  );
};

const syncCourseware = async () => {
  if (selectedCoursewareId.value) {
    localStorage.setItem("selected_courseware_id", String(selectedCoursewareId.value));
  } else {
    localStorage.removeItem("selected_courseware_id");
  }
  emitSelectionChanged();
};

const handleExternalSelectionChange = () => {
  const stored = localStorage.getItem("selected_courseware_id");
  selectedCoursewareId.value = stored ? Number(stored) : undefined;
};

const fetchCoursewares = async () => {
  try {
    const { data } = await http.get<CoursewareItem[]>("/coursewares");
    coursewares.value = data;

    if (selectedCoursewareId.value && !coursewares.value.some((item) => item.id === selectedCoursewareId.value)) {
      selectedCoursewareId.value = coursewares.value[0]?.id;
      await syncCourseware();
      return;
    }

    if (!selectedCoursewareId.value && coursewares.value.length) {
      selectedCoursewareId.value = coursewares.value[0].id;
      await syncCourseware();
      return;
    }

    emitSelectionChanged();
  } catch {
    ElMessage.error("课件列表加载失败");
  }
};

const logout = () => {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("selected_courseware_id");
  localStorage.removeItem("username");
  window.dispatchEvent(new CustomEvent(selectionEventName, { detail: null }));
  router.push("/login");
};

const handleUserCommand = async (command: string) => {
  if (command === "logout") {
    logout();
    return;
  }

  if (command === "records") {
    await router.push("/dashboard/records");
    return;
  }

  if (command === "upload") {
    await router.push("/dashboard/upload");
  }
};

onMounted(async () => {
  window.addEventListener(selectionEventName, handleExternalSelectionChange as EventListener);
  await fetchCoursewares();
  if (router.currentRoute.value.path === "/dashboard") {
    await router.push("/dashboard/upload");
  }
});

onUnmounted(() => {
  window.removeEventListener(selectionEventName, handleExternalSelectionChange as EventListener);
});
</script>

<style scoped>
.dashboard-shell {
  min-height: 100vh;
  padding: 28px;
  display: grid;
  gap: 20px;
}

.dashboard-topbar {
  display: grid;
  grid-template-columns: minmax(0, 1.22fr) minmax(320px, 0.78fr);
  gap: 24px;
  overflow: hidden;
  position: relative;
  border-color: rgba(98, 115, 136, 0.2);
}

.dashboard-topbar::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at right top, rgba(201, 107, 44, 0.16), transparent 22%),
    radial-gradient(circle at left center, rgba(56, 189, 248, 0.12), transparent 22%),
    linear-gradient(135deg, rgba(255, 255, 255, 0.08), transparent 45%);
  pointer-events: none;
}

.dashboard-topbar::after {
  content: "";
  position: absolute;
  top: 0;
  left: 24px;
  right: 24px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.7), transparent);
  pointer-events: none;
}

.topbar-main,
.topbar-actions {
  position: relative;
  z-index: 1;
}

.topbar-kicker {
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 700;
}

.topbar-title {
  margin: 12px 0 0;
  font-size: clamp(34px, 5vw, 52px);
  line-height: 0.94;
  letter-spacing: -0.04em;
  max-width: 10.5em;
}

.topbar-subtitle {
  margin: 16px 0 0;
  max-width: 720px;
  color: var(--muted);
  line-height: 1.85;
  font-size: 14px;
}

.topbar-meta {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.meta-card {
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid rgba(122, 104, 86, 0.14);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(255, 248, 241, 0.62)),
    rgba(255, 255, 255, 0.6);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.9),
    0 12px 24px rgba(17, 32, 49, 0.05);
}

.meta-card span {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.meta-card strong {
  display: block;
  line-height: 1.55;
  font-size: 18px;
}

.topbar-actions {
  display: grid;
  gap: 16px;
  align-content: start;
}

.courseware-strip {
  display: grid;
  grid-template-columns: minmax(280px, 1.1fr) minmax(260px, 0.9fr);
  gap: 14px;
  align-items: stretch;
}

.control-card {
  display: grid;
  align-content: start;
  padding: 18px;
  border-radius: 24px;
  background:
    radial-gradient(circle at right top, rgba(22, 106, 109, 0.08), transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(248, 250, 252, 0.96));
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
}

.control-label {
  display: block;
  margin-bottom: 10px;
  font-size: 12px;
  color: var(--muted);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 700;
}

.courseware-select {
  width: 100%;
}

.topbar-buttons {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  align-items: center;
}

.quick-links {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  padding: 8px;
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.42);
  border: 1px solid rgba(255, 255, 255, 0.42);
}

.user-center {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.98)),
    rgba(255, 255, 255, 0.5);
  cursor: pointer;
  box-shadow: 0 12px 22px rgba(17, 32, 49, 0.06);
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
}

.user-center:hover {
  transform: translateY(-1px);
  border-color: rgba(201, 107, 44, 0.26);
  box-shadow: 0 16px 28px rgba(17, 32, 49, 0.1);
}

.user-avatar {
  width: 42px;
  height: 42px;
  border-radius: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  font-weight: 700;
  background: linear-gradient(135deg, #dd7a30, #b94020);
  box-shadow: 0 10px 24px rgba(217, 119, 6, 0.28);
}

.user-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
}

.user-meta strong {
  color: var(--text);
}

.user-meta small {
  color: var(--muted);
}

.dashboard-main {
  position: relative;
}

.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.32s ease;
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(12px) scale(0.995);
}

@media (max-width: 1080px) {
  .dashboard-shell {
    padding: 18px;
  }

  .dashboard-topbar {
    grid-template-columns: 1fr;
  }

  .topbar-meta {
    grid-template-columns: 1fr;
  }

  .courseware-strip {
    grid-template-columns: 1fr;
  }
}
</style>
