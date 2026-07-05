#!/bin/bash
# premarket_check.sh — StockInsight 开盘前自检脚本
# v2.0 — 集成基建检查
# 退出码: 0=全部通过, 1=有失败项

# 不使用 set -e，让脚本继续执行所有检查
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "$SCRIPT_DIR")")"
cd "$PROJECT_DIR"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

echo "=========================================="
echo "📈 StockInsight 开盘前自检"
echo "   日期: $(date '+%Y-%m-%d %H:%M')"
echo "=========================================="
echo ""

# 检查函数
check_pass() {
    echo -e "${GREEN}✅ $1${NC}"
    ((PASS_COUNT++))
}

check_fail() {
    echo -e "${RED}❌ $1${NC}"
    ((FAIL_COUNT++))
}

check_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
    ((WARN_COUNT++))
}

# ========================================
# 1. Python 环境检查
# ========================================
echo "【1. Python 环境检查】"

if [ -f "$PROJECT_DIR/backend/venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/backend/venv/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON="python3"
else
    check_fail "Python 未找到"
    exit 1
fi

if $PYTHON --version &> /dev/null; then
    VER=$($PYTHON --version 2>&1)
    check_pass "Python: $VER"
else
    check_fail "Python 无法执行"
fi

echo ""

# ========================================
# 2. 关键依赖检查
# ========================================
echo "【2. 关键依赖检查】"

KEY_PACKAGES=("pandas" "numpy" "flask" "requests" "akshare" "baostock")
for pkg in "${KEY_PACKAGES[@]}"; do
    if $PYTHON -c "import $pkg" 2>/dev/null; then
        check_pass "$pkg 已安装"
    else
        check_fail "$pkg 未安装"
    fi
done

echo ""

# ========================================
# 3. 数据缓存检查
# ========================================
echo "【3. 数据缓存检查】"

CACHE_DB="$PROJECT_DIR/stock_cache.db"
if [ -f "$CACHE_DB" ]; then
    SIZE=$(du -h "$CACHE_DB" | cut -f1)
    check_pass "缓存数据库存在 ($SIZE)"
else
    check_warn "缓存数据库不存在，将在首次运行时创建"
fi

# 检查缓存是否过期（超过7天）
if [ -f "$CACHE_DB" ]; then
    LAST_MOD=$(stat -f %m "$CACHE_DB" 2>/dev/null || stat -c %Y "$CACHE_DB" 2>/dev/null)
    NOW=$(date +%s)
    DIFF=$((NOW - LAST_MOD))
    DAYS=$((DIFF / 86400))
    if [ $DAYS -gt 7 ]; then
        check_warn "缓存数据库已 ${DAYS} 天未更新"
    else
        check_pass "缓存数据库较新 (${DAYS}天前更新)"
    fi
fi

echo ""

# ========================================
# 4. ML 模型检查
# ========================================
echo "【4. ML 模型检查】"

MODELS_DIR="$PROJECT_DIR/models"
if [ -d "$MODELS_DIR" ]; then
    MODEL_COUNT=$(ls -1 "$MODELS_DIR"/*.pkl 2>/dev/null | wc -l | tr -d ' ')
    if [ "$MODEL_COUNT" -gt 0 ]; then
        check_pass "ML 模型文件存在 ($MODEL_COUNT 个)"
    else
        check_warn "models/ 目录存在但无 .pkl 文件"
    fi
else
    check_warn "models/ 目录不存在，首次运行将训练模型"
fi

echo ""

# ========================================
# 5. 后端服务检查
# ========================================
echo "【5. 后端服务检查】"

# 检查端口占用（后端默认 8765）
API_PORT=8765
if lsof -i:${API_PORT} &> /dev/null; then
    check_pass "端口 ${API_PORT} 已被占用 (后端可能运行中)"
else
    check_warn "端口 ${API_PORT} 空闲 (后端未运行)"
fi

# 检查 backend 进程（支持 backend/app.py 和 backend/main.py）
if pgrep -f "backend.*app\.py" &> /dev/null || pgrep -f "backend.*main\.py" &> /dev/null || pgrep -f "python.*8765" &> /dev/null; then
    check_pass "后端进程存在"
else
    check_warn "未检测到后端进程"
fi

echo ""

# ========================================
# 6. 数据源连通性检查
# ========================================
echo "【6. 数据源连通性检查】"

# 简单检查网络连通性
if ping -c 1 -W 2 quote.eastmoney.com &> /dev/null; then
    check_pass "东方财富数据源可达"
else
    check_warn "东方财富数据源不可达"
fi

if ping -c 1 -W 2 hq.sinajs.cn &> /dev/null; then
    check_pass "新浪行情数据源可达"
else
    check_warn "新浪行情数据源不可达"
fi

echo ""

# ========================================
# 7. 前端构建检查
# ========================================
echo "【7. 前端构建检查】"

if [ -d "$PROJECT_DIR/build" ]; then
    FILE_COUNT=$(find "$PROJECT_DIR/build" -type f | wc -l)
    check_pass "前端构建存在 ($FILE_COUNT 文件)"
elif [ -d "$PROJECT_DIR/dist" ]; then
    FILE_COUNT=$(find "$PROJECT_DIR/dist" -type f | wc -l)
    check_pass "前端构建存在 ($FILE_COUNT 文件)"
else
    check_warn "前端未构建 (运行 npm run build)"
fi

echo ""

# ========================================
# 8. 日志目录检查
# ========================================
echo "【8. 日志目录检查】"

LOG_DIR="$PROJECT_DIR/logs"
if [ -d "$LOG_DIR" ]; then
    check_pass "日志目录存在"
else
    mkdir -p "$LOG_DIR"
    check_pass "日志目录已创建"
fi

# ========================================
# 汇总报告
# ========================================
echo ""
echo "=========================================="
echo "📊 自检汇总"
echo "=========================================="
echo -e "${GREEN}通过: $PASS_COUNT${NC}"
echo -e "${YELLOW}警告: $WARN_COUNT${NC}"
echo -e "${RED}失败: $FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    echo -e "${GREEN}✅ 自检通过，系统就绪${NC}"
    exit 0
else
    echo -e "${RED}❌ 自检失败，请检查 above 项目${NC}"
    exit 1
fi
