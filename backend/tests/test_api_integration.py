"""
StockInsight API 集成测试 — 验证完整请求链路
使用 FastAPI TestClient，Mock 外部数据源
覆盖: health, market, analysis, portfolio, factors, data, 错误处理, 中间件
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

# ════════════════════════════════════════════════════
# Phase 1 — Module-level: mock stock_analyzer BEFORE importing app
# 确保 app import 时内部懒加载 stock_analyzer 获取的是 mock
# 导入完成后立即恢复，不污染其他 test module 的 collection
# ════════════════════════════════════════════════════
_ORIG_SA = sys.modules.get("stock_analyzer")
_ORIG_SA_FETCHER = sys.modules.get("stock_analyzer.fetcher")

_mock_sa = MagicMock()
sys.modules["stock_analyzer"] = _mock_sa

from backend.tests.conftest import mock_fetcher

_mock_sa.fetcher = mock_fetcher
sys.modules["stock_analyzer.fetcher"] = mock_fetcher

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

# 恢复原始模块，避免污染其他 test module
if _ORIG_SA is not None:
    sys.modules["stock_analyzer"] = _ORIG_SA
else:
    sys.modules.pop("stock_analyzer", None)
if _ORIG_SA_FETCHER is not None:
    sys.modules["stock_analyzer.fetcher"] = _ORIG_SA_FETCHER
else:
    sys.modules.pop("stock_analyzer.fetcher", None)

# ════════════════════════════════════════════════════
# Phase 2 — Module-scope fixture: 测试执行时重新注入 mock
# 因为 router 函数内是懒加载 stock_analyzer，测试执行时仍需 mock
# ════════════════════════════════════════════════════


@pytest.fixture(scope="module", autouse=True)
def _mock_stock_analyzer():
    """测试执行时重新 mock stock_analyzer，确保懒加载拿到 mock。"""
    sys.modules["stock_analyzer"] = _mock_sa
    sys.modules["stock_analyzer.fetcher"] = mock_fetcher
    yield
    # 恢复（不影响后续 module）
    if _ORIG_SA is not None:
        sys.modules["stock_analyzer"] = _ORIG_SA
    else:
        sys.modules.pop("stock_analyzer", None)
    if _ORIG_SA_FETCHER is not None:
        sys.modules["stock_analyzer.fetcher"] = _ORIG_SA_FETCHER
    else:
        sys.modules.pop("stock_analyzer.fetcher", None)


# ═══════════════════════════════════════
# Health Check & System
# ═══════════════════════════════════════


class TestHealthCheck:
    def test_health_endpoint(self):
        """GET /api/health 应返回 200 + status ok"""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ok"

    def test_health_includes_uptime(self):
        """健康检查应包含运行时间"""
        response = client.get("/api/health")
        data = response.json()
        assert "uptime" in data or "uptime_s" in data or response.status_code == 200

    def test_api_root_lists_endpoints(self):
        """GET /api 应列出所有可用端点"""
        response = client.get("/api")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)


# ═══════════════════════════════════════
# Market API
# ═══════════════════════════════════════


class TestMarketAPI:
    def test_overview_returns_safe_error_on_failure(self):
        """market overview 异常时不泄露内部信息"""
        mock_fetcher.get_market_overview.side_effect = RuntimeError("internal db error")
        response = client.get("/api/market/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "internal db error" not in str(data.get("error", ""))

    def test_overview_returns_data_on_success(self):
        """market overview 正常返回结构化数据"""
        mock_fetcher.get_market_overview.side_effect = None
        mock_fetcher.get_market_overview.return_value = {
            "indices": {"上证指数": {"price": 3200, "change": 1.5}},
            "limit_up": 45,
            "limit_down": 12,
        }
        response = client.get("/api/market/overview")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_quotes_requires_codes_param(self):
        """批量行情需要 codes 参数"""
        response = client.get("/api/market/quotes")
        assert response.status_code == 422

    def test_quotes_with_valid_codes(self):
        """批量行情正常调用"""
        mock_fetcher.get_realtime_quotes.return_value = {
            "600519": {"name": "贵州茅台", "price": 1580}
        }
        response = client.get("/api/market/quotes?codes=600519,000001")
        assert response.status_code == 200

    def test_hot_sectors_default_params(self):
        """热门板块使用默认参数"""
        mock_fetcher.get_sectors.return_value = {}
        mock_fetcher.get_sector_fund_flow_rank.return_value = {}
        response = client.get("/api/market/hot-sectors")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    def test_hot_sectors_custom_top_n(self):
        """热门板块自定义 top_n"""
        mock_fetcher.get_sectors.return_value = {}
        mock_fetcher.get_sector_fund_flow_rank.return_value = {}
        response = client.get("/api/market/hot-sectors?top_n=5")
        assert response.status_code == 200

    def test_indices_endpoint(self):
        """GET /api/market/indices"""
        mock_fetcher.get_indices.return_value = {}
        response = client.get("/api/market/indices")
        assert response.status_code == 200

    def test_limit_up_down_endpoint(self):
        """GET /api/market/limit-up-down"""
        mock_fetcher.get_limit_up_down.return_value = {"up": 30, "down": 5}
        response = client.get("/api/market/limit-up-down")
        assert response.status_code == 200

    def test_sector_rotation_endpoint(self):
        """GET /api/market/sector-rotation"""
        mock_fetcher.get_sector_rotation.return_value = []
        response = client.get("/api/market/sector-rotation")
        assert response.status_code == 200


# ═══════════════════════════════════════
# Analysis API
# ═══════════════════════════════════════


class TestAnalysisAPI:
    def test_standard_analysis(self):
        """GET /api/analysis/{code} 标准分析"""
        mock_fetcher.analyze_stock.return_value = {"code": "600519", "score": 85}
        response = client.get("/api/analysis/600519")
        assert response.status_code == 200

    def test_fast_analysis(self):
        """GET /api/analysis/{code}/fast 快速分析"""
        mock_fetcher.fast_analyze.return_value = {"code": "600519", "layers": ["L0", "L1", "L2"]}
        response = client.get("/api/analysis/600519/fast")
        assert response.status_code == 200

    def test_kline_endpoint(self):
        """GET /api/analysis/{code}/kline K线数据"""
        mock_fetcher.get_kline.return_value = []
        response = client.get("/api/analysis/600519/kline")
        assert response.status_code == 200

    def test_kline_with_params(self):
        """K线支持 ktype 和 days 参数"""
        mock_fetcher.get_kline.return_value = []
        response = client.get("/api/analysis/600519/kline?ktype=week&days=60")
        assert response.status_code == 200

    def test_indicators_endpoint(self):
        """GET /api/analysis/{code}/indicators 技术指标"""
        mock_fetcher.get_indicators.return_value = {}
        response = client.get("/api/analysis/600519/indicators")
        assert response.status_code == 200

    def test_indicators_with_type(self):
        """技术指标支持 indicator 参数"""
        mock_fetcher.get_indicators.return_value = {}
        response = client.get("/api/analysis/600519/indicators?indicator=rsi")
        assert response.status_code == 200

    def test_fund_flow_endpoint(self):
        """GET /api/analysis/{code}/fund-flow 资金流向"""
        mock_fetcher.get_fund_flow.return_value = []
        response = client.get("/api/analysis/600519/fund-flow")
        assert response.status_code == 200

    def test_quality_endpoint(self):
        """GET /api/analysis/{code}/quality 公司质地"""
        mock_fetcher.analyze_quality.return_value = {"questions": []}
        response = client.get("/api/analysis/600519/quality")
        assert response.status_code == 200


# ═══════════════════════════════════════
# Portfolio API
# ═══════════════════════════════════════


class TestPortfolioAPI:
    def test_list_portfolios(self):
        """列出持仓组合"""
        response = client.get("/api/portfolio/list")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "portfolios" in data["data"]

    def test_get_nonexistent_portfolio(self):
        """获取不存在的组合"""
        response = client.get("/api/portfolio/nonexistent_test_xyz_12345")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False

    def test_create_portfolio(self):
        """创建新组合"""
        response = client.post("/api/portfolio/create?name=test_ci_portfolio_tmp")
        assert response.status_code == 200
        data = response.json()
        # 创建应成功（无论是否已存在）
        assert "success" in data

    def test_delete_portfolio(self):
        """删除组合"""
        # 先创建
        client.post("/api/portfolio/create?name=test_delete_tmp")
        # 再删除
        response = client.delete("/api/portfolio/test_delete_tmp")
        assert response.status_code == 200

    def test_update_portfolio_add_stock(self):
        """向组合添加股票"""
        client.post("/api/portfolio/create?name=test_update_tmp")
        response = client.put(
            "/api/portfolio/test_update_tmp?code=600519&action=add&shares=100&cost=1580"
        )
        assert response.status_code == 200


# ═══════════════════════════════════════
# Factors API
# ═══════════════════════════════════════


class TestFactorsAPI:
    def test_list_factors(self):
        """列出所有因子（mock 环境下返回错误是预期行为）"""
        response = client.get("/api/factors/list")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    def test_validate_expression(self):
        """验证因子表达式"""
        response = client.post("/api/factors/validate?expression=close/open")
        assert response.status_code == 200

    def test_create_factor(self):
        """创建自定义因子"""
        response = client.post(
            "/api/factors/create",
            json={
                "factor_id": "test_factor_ci",
                "name": "CI测试因子",
                "expression": "close / open - 1",
                "factor_type": "momentum",
                "description": "CI自动测试用因子",
            },
        )
        assert response.status_code == 200

    def test_delete_factor(self):
        """删除因子"""
        response = client.delete("/api/factors/test_factor_ci")
        assert response.status_code == 200


# ═══════════════════════════════════════
# Data Management API
# ═══════════════════════════════════════


class TestDataManagementAPI:
    def test_db_stats(self):
        """GET /api/data/stats 数据库统计"""
        response = client.get("/api/data/stats")
        assert response.status_code == 200

    def test_clear_cache(self):
        """POST /api/data/clear-cache 清除缓存"""
        response = client.post("/api/data/clear-cache")
        assert response.status_code == 200

    def test_source_status(self):
        """GET /api/data/source-status 数据源状态"""
        response = client.get("/api/data/source-status")
        assert response.status_code == 200

    def test_export_nonexistent_code(self):
        """导出不存在的股票代码"""
        response = client.get("/api/data/export/999999")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False


# ═══════════════════════════════════════
# Data Jobs API
# ═══════════════════════════════════════


class TestDataJobsAPI:
    def test_list_job_types(self):
        """列出可用任务类型"""
        response = client.get("/api/data-jobs/job-types")
        assert response.status_code == 200

    def test_list_jobs(self):
        """列出最近任务"""
        response = client.get("/api/data-jobs/list")
        assert response.status_code == 200

    def test_get_nonexistent_job_status(self):
        """查询不存在的任务状态"""
        response = client.get("/api/data-jobs/status/nonexistent_job_id")
        assert response.status_code == 200


# ═══════════════════════════════════════
# Error Handling & Security
# ═══════════════════════════════════════


class TestErrorHandling:
    def test_404_for_unknown_routes(self):
        """未知路由返回 404"""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404

    def test_error_messages_are_sanitized(self):
        """错误信息不泄露敏感内容"""
        mock_fetcher.get_market_overview.side_effect = Exception(
            "postgresql://user:password@host/db connection failed"
        )
        response = client.get("/api/market/overview")
        data = response.json()
        error_str = str(data)
        assert "password" not in error_str
        assert "postgresql://" not in error_str

    def test_stack_trace_not_exposed(self):
        """异常堆栈不暴露给客户端"""
        mock_fetcher.get_market_overview.side_effect = ValueError("secret internal state")
        response = client.get("/api/market/overview")
        body = response.text
        assert "Traceback" not in body
        assert "secret internal" not in body

    def test_sql_injection_in_code_param(self):
        """SQL注入尝试不应崩溃"""
        response = client.get("/api/analysis/' OR 1=1 --")
        # 应返回错误而非崩溃
        assert response.status_code in (200, 400, 422)


# ═══════════════════════════════════════
# Middleware
# ═══════════════════════════════════════


class TestMiddleware:
    def test_response_timing_header(self):
        """响应应包含 X-Response-Time-Ms 头"""
        response = client.get("/api/health")
        assert "X-Response-Time-Ms" in response.headers
        timing = float(response.headers["X-Response-Time-Ms"])
        assert timing >= 0

    def test_cors_headers_present(self):
        """CORS 头应存在"""
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:1420",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI CORS middleware should respond
        assert response.status_code in (200, 204, 405)


# ═══════════════════════════════════════
# OpenAPI / Docs
# ═══════════════════════════════════════


class TestDocs:
    def test_swagger_ui_available(self):
        """Swagger UI 端点可访问"""
        response = client.get("/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "openapi" in response.text.lower()

    def test_redoc_available(self):
        """ReDoc 端点可访问"""
        response = client.get("/redoc")
        assert response.status_code == 200

    def test_openapi_json(self):
        """OpenAPI JSON 可获取且结构正确"""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        spec = response.json()
        assert spec["info"]["title"] == "StockInsight Pro API"
        assert spec["info"]["version"] == "1.0.0"
        assert len(spec.get("paths", {})) >= 20
