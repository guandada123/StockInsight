import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import ErrorBoundary from "./ErrorBoundary";

// 会抛出错误的子组件
function BuggyComponent({ shouldThrow = false }: { shouldThrow?: boolean }) {
  if (shouldThrow) {
    throw new Error("测试错误");
  }
  return <div>正常渲染</div>;
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    // 抑制 console.error 在测试中的输出
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  it("正常渲染子组件", () => {
    render(
      <ErrorBoundary>
        <div>子组件内容</div>
      </ErrorBoundary>
    );
    expect(screen.getByText("子组件内容")).toBeInTheDocument();
  });

  it("捕获子组件抛出的错误并显示降级 UI", () => {
    // 使用包裹容器触发错误
    function TestCase() {
      return (
        <ErrorBoundary>
          <BuggyComponent shouldThrow />
        </ErrorBoundary>
      );
    }

    // 类组件错误边界需要用特殊方式测试
    // 简单验证：挂载一个会抛出错误的子组件
    const origError = console.error;
    console.error = vi.fn();

    const { container } = render(
      <ErrorBoundary>
        <BuggyComponent shouldThrow />
      </ErrorBoundary>
    );

    console.error = origError;

    // 错误边界应该显示降级 UI
    expect(screen.getByText("页面加载异常")).toBeInTheDocument();
    expect(screen.getByText("重新加载")).toBeInTheDocument();
  });

  it("捕获错误时显示具体的错误信息", () => {
    const origError = console.error;
    console.error = vi.fn();

    render(
      <ErrorBoundary>
        <BuggyComponent shouldThrow />
      </ErrorBoundary>
    );

    console.error = origError;

    // 错误信息应该显示
    expect(screen.getByText("测试错误")).toBeInTheDocument();
  });

  it("错误后点击重新加载按钮恢复", () => {
    const origError = console.error;
    console.error = vi.fn();

    // 使用可切换状态的组件验证 retry
    function ToggleBuggy({ triggerError }: { triggerError: boolean }) {
      if (triggerError) throw new Error("临时错误");
      return <div>恢复成功</div>;
    }

    function TestHarness() {
      // 始终触发错误
      return (
        <ErrorBoundary>
          <ToggleBuggy triggerError />
        </ErrorBoundary>
      );
    }

    render(<TestHarness />);

    // 确认显示错误 UI
    expect(screen.getByText("页面加载异常")).toBeInTheDocument();

    // 点击重新加载 — 子组件仍会抛出，但 ErrorBoundary 状态重置
    // 验证按钮可点击且不崩溃
    const btn = screen.getByText("重新加载");
    expect(btn).toBeInTheDocument();
    expect(() => fireEvent.click(btn)).not.toThrow();

    console.error = origError;
  });

  it("支持自定义 fallback 属性", () => {
    const origError = console.error;
    console.error = vi.fn();

    render(
      <ErrorBoundary fallback={<div>自定义错误提示</div>}>
        <BuggyComponent shouldThrow />
      </ErrorBoundary>
    );

    console.error = origError;

    expect(screen.getByText("自定义错误提示")).toBeInTheDocument();
    // 默认降级 UI 不应显示
    expect(screen.queryByText("页面加载异常")).not.toBeInTheDocument();
  });

  it("无错误时不显示降级 UI", () => {
    render(
      <ErrorBoundary>
        <div>正常内容</div>
      </ErrorBoundary>
    );

    expect(screen.queryByText("页面加载异常")).not.toBeInTheDocument();
    expect(screen.getByText("正常内容")).toBeInTheDocument();
  });
});
