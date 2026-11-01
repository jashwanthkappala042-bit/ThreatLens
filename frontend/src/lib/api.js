import axios from "axios";

export const TOKEN_KEY = "threatlens.token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage may be unavailable */
  }
}

const baseURL = import.meta.env.VITE_API_BASE || "";

export const http = axios.create({
  baseURL,
  timeout: 45_000,
});

http.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export class ApiError extends Error {
  constructor(message, { code = "request_failed", status = 0, details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

http.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      const body = error.response.data;
      const info = body?.error || {};
      const normalized = new ApiError(
        info.message || `Request failed (${error.response.status}).`,
        {
          code: info.code || "request_failed",
          status: error.response.status,
          details: info.details || null,
        },
      );
      if (error.response.status === 401 && getToken()) {
        window.dispatchEvent(new CustomEvent("threatlens:unauthorized"));
      }
      return Promise.reject(normalized);
    }
    if (error.code === "ECONNABORTED") {
      return Promise.reject(
        new ApiError("The request timed out. The site may be slow or unreachable.", {
          code: "timeout",
        }),
      );
    }
    return Promise.reject(
      new ApiError(
        "Could not reach the ThreatLens API. Confirm the backend is running on port 5000.",
        { code: "network_error" },
      ),
    );
  },
);

function unwrap(response) {
  const body = response.data;
  if (!body || body.success !== true) {
    throw new ApiError("The API returned an unexpected response.", { code: "bad_response" });
  }
  const result = body.data;
  if (body.meta && result && typeof result === "object" && !Array.isArray(result)) {
    return { data: result, meta: body.meta };
  }
  return { data: result, meta: body.meta || null };
}

async function get(url, config) {
  return unwrap(await http.get(url, config));
}
async function post(url, body, config) {
  return unwrap(await http.post(url, body, config));
}
async function patch(url, body, config) {
  return unwrap(await http.patch(url, body, config));
}
async function del(url, config) {
  return unwrap(await http.delete(url, config));
}

export const api = {
  health: () => get("/api/health"),

  register: (payload) => post("/api/auth/register", payload),
  login: (payload) => post("/api/auth/login", payload),
  me: () => get("/api/auth/me"),
  logout: () => post("/api/auth/logout"),

  scanUrl: (url) => post("/api/scan/url", { url }),
  scanEmail: ({ subject, sender, body }) => post("/api/scan/email", { subject, sender, body }),
  scanImage: (file) => {
    const form = new FormData();
    form.append("file", file);
    return post("/api/scan/image", form, {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 90_000,
    });
  },
  analysis: (id) => get(`/api/analysis/${id}`),
  scanStatus: (id) => get(`/api/scan/${id}/status`),
  scanReportUrl: (id) => `${baseURL}/api/scan/${id}/report.pdf`,

  history: (params) => get("/api/history", { params }),
  deleteScan: (id) => del(`/api/history/${id}`),

  dashboardStats: () => get("/api/dashboard/stats"),
  dashboardActivity: () => get("/api/dashboard/activity"),
  dashboardCategories: () => get("/api/dashboard/categories"),
  dashboardOverview: () => get("/api/dashboard/overview"),

  posts: (params) => get("/api/community/posts", { params }),
  post: (id) => get(`/api/community/posts/${id}`),
  createPost: (payload) => post("/api/community/posts", payload),
  addComment: (postId, content) => post(`/api/community/posts/${postId}/comments`, { content }),
  reportPost: (postId, reason) => post(`/api/community/posts/${postId}/report`, { reason }),
  deletePost: (postId) => del(`/api/community/posts/${postId}`),
  moderationReports: () => get("/api/community/moderation/reports"),
  moderatePost: (postId, action, note = "") =>
    patch(`/api/community/posts/${postId}/moderation`, { action, note }),
  resolveReport: (reportId, action, note = "") =>
    patch(`/api/community/reports/${reportId}`, { action, note }),

  complaints: (params) => get("/api/complaints", { params }),
  complaint: (id) => get(`/api/complaints/${id}`),
  createComplaint: (payload) => post("/api/complaints/generate", payload),
  complaintPdfUrl: (id) => `${baseURL}/api/complaints/${id}/pdf`,

  profile: () => get("/api/profile"),
  updateProfile: (payload) => patch("/api/profile", payload),
};

/**
 * Authenticated file downloads must carry the bearer token. Fetch the file and
 * trigger a browser save without exposing the token in a URL.
 */
export async function downloadAuthenticated(url, fallbackName) {
  const response = await http.get(url.replace(baseURL, ""), { responseType: "blob" });
  const disposition = response.headers["content-disposition"] || "";
  const match = /filename\*?=(?:UTF-8'')?"?([^\";]+)"?/i.exec(disposition);
  const name = match ? decodeURIComponent(match[1]) : fallbackName;
  const objectUrl = URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 30_000);
}
