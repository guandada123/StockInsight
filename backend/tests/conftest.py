"""
StockInsight API 集成测试 — 共享 fixtures

注意: stock_analyzer mock 在 test_api_integration.py 模块加载时自动处理，
      conftest 仅提供通用测试数据 fixtures 和 mock_fetcher 引用。
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 确保 backend 和 stock_analyzer 可导入
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


# ── 模块级 mock_fetcher 引用（供 test_api_integration.py 使用）──
mock_fetcher = MagicMock()


@pytest.fixture
def mock_market_data():
    """模拟行情数据（新浪/东方财富格式）"""
    return {
        "000001": {
            "名称": "平安银行",
            "最新价": "12.50",
            "昨收": "12.30",
            "今开": "12.35",
            "最高": "12.60",
            "最低": "12.20",
            "成交额": "1500000000",
            "振幅": "3.25",
            "成交量": "120000000",
            "换手率": "0.62",
        },
        "600519": {
            "名称": "贵州茅台",
            "最新价": "1580.00",
            "昨收": "1560.00",
            "今开": "1565.00",
            "最高": "1590.00",
            "最低": "1555.00",
            "成交额": "3200000000",
            "振幅": "2.24",
            "成交量": "2030000",
            "换手率": "0.16",
        },
    }


@pytest.fixture
def mock_sectors_data():
    """模拟板块数据"""
    return {
        "白酒": {
            "code": "BK0477",
            "涨跌幅": "2.15",
            "资金净流入": "850000000",
            "领涨股": "贵州茅台",
        },
        "银行": {
            "code": "BK0475",
            "涨跌幅": "1.05",
            "资金净流入": "320000000",
            "领涨股": "招商银行",
        },
        "新能源车": {
            "code": "BK0900",
            "涨跌幅": "-0.52",
            "资金净流入": "-150000000",
            "领涨股": "比亚迪",
        },
    }
