"""配置常量 — 所有路径基于项目根目录自动解析

新增内容（2026-05-26）：
  - 自动检测项目根目录（向上找 stock_cache.db 或 cli.py）
  - 统一路径常量（供 cache/alert/portfolio/report_html 复用）
  - 因子权重可通过环境变量覆盖

2026-06-14 更新：
  - 集成 python-dotenv 加载 .env 文件
  - 敏感配置统一从环境变量读取
"""

import os

from stock_analyzer.env import get_env, load_env

# 启动时自动加载 .env 文件（静默失败如果 dotenv 未安装）
load_env()

# ── 项目根目录 ────────────────────────────────────


def _find_root():
    """自动检测项目根目录"""
    # 从当前文件位置向上找
    d = os.path.dirname(os.path.abspath(__file__))
    markers = ["stock_cache.db", "cli.py", "full_scan_results.csv"]
    for _ in range(3):
        for m in markers:
            if os.path.exists(os.path.join(d, m)):
                return d
        d = os.path.dirname(d)
    return d


ROOT_DIR = _find_root()

# ── 代理配置：国内数据源直连 ──────────────────────
# 系统代理(Clash/V2Ray)会拦截东方财富等国内站点，
# 将其加入 NO_PROXY 让 requests 和 akshare 直连。
_NO_PROXY_DOMAINS = (
    "eastmoney.com,push2.eastmoney.com,80.push2.eastmoney.com,"
    "push2his.eastmoney.com,data.eastmoney.com,emweb.securities.eastmoney.com,"
    "10jqka.com.cn,sinajs.cn,sina.com.cn,"
    "akshare.push2.eastmoney.com"
)
_current_no_proxy = os.environ.get("NO_PROXY", "")
if _current_no_proxy:
    os.environ["NO_PROXY"] = f"{_current_no_proxy},{_NO_PROXY_DOMAINS}"
else:
    os.environ["NO_PROXY"] = _NO_PROXY_DOMAINS

# ── 路径常量 ──────────────────────────────────────

DB_PATH = os.path.join(ROOT_DIR, "stock_cache.db")
REPORT_DIR = os.path.join(ROOT_DIR, "reports")
CHART_DIR = os.path.join(ROOT_DIR, "reports", "charts")
PORTFOLIO_DIR = os.path.join(ROOT_DIR, "portfolios")
LOG_DIR = os.path.join(ROOT_DIR, "logs")
ARCHIVE_DIR = os.path.join(ROOT_DIR, "archive")
ALERTS_PATH = os.path.join(ROOT_DIR, "alerts.json")
ALERTS_LOG_PATH = os.path.join(ROOT_DIR, "alerts_log.txt")
STOCK_LIST_CACHE = os.path.join(ROOT_DIR, "stock_list_cache.json")
CHECKPOINT_FILE = os.path.join(ROOT_DIR, ".scan_progress")

# 确保目录存在
for _d in [REPORT_DIR, CHART_DIR, PORTFOLIO_DIR, LOG_DIR, ARCHIVE_DIR]:
    os.makedirs(_d, exist_ok=True)

# ── API请求头 ─────────────────────────────────────

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

API_HIS = "https://push2his.eastmoney.com"
API_HOSTS = [
    "https://push2his.eastmoney.com",
    "http://80.push2.eastmoney.com",
    "https://push2.eastmoney.com",
]

UT = "bd1d9ddb04089700cf9c27f6f7426281"
KLINE_PERIODS = {"daily": 101, "weekly": 102, "monthly": 103}
ADJUST = {"qfq": 1, "hfq": 2, "none": 0}

# ── 技术分析参数 ──────────────────────────────────

MA_WINDOWS = [5, 10, 20, 60]
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
RSI_PERIOD = 14
KDJ_PERIOD = 9

# ── 量化分析参数 ──────────────────────────────────

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE = 0.03
VAR_CONFIDENCE = 0.95
BB_PERIOD = 20
BB_STD_DEV = 2
ADX_PERIOD = 14

QUANT_FACTOR_WEIGHTS = {
    "momentum": 0.21,
    "technical": 0.21,
    "fundamental": 0.17,
    "volume": 0.10,
    "risk": 0.11,
    "sentiment": 0.10,  # 舆情因子升至10%（原3%），反映消息面重要性
    "fund_flow": 0.10,
}

# ── 扫描默认参数 ──────────────────────────────────

DEFAULT_TOP_N = 30
DEFAULT_MIN_SCORE = 60
DEFAULT_KLINE_DAYS = 120
DEFAULT_SCAN_MODE = "mainboard"  # "full" or "mainboard"
MEM_CACHE_MAX = 5000
CHECKPOINT_INTERVAL = 100  # 每N只保存一次断点

# 缓存 TTL（秒）
KLINE_CACHE_TTL = 86400  # K线 24 小时（日线数据盘中不变，隔夜才需刷新）
FUNDAMENTALS_CACHE_TTL = 86400  # 基本面 24 小时
NT_HOLDINGS_CACHE_TTL = 604800  # 国家队 7 天（季报数据）
NT_HOLDINGS_FAIL_TTL = 86400  # 国家队查询失败缓存 24 小时
SCAN_WORKERS = 8  # 扫描并行线程数

# ── TuShare（可选增强数据源）────────────────────

TUSHARE_TOKEN = get_env("TUSHARE_TOKEN", "")
# 注册地址: https://tushare.pro/register
# 设置方式: 在 .env 文件中设置 TUSHARE_TOKEN=your_token
# 或在系统环境变量中 export TUSHARE_TOKEN=your_token

# ── 飞书推送（从环境变量读取）────────────────
FEISHU_WEBHOOK = get_env("FEISHU_WEBHOOK", "")
FEISHU_CHAT_ID = get_env("FEISHU_CHAT_ID", "")

# ── AI 模型密钥 ─────────────────────────────
DEEPSEEK_API_KEY = get_env("DEEPSEEK_API_KEY", "")
