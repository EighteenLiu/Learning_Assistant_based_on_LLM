import axios from "axios";

export const http = axios.create({
  baseURL: "/api",
  timeout: 60000,
});

http.interceptors.request.use((config) => {
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
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      if (!location.pathname.includes("/login")) {
        location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

