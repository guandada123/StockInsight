# 安全扫描与密钥防护

## 三层密钥防护体系

StockInsight 采用 QTS 同款三层防护策略，防止密钥泄露。

| 层级 | 触发条件 | 工具 |
|------|----------|------|
| 🛡️ 本地开发 | 本地构建 / `make check-deploy` | grep 扫描 |
| 🛡️ CI PR/推送 | GitHub Actions `test.yml` | grep 扫描 |
| 🛡️ 定时/推送 main | GitHub Actions `security-scan.yml` | gitleaks |

## CSP 策略（生产环境）

```
default-src 'self'
script-src 'self'
style-src 'self' 'unsafe-inline'
img-src 'self' data: https:
connect-src 'self'
frame-ancestors 'none'
form-action 'self'
```

## 生产环境限制

- `PYWORKSPACE_ENV=production` 时，禁用 `/docs`、`/redoc`、`/openapi.json`
- HSTS 仅在生产环境启用
- CORS 白名单：仅 `localhost:1420`、`tauri://localhost`
- 速率限制：60 req/min/IP

## 依赖扫描

- 本地：`grep -rn "sk-" backend/ stock_analyzer/` 检测硬编码密钥
- CI：集成 gitleaks 全量扫描
- `ruff.toml` 配置代码风格规则
