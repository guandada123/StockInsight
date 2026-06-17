import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useApi } from "./useApi";
import type { ApiResponse } from "../types/api";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("useApi", () => {
  it("初始状态 loading=false, error=null", () => {
    const { result } = renderHook(() => useApi());
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("fetchApi 成功后返回数据并清除 error", async () => {
    const mockData: ApiResponse<{ value: number }> = {
      success: true,
      data: { value: 42 },
      error: null,
      freshness: "fresh",
      timing_ms: 10,
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve(mockData),
    });

    const { result } = renderHook(() => useApi<{ value: number }>());

    let res: ApiResponse<{ value: number }> | undefined;
    await act(async () => {
      res = await result.current.fetchApi("/test");
    });

    expect(res?.success).toBe(true);
    expect(res?.data?.value).toBe(42);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it("fetchApi 网络异常时设置 error", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error("Network failure"));

    const { result } = renderHook(() => useApi());

    let res: ApiResponse<unknown> | undefined;
    await act(async () => {
      res = await result.current.fetchApi("/fail");
    });

    expect(res?.success).toBe(false);
    expect(result.current.error).toBe("Network failure");
  });

  it("fetchApi 收到 API 层错误时设置 error", async () => {
    const mockError: ApiResponse<null> = {
      success: false,
      data: null,
      error: "Invalid request",
      freshness: "stale",
      timing_ms: 5,
    };
    globalThis.fetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve(mockError),
    });

    const { result } = renderHook(() => useApi());

    let res: ApiResponse<unknown> | undefined;
    await act(async () => {
      res = await result.current.fetchApi("/bad-request");
    });

    expect(res?.success).toBe(false);
    expect(result.current.error).toBe("Invalid request");
  });

  it("postApi 发送 JSON body", async () => {
    const mockData: ApiResponse<{ id: number }> = {
      success: true,
      data: { id: 1 },
      error: null,
      freshness: "fresh",
      timing_ms: 8,
    };
    const fetchMock = vi.fn().mockResolvedValue({
      json: () => Promise.resolve(mockData),
    });
    globalThis.fetch = fetchMock;

    const { result } = renderHook(() => useApi<{ id: number }>());

    await act(async () => {
      await result.current.postApi("/create", { name: "test" });
    });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/create"),
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "test" }),
      })
    );
  });

  it("loading 在请求期间为 true，完成后为 false", async () => {
    let resolvePromise!: (v: ApiResponse<string>) => void;
    globalThis.fetch = vi.fn().mockReturnValue(
      new Promise<Response>((resolve) => {
        resolvePromise = (v: ApiResponse<string>) =>
          resolve({ json: () => Promise.resolve(v) } as Response);
      })
    );

    const { result } = renderHook(() => useApi<string>());

    // 发起请求但不 await
    const promise = result.current.fetchApi("/slow");

    // 请求中 loading 应为 true
    await waitFor(() => expect(result.current.loading).toBe(true));

    // 完成后
    await act(async () => {
      resolvePromise({
        success: true,
        data: "done",
        error: null,
        freshness: "fresh",
        timing_ms: 100,
      });
      await promise;
    });

    expect(result.current.loading).toBe(false);
  });
});
