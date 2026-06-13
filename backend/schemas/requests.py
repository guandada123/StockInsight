"""
API 请求参数验证模型 — Pydantic v2
统一入参校验，防止无效输入进入业务逻辑层。

Usage:
    from backend.schemas.requests import StockCode, KlineParams

    @router.get("/{code}")
    async def analyze(code: StockCode):
        ...
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ═══════════════════════════════════════
# 基础类型
# ═══════════════════════════════════════


class StockCodeParam(BaseModel):
    """股票代码验证（6位数字）"""

    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

    @field_validator("code")
    @classmethod
    def validate_market(cls, v: str) -> str:
        """验证股票代码属于支持的市场"""
        if v.startswith(("688", "689")):
            raise ValueError(f"{v} 属于科创板，当前不支持")
        if v.startswith(("300", "301")):
            raise ValueError(f"{v} 属于创业板，当前不支持")
        if v.startswith(("8", "4")):
            raise ValueError(f"{v} 属于北交所，当前不支持")
        return v


class BatchCodesParam(BaseModel):
    """批量股票代码验证"""

    codes: str = Field(..., min_length=6, description="逗号分隔的股票代码")

    @field_validator("codes")
    @classmethod
    def validate_codes(cls, v: str) -> str:
        code_list = [c.strip() for c in v.split(",") if c.strip()]
        if not code_list:
            raise ValueError("请提供至少一个股票代码")
        if len(code_list) > 20:
            raise ValueError("批量查询最多支持20个代码")
        for code in code_list:
            if not re.match(r"^\d{6}$", code):
                raise ValueError(f"无效代码格式: {code}，需要6位数字")
        return v

    @property
    def code_list(self) -> list[str]:
        return [c.strip() for c in self.codes.split(",") if c.strip()]


# ═══════════════════════════════════════
# K线参数
# ═══════════════════════════════════════


class KlineParams(BaseModel):
    """K线请求参数"""

    ktype: Literal["day", "week", "month"] = "day"
    days: int = Field(default=120, ge=5, le=500)


class IndicatorParams(BaseModel):
    """技术指标请求参数"""

    indicator: Literal["macd", "rsi", "kdj"] = "macd"


# ═══════════════════════════════════════
# 持仓参数
# ═══════════════════════════════════════


class PortfolioCreateParams(BaseModel):
    """创建组合参数"""

    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[\w\u4e00-\u9fff\-]+$")
    codes: str = Field(default="", description="逗号分隔的股票代码(可选)")

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """防止路径遍历攻击"""
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("名称不能包含路径分隔符")
        return v.strip()


class PortfolioUpdateParams(BaseModel):
    """更新持仓参数"""

    code: str = Field(..., pattern=r"^\d{6}$")
    shares: int = Field(default=0, ge=0, le=10000000)
    cost: float = Field(default=0.0, ge=0, le=100000)
    action: Literal["add", "remove", "update"] = "add"


# ═══════════════════════════════════════
# 数据任务参数
# ═══════════════════════════════════════


class DataJobParams(BaseModel):
    """数据下载任务参数"""

    job_type: Literal[
        "trade_calendar", "stock_basic", "daily_history", "daily_basic", "moneyflow", "industry"
    ]
    start_date: str | None = Field(default=None, pattern=r"^\d{8}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{8}$")

    @field_validator("start_date", "end_date")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        year, month, day = int(v[:4]), int(v[4:6]), int(v[6:8])
        if not (2000 <= year <= 2030 and 1 <= month <= 12 and 1 <= day <= 31):
            raise ValueError(f"无效日期: {v}")
        return v


# ═══════════════════════════════════════
# 分页参数
# ═══════════════════════════════════════


class PaginationParams(BaseModel):
    """通用分页参数"""

    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
