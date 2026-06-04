import { createRouter, createWebHistory } from 'vue-router';
import DashboardLayout from '../views/DashboardLayout.vue';
import LoginView from '../views/LoginView.vue';
import RecordsView from '../views/RecordsView.vue';
import UploadTranslateView from '../views/UploadTranslateView.vue';

/** Cache: once validated in this session, skip re-checking on every route change. */
let _tokenValidated = false;

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to) {
    if (to.hash) {
      return {
        el: to.hash,
        top: 24,
        behavior: 'smooth',
      };
    }
    return { top: 0 };
  },
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { public: true },
    },
    {
      path: '/',
      redirect: '/dashboard/upload',
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: DashboardLayout,
      children: [
        { path: '', redirect: '/dashboard/upload' },
        { path: 'upload', name: 'upload', component: UploadTranslateView, meta: { keepAlive: true } },
        { path: 'qa', redirect: '/dashboard/upload#qa-section' },
        { path: 'summary', redirect: '/dashboard/upload#summary-section' },
        { path: 'records', name: 'records', component: RecordsView },
      ],
    },
  ],
});

async function validateToken(): Promise<boolean> {
  const token = localStorage.getItem('access_token');
  if (!token) return false;
  try {
    const resp = await fetch('/api/auth/me', {
      headers: { Authorization: 'Bearer ' + token },
    });
    return resp.ok;
  } catch {
    return false;
  }
}

// 实现 clearSession 对应的核心处理，封装输入转换、状态更新或结果返回。
function clearSession() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('username');
}

router.beforeEach(async (to) => {
  const token = localStorage.getItem('access_token');
  if (!to.meta.public && !token) {
    return '/login';
  }
  if (to.path === '/login' && token) {
    return '/dashboard/upload';
  }

  // For protected routes with a token, validate it once per session
  if (!to.meta.public && token && !_tokenValidated) {
    const valid = await validateToken();
    if (!valid) {
      clearSession();
      return '/login';
    }
    _tokenValidated = true;
  }

  return true;
});

export default router;
