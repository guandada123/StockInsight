import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: string;
}

/**
 * 全局错误边界 — 防止单组件崩溃导致白屏。
 *
 * 用法:
 *   <ErrorBoundary>
 *     <Dashboard />
 *   </ErrorBoundary>
 *
 * 特性:
 *   - 捕获子组件渲染/生命周期中的 JS 异常
 *   - 显示友好错误提示（非白屏）
 *   - 支持一键重试恢复
 *   - 记录错误到 console（生产可接 Sentry）
 */
export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: "" };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: { componentStack?: string | null }) {
    const errorInfo = info.componentStack || "";
    this.setState({ errorInfo });

    // 记录错误（生产环境可发送到 Sentry / 飞书告警）
    console.error("[ErrorBoundary] Caught:", error.message);
    if (errorInfo) {
      console.error("[ErrorBoundary] Stack:", errorInfo);
    }
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: "" });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "40vh",
            padding: 32,
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
          <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>页面加载异常</h2>
          <p style={{ color: "var(--dm, #888)", fontSize: 14, marginBottom: 20, maxWidth: 400 }}>
            该模块遇到了意外错误。您的数据不会丢失，点击下方按钮可尝试恢复。
          </p>
          {this.state.error && (
            <pre
              style={{
                fontSize: 11,
                color: "var(--dm, #666)",
                background: "var(--bg2, #f5f5f5)",
                padding: "8px 16px",
                borderRadius: 6,
                maxWidth: 500,
                overflow: "auto",
                marginBottom: 16,
              }}
            >
              {this.state.error.message}
            </pre>
          )}
          <button
            onClick={this.handleRetry}
            style={{
              padding: "10px 24px",
              borderRadius: 8,
              border: "none",
              background: "#2563eb",
              color: "white",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
              transition: "transform 0.2s, box-shadow 0.2s",
            }}
            onMouseEnter={(e) => {
              (e.target as HTMLElement).style.transform = "translateY(-1px)";
              (e.target as HTMLElement).style.boxShadow = "0 4px 12px rgba(37,99,235,0.3)";
            }}
            onMouseLeave={(e) => {
              (e.target as HTMLElement).style.transform = "";
              (e.target as HTMLElement).style.boxShadow = "";
            }}
          >
            重新加载
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
