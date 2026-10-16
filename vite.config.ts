import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    host: "0.0.0.0",
    port: 1420,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**", "**/stock_cache.db*"],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
  envPrefix: ["VITE_", "TAURI_"],
  build: {
    target: process.env.TAURI_PLATFORM === "windows" ? "chrome105" : "es2020",
    // vite 8 默认用 rolldown 构建器，esbuild 已拆为独立包且 transformWithEsbuild 弃用。
    // 改用内置 oxc 压缩器（rolldown 原生支持，无需额外依赖），避免 docker 构建时
    // "Failed to load transformWithEsbuild / Cannot find package 'esbuild'" 报错。
    minify: !process.env.TAURI_DEBUG ? "oxc" : false,
    sourcemap: !!process.env.TAURI_DEBUG,
    rollupOptions: {
      output: {
        // P2-8：把 React 运行时拆成独立 vendor chunk；配合 App.tsx 的路由级
        //   React.lazy 动态导入，ECharts 会被 rolldown 归入懒加载的 StockAnalysis
        //   chunk（首屏不再加载），首屏产物体积由 ~1.45MB 降到 ~265KB。
        //
        // 实测结论（见修复报告）：把 echarts 也写进 manualChunks 会让 **入口 chunk 静态
        //   import 该 echarts chunk**（构建产物 index-*.js 内含 `import ... from
        //   "./echarts-*.js"`，index.html 也会 <link rel="modulepreload"> 它），
        //   导致 1.14MB 的 ECharts 重新回到首屏、抵消懒加载收益。因此这里只拆
        //   react-vendor，ECharts 交给动态 import 自然分包。
        // vite 8(rolldown) 的 manualChunks 仅接受函数形式。
        manualChunks(id: string) {
          if (
            id.includes("react-dom") ||
            id.includes("/react/") ||
            id.includes("scheduler") ||
            id.includes("react-router")
          ) {
            return "react-vendor";
          }
          return undefined;
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
