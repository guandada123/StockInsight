import { useState, useCallback } from "react";
import type { ApiResponse } from "../types/api";
import { API_BASE } from "../types/api";

/**
 * 把非 2xx 响应转成可读文案。
 * 后端错误体形如 `{"detail": "..."}`（FastAPI 的 HTTPException），并非 ApiResponse。
 */
async function buildHttpError(res: Response): Promise<string> {
  let detail = "";
  try {
    const body = (await res.json()) as { detail?: unknown; error?: unknown } | null;
    const d = body?.detail ?? body?.error;
    if (typeof d === "string" && d) detail = d;
  } catch {
    // 响应体不是 JSON（或已被消费），忽略，仅用状态码文案
  }
  const base =
    res.status === 401
      ? "鉴权失败"
      : res.status === 429
        ? "请求过于频繁，请稍后重试"
        : `请求失败（HTTP ${res.status}）`;
  return detail ? `${base}：${detail}` : base;
}

export function useApi<T>() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 通用请求方法，支持 GET / POST / DELETE / PUT，并可通过 signal 取消 */
  const request = useCallback(
    async (
      path: string,
      options?: { method?: string; body?: unknown; signal?: AbortSignal }
    ): Promise<ApiResponse<T>> => {
      setLoading(true);
      setError(null);
      try {
        const init: RequestInit = { method: options?.method || "GET" };
        if (options?.body !== undefined) {
          init.headers = { "Content-Type": "application/json" };
          init.body = JSON.stringify(options.body);
        }
        if (options?.signal) init.signal = options.signal;

        const res = await fetch(`${API_BASE}${path}`, init);

        // 先判 res.ok：401/429/5xx 时后端返回 {"detail": ...}，不是 ApiResponse，
        // 直接 res.json() 会把它当成 ApiResponse 解析 → 用户永远看到 "Unknown error"。
        // 这里用 `res.ok === false` 而非 `!res.ok`，以兼容仅 mock 了 json() 的测试替身
        // （其 ok 为 undefined，应继续走正常解析分支）。
        if (res.ok === false) {
          const msg = await buildHttpError(res);
          setError(msg);
          return {
            success: false,
            data: null as unknown as T,
            error: msg,
            freshness: "stale",
            timing_ms: 0,
          };
        }

        const json: ApiResponse<T> = await res.json();
        if (!json.success) {
          setError(json.error || "Unknown error");
        }
        return json;
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        return {
          success: false,
          data: null as unknown as T,
          error: msg,
          freshness: "stale",
          timing_ms: 0,
        };
      } finally {
        setLoading(false);
      }
    },
    []
  );

  /** GET 请求，可选传入 AbortSignal 以支持取消 */
  const fetchApi = useCallback(
    (path: string, signal?: AbortSignal): Promise<ApiResponse<T>> =>
      request(path, { method: "GET", signal }),
    [request]
  );

  /** POST 请求（JSON body） */
  const postApi = useCallback(
    (path: string, body?: unknown): Promise<ApiResponse<T>> =>
      request(path, { method: "POST", body }),
    [request]
  );

  return { fetchApi, postApi, request, loading, error, setError };
}
