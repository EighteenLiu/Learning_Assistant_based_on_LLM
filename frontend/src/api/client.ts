import axios from "axios";

export const http = axios.create({
  baseURL: "/api",
  timeout: 60000,
});

http.interceptors.request.use((config) => {
  // 统一在请求拦截器注入 JWT，业务页面不用重复处理认证头。
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (resp) => resp,
  (error) => {
    if (error?.response?.status === 401) {
      // token 失效后清理本地状态并回到登录页，避免继续用失效身份请求接口。
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      if (!location.pathname.includes("/login")) {
        location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);
