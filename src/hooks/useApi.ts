import { useState, useCallback } from "react";
import type { ApiResponse } from "../types/api";
import { API_BASE } from "../types/api";

export function useApi<T>() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** 通用请求方法，支持 GET / POST / DELETE / PUT */
  const request = useCallback(async (
    path: string,
    options?: { method?: string; body?: unknown }
  ): Promise<ApiResponse<T>> => {
    setLoading(true);
    setError(null);
    try {
      const init: RequestInit = { method: options?.method || "GET" };
      if (options?.body !== undefined) {
        init.headers = { "Content-Type": "application/json" };
        init.body = JSON.stringify(options.body);
      }
      const res = await fetch(`${API_BASE}${path}`, init);
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
  }, []);

  /** GET 请求 */
  const fetchApi = useCallback(
    (path: string): Promise<ApiResponse<T>> => request(path, { method: "GET" }),
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
