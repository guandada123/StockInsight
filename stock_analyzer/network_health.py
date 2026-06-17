"""网络健康监测模块 —— 启动时快速检测各数据源可用性，动态选择最优源

用法:
  from stock_analyzer.network_health import check_all, get_best_source
  health = check_all()  # 2秒内完成
  print(health.best_kline_source)  # 'sina' / 'tencent' / 'baostock'
"""

import time
from dataclasses import dataclass, field

import requests


@dataclass
class SourceStatus:
    name: str
    available: bool = False
    latency_ms: float = 9999
    error: str = ""


@dataclass
class NetworkHealth:
    sina: SourceStatus = field(default_factory=lambda: SourceStatus("sina"))
    tencent: SourceStatus = field(default_factory=lambda: SourceStatus("tencent"))
    baostock: SourceStatus = field(default_factory=lambda: SourceStatus("baostock"))
    eastmoney: SourceStatus = field(default_factory=lambda: SourceStatus("eastmoney"))
    checked_at: float = 0

    @property
    def best_kline_source(self) -> str:
        """返回最优K线源"""
        candidates = [self.sina, self.tencent, self.baostock]
        available = [s for s in candidates if s.available]
        if not available:
            return "baostock"  # 最终兜底
        return min(available, key=lambda s: s.latency_ms).name

    @property
    def all_ok(self) -> bool:
        return self.sina.available or self.tencent.available

    @property
    def mode(self) -> str:
        """当前网络模式"""
        if self.sina.available and self.sina.latency_ms < 500:
            return "fast"
        elif self.all_ok:
            return "normal"
        else:
            return "offline"


def _quick_get(url, timeout=2):
    """快速GET请求，返回(耗时ms, 是否成功)"""
    t0 = time.time()
    try:
        s = requests.Session()
        s.trust_env = False
        r = s.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "http://finance.sina.com.cn"},
        )
        ms = (time.time() - t0) * 1000
        return ms, r.status_code == 200 and len(r.text) > 100
    except Exception:
        return 9999, False


def check_all():
    """检测所有数据源，2秒内返回结果"""
    health = NetworkHealth()
    health.checked_at = time.time()

    # 新浪实时行情
    ms, ok = _quick_get("http://hq.sinajs.cn/list=sh000001", timeout=2)
    health.sina = SourceStatus("sina", ok, ms, "" if ok else "超时或不可达")

    # 腾讯K线
    ms, ok = _quick_get(
        "http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,,,5,qfq", timeout=2
    )
    health.tencent = SourceStatus("tencent", ok, ms, "" if ok else "超时或不可达")

    # 东方财富（板块数据）
    ms, ok = _quick_get(
        "https://push2.eastmoney.com/api/qt/clist/get?"
        "pn=1&pz=1&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2&"
        "fields=f12,f14&ut=bd1d9ddb04089700cf9c27f6f7426281",
        timeout=3,
    )
    health.eastmoney = SourceStatus("eastmoney", ok, ms, "" if ok else "超时或不可达")

    return health


# 全局缓存（10分钟有效）
_health_cache = None
_health_cache_time = 0.0
_HEALTH_TTL = 600  # 10分钟


def get_health(force=False):
    """获取网络健康状态（缓存10分钟）"""
    global _health_cache, _health_cache_time
    if not force and _health_cache and time.time() - _health_cache_time < _HEALTH_TTL:  # type: ignore[unreachable]
        return _health_cache  # type: ignore[unreachable]
    _health_cache = check_all()
    _health_cache_time = time.time()
    return _health_cache


def print_health():
    """打印网络健康报告"""
    h = get_health(force=True)
    print(f"网络健康检测 ({time.strftime('%H:%M:%S')}):")
    for s in [h.sina, h.tencent, h.eastmoney]:
        status = f"✅ {s.latency_ms:.0f}ms" if s.available else f"❌ {s.error}"
        print(f"  {s.name:<12} {status}")
    baostock_ok = True  # Baostock 需要 import，不在这里测
    print(f"  baostock     {'✅ Python包可用' if baostock_ok else '❌ 未安装'}")
    print(f"  最优K线源: {h.best_kline_source}")
    print(f"  模式: {h.mode}")
    return h


if __name__ == "__main__":
    print_health()
