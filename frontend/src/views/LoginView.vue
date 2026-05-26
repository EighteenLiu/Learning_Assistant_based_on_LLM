<template>
  <div class="login-wrap">
    <section class="login-story">
      <div class="story-kicker">Bilingual Courseware Studio</div>
      <h1 class="story-title">把一份英文课件，整理成可读、可问、可复习的学习空间。</h1>
      <p class="story-copy">
        上传课件后，系统会按页呈现中文预览，保留原有页面脉络。你可以围绕正在阅读的页面追问，也可以让整份课件沉淀为摘要、术语和复习线索。
      </p>

      <div class="story-ribbon">
        <span>中英对照阅读</span>
        <span>围绕课件提问</span>
        <span>生成复习线索</span>
      </div>
    </section>

    <section class="login-panel page-card">
      <div class="login-badge">Smart Courseware Workspace</div>
      <h2 class="login-title">{{ isRegister ? "创建账号" : "欢迎回来" }}</h2>
      <p class="login-subtitle">
        {{ isRegister ? "创建账号后即可开始建立你的双语课件工作台。" : "登录后继续你的课件翻译与学习流程。" }}
      </p>

      <el-form :model="form" label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位字符" />
        </el-form-item>
        <el-button type="primary" :loading="loading" @click="submit" class="full-btn">
          {{ isRegister ? "注册并登录" : "登录系统" }}
        </el-button>
      </el-form>

      <el-button text class="switch-btn" @click="isRegister = !isRegister">
        {{ isRegister ? "已有账号，返回登录" : "没有账号，创建一个" }}
      </el-button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { http } from "../api/client";

const router = useRouter();
const loading = ref(false);
const isRegister = ref(false);
const form = reactive({
  username: "",
  password: "",
});

const submit = async () => {
  if (!form.username.trim() || !form.password.trim()) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }

  loading.value = true;
  try {
    const url = isRegister.value ? "/auth/register" : "/auth/login";
    const { data } = await http.post(url, form);
    localStorage.setItem("access_token", data.access);
    localStorage.setItem("refresh_token", data.refresh);
    localStorage.setItem("username", data.username);
    ElMessage.success(isRegister.value ? "注册成功，已自动登录" : "登录成功");
    router.push("/dashboard/upload");
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "登录或注册失败");
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(340px, 400px);
  align-items: center;
  gap: 28px;
  padding: 32px clamp(20px, 5vw, 64px);
}

.login-story {
  position: relative;
  max-width: 640px;
  padding: 18px 4px;
}

.story-kicker {
  position: relative;
  z-index: 1;
  font-size: 11px;
  letter-spacing: 0;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 700;
}

.story-title {
  position: relative;
  z-index: 1;
  margin: 14px 0 0;
  max-width: 520px;
  font-size: clamp(28px, 3.4vw, 40px);
  line-height: 1.2;
  letter-spacing: 0;
  font-weight: 700;
}

.story-copy {
  position: relative;
  z-index: 1;
  margin: 16px 0 0;
  max-width: 560px;
  font-size: 14px;
  color: var(--muted);
  line-height: 1.85;
}

.story-ribbon {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 20px;
}

.story-ribbon span {
  padding: 7px 11px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.16);
  color: #475569;
  font-size: 12px;
}

.login-panel {
  padding: 24px;
  border-radius: 24px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.96));
}

.login-badge {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(249, 115, 22, 0.12);
  color: #c2410c;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
}

.login-title {
  margin: 16px 0 6px;
  font-size: 26px;
  line-height: 1.18;
  letter-spacing: 0;
}

.login-subtitle {
  margin: 0 0 18px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}

.full-btn {
  width: 100%;
  min-height: 38px;
  font-size: 14px;
}

.switch-btn {
  margin-top: 10px;
  font-size: 13px;
}

:deep(.el-form-item) {
  margin-bottom: 16px;
}

:deep(.el-form-item__label) {
  margin-bottom: 5px;
  font-size: 13px;
  line-height: 1.4;
}

:deep(.el-input__inner) {
  font-size: 13px;
}

:deep(.el-input__wrapper) {
  min-height: 38px;
  border-radius: 12px;
}

@media (max-width: 980px) {
  .login-wrap {
    grid-template-columns: 1fr;
    align-content: center;
    padding: 24px 18px;
  }

  .login-story {
    padding: 6px 0;
  }

  .story-title {
    font-size: clamp(28px, 8vw, 38px);
  }
}

@media (max-width: 640px) {
  .login-wrap {
    gap: 18px;
  }

  .login-panel {
    padding: 20px;
  }

  .story-copy {
    font-size: 13px;
  }
}
</style>
