import { useState, useCallback } from "react";
import type { ApiResponse } from "../types/api";
import { API_BASE } from "../types/api";

export function useApi<T>() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchApi = useCallback(async (path: string): Promise<ApiResponse<T>> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}${path}`);
      const json: ApiResponse<T> = await res.json();
      if (!json.success) {
        setError(json.error || "Unknown error");
      }
      return json;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      return { success: false, data: null as any, error: msg, freshness: "stale", timing_ms: 0 };
    } finally {
      setLoading(false);
    }
  }, []);

  const postApi = useCallback(async (path: string, body?: unknown): Promise<ApiResponse<T>> => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const json: ApiResponse<T> = await res.json();
      if (!json.success) setError(json.error || "Unknown error");
      return json;
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      return { success: false, data: null as any, error: msg, freshness: "stale", timing_ms: 0 };
    } finally {
      setLoading(false);
    }
  }, []);

  return { fetchApi, postApi, loading, error, setError };
}
