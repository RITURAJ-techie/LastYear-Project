import axios, { AxiosError } from "axios";

export const api = axios.create({ baseURL: "/" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("if_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err: AxiosError) => {
    if (err.response?.status === 401 && !String(err.config?.url).includes("/auth/")) {
      localStorage.removeItem("if_token");
      if (!location.pathname.startsWith("/login")) location.href = "/login";
    }
    return Promise.reject(err);
  },
);

export function errMsg(e: unknown): string {
  const ax = e as AxiosError<{ detail?: unknown }>;
  const d = ax?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x: any) => x.msg ?? String(x)).join("; ");
  return ax?.message || "Something went wrong";
}

export async function download(url: string, filename: string) {
  const r = await api.get(url, { responseType: "blob" });
  const href = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = href;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(href);
}

export async function openHtml(url: string) {
  const r = await api.get(url, { responseType: "text" });
  const w = window.open("", "_blank");
  if (w) {
    w.document.open();
    w.document.write(r.data);
    w.document.close();
  }
}
