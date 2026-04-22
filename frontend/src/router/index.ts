import { createRouter, createWebHistory } from "vue-router";
import DashboardLayout from "../views/DashboardLayout.vue";
import LoginView from "../views/LoginView.vue";
import RecordsView from "../views/RecordsView.vue";
import UploadTranslateView from "../views/UploadTranslateView.vue";

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior(to) {
    if (to.hash) {
      return {
        el: to.hash,
        top: 24,
        behavior: "smooth",
      };
    }
    return { top: 0 };
  },
  routes: [
    {
      path: "/login",
      name: "login",
      component: LoginView,
      meta: { public: true },
    },
    {
      path: "/",
      redirect: "/dashboard/upload",
    },
    {
      path: "/dashboard",
      name: "dashboard",
      component: DashboardLayout,
      children: [
        { path: "", redirect: "/dashboard/upload" },
        { path: "upload", name: "upload", component: UploadTranslateView, meta: { keepAlive: true } },
        { path: "qa", redirect: "/dashboard/upload#qa-section" },
        { path: "summary", redirect: "/dashboard/upload#summary-section" },
        { path: "records", name: "records", component: RecordsView },
      ],
    },
  ],
});

router.beforeEach((to) => {
  const token = localStorage.getItem("access_token");
  if (!to.meta.public && !token) {
    return "/login";
  }
  if (to.path === "/login" && token) {
    return "/dashboard/upload";
  }
  return true;
});

export default router;
