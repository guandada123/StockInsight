/**
 * StockInsight Pro — k6 性能压测脚本
 *
 * 用法:
 *   k6 run scripts/load_test.js
 *   k6 run -e BASE_URL=http://127.0.0.1:8765 scripts/load_test.js
 *
 * 安装 k6:
 *   brew install k6          # macOS
 *   docker run -i grafana/k6 run - < scripts/load_test.js   # Docker
 *
 * 输出:
 *   - 控制台摘要
 *   - load_test_report.json  (详细指标)
 *   - load_test_report.html  (可视化, 需 k6-reporter)
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";
import { htmlReport } from "https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js";
import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.1/index.js";

// ═══════════════════════════════════════
// 配置
// ═══════════════════════════════════════

const BASE_URL = __ENV.BASE_URL || "http://127.0.0.1:8765";

// 测试用股票代码池
const STOCK_CODES = ["600519", "000001", "000858", "601398", "002594"];

// ═══════════════════════════════════════
// 负载模型: 5→15 VU, 共4分钟
// ═══════════════════════════════════════

export const options = {
  stages: [
    { duration: "30s", target: 5 },   // 预热: 0→5 VU
    { duration: "1m", target: 15 },   // 爬升: 5→15 VU
    { duration: "2m", target: 15 },   // 维持: 15 VU 稳定负载
    { duration: "30s", target: 0 },   // 冷却: 15→0 VU
  ],
  thresholds: {
    http_req_duration: [
      "p(95)<500",   // 95% 请求 < 500ms
      "p(99)<2000",  // 99% 请求 < 2s (包容重量级分析)
    ],
    http_req_failed: ["rate<0.01"],  // HTTP 失败率 < 1%
    error_rate: ["rate<0.05"],       // 业务错误率 < 5%
  },
};

// ═══════════════════════════════════════
// 自定义指标
// ═══════════════════════════════════════

const errorRate = new Rate("error_rate");
const apiLatency = new Trend("api_latency", true);
const healthLatency = new Trend("health_latency", true);
const successCount = new Counter("success_count");
const failCount = new Counter("fail_count");

// ═══════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════

function randomCode() {
  return STOCK_CODES[Math.floor(Math.random() * STOCK_CODES.length)];
}

function checkResponse(res, name) {
  const ok = check(res, {
    [`${name}: status 200`]: (r) => r.status === 200,
    [`${name}: has body`]: (r) => r.body && r.body.length > 0,
  });

  if (ok) {
    successCount.add(1);
    errorRate.add(false);
  } else {
    failCount.add(1);
    errorRate.add(true);
  }

  apiLatency.add(res.timings.duration);
  return ok;
}

// ═══════════════════════════════════════
// 主测试函数
// ═══════════════════════════════════════

export default function () {
  // Group 1: 健康检查 (基线)
  group("Health Check", () => {
    const res = http.get(`${BASE_URL}/api/health`);
    healthLatency.add(res.timings.duration);
    check(res, {
      "health: status 200": (r) => r.status === 200,
      "health: latency < 100ms": (r) => r.timings.duration < 100,
    });
  });

  // Group 2: 市场行情
  group("Market Overview", () => {
    const res1 = http.get(`${BASE_URL}/api/market/overview`);
    checkResponse(res1, "market/overview");

    const res2 = http.get(`${BASE_URL}/api/market/hot-sectors?top_n=12`);
    checkResponse(res2, "market/hot-sectors");
  });

  // Group 3: 批量报价
  group("Batch Quotes", () => {
    const codes = STOCK_CODES.slice(0, 3).join(",");
    const res = http.get(`${BASE_URL}/api/market/quotes?codes=${codes}`);
    checkResponse(res, "market/quotes");
  });

  // Group 4: 快速分析 (200ms级)
  group("Fast Analysis", () => {
    const code = randomCode();
    const res = http.get(`${BASE_URL}/api/analysis/${code}/fast`);
    checkResponse(res, `analysis/${code}/fast`);
    check(res, {
      "fast: latency < 500ms": (r) => r.timings.duration < 500,
    });
  });

  // Group 5: 标准分析 (L0-L5)
  group("Standard Analysis", () => {
    const code = randomCode();
    const res = http.get(`${BASE_URL}/api/analysis/${code}`);
    checkResponse(res, `analysis/${code}`);
  });

  // Group 6: 持仓列表
  group("Portfolio", () => {
    const res = http.get(`${BASE_URL}/api/portfolio/list`);
    checkResponse(res, "portfolio/list");
  });

  // 迭代间停顿 (模拟真实用户思考时间)
  sleep(1);
}

// ═══════════════════════════════════════
// 报告输出
// ═══════════════════════════════════════

export function handleSummary(data) {
  return {
    stdout: textSummary(data, { indent: "  ", enableColors: true }),
    "load_test_report.json": JSON.stringify(data, null, 2),
    "load_test_report.html": htmlReport(data),
  };
}
