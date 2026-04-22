<template>
  <div class="login-wrap">
    <section class="login-story">
      <div class="story-kicker">Learning Workflow</div>
      <h1 class="story-title">让课件翻译、问答和总结，拥有真正像产品的视觉气质。</h1>
      <p class="story-copy">
        上传英文课件后，你可以逐页浏览中文成品图、围绕当前页提问，也可以对整份 PPT 发起整体问答和章节总结。
      </p>

      <div class="story-ribbon">
        <span>逐页翻译预览</span>
        <span>按页 / 整体问答</span>
        <span>总结与术语沉淀</span>
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
  grid-template-columns: minmax(0, 1.15fr) minmax(380px, 460px);
  align-items: center;
  gap: 32px;
  padding: 34px;
}

.login-story {
  position: relative;
  max-width: 760px;
  padding: 26px 10px;
}

.login-story::before {
  content: "";
  position: absolute;
  inset: 0 auto auto 0;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(245, 158, 11, 0.24), transparent 68%);
  filter: blur(10px);
}

.story-kicker {
  position: relative;
  z-index: 1;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--muted);
}

.story-title {
  position: relative;
  z-index: 1;
  margin: 18px 0 0;
  font-size: clamp(42px, 6vw, 72px);
  line-height: 0.95;
  letter-spacing: -0.05em;
}

.story-copy {
  position: relative;
  z-index: 1;
  margin: 20px 0 0;
  max-width: 640px;
  font-size: 17px;
  color: var(--muted);
  line-height: 1.95;
}

.story-ribbon {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 24px;
}

.story-ribbon span {
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(148, 163, 184, 0.16);
  color: #475569;
  font-size: 13px;
}

.login-panel {
  border-radius: 32px;
  background:
    radial-gradient(circle at top right, rgba(249, 115, 22, 0.16), transparent 30%),
    radial-gradient(circle at left bottom, rgba(56, 189, 248, 0.12), transparent 24%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.96));
}

.login-badge {
  display: inline-flex;
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(249, 115, 22, 0.12);
  color: #c2410c;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.login-title {
  margin: 18px 0 8px;
  font-size: 36px;
  line-height: 1.05;
}

.login-subtitle {
  margin: 0 0 20px;
  color: var(--muted);
  line-height: 1.8;
}

.full-btn {
  width: 100%;
}

.switch-btn {
  margin-top: 12px;
}

@media (max-width: 980px) {
  .login-wrap {
    grid-template-columns: 1fr;
    padding: 20px;
  }

  .login-story {
    padding: 6px 0;
  }
}
</style>
