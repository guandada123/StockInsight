// 运行时 API 基址注入（构建时由 vite 复制到 dist/config.js，index.html 通过
//   <script src="/config.js"> 加载）。空串 = 同源相对路径，由部署方的反向代理
//   提供 /api（docker nginx / tailscale serve / vite dev proxy 均属此列）。
// 需要跨域直连 API 时，把这里改成你的 API 域名，例如：
//   window.__API_BASE__ = "https://api.example.com";
window.__API_BASE__ = "";
