"""
Root conftest for StockInsight.

1. Cleans persistent state before test session starts.
2. Ensures deterministic test collection order.
3. Cleans up temp portfolio files leaked by integration tests.
"""

import os


def pytest_sessionstart(session):
    """Pre-test cleanup: remove rate limiter state file.

    backend/main.py loads/stores rate limit state in .rate_limits.json
    via _load_rate_limits() / _dump_rate_limits(). If a previous test run
    left this file within the 60-second sliding window, the new session
    inherits stale entries and tests start returning 429 Too Many Requests
    before the suite completes.
    """
    rate_file = os.path.join(os.path.dirname(__file__), "backend", ".rate_limits.json")
    if os.path.exists(rate_file):
        os.remove(rate_file)


def pytest_collection_modifyitems(config, items):
    """Sort collected tests so stock_analyzer/tests/ items come first.

    When pytest . runs from project root, collection follows filesystem
    traversal order, which may pick up backend/tests/ before
    stock_analyzer/tests/. The module-level mock/import/restore code in
    test_api_integration.py then runs before stock_analyzer modules are
    loaded, leading to inconsistent mock state during test execution.

    By fixing the execution order here, we ensure stock_analyzer modules
    are fully loaded before any backend tests execute.
    """
    stock_items = []
    backend_items = []
    other_items = []

    for item in items:
        fspath = str(item.fspath)
        if "stock_analyzer/tests/" in fspath:
            stock_items.append(item)
        elif "backend/tests/" in fspath:
            backend_items.append(item)
        else:
            other_items.append(item)

    # Reorder: stock_analyzer first, then backend, then everything else
    items[:] = stock_items + backend_items + other_items


def pytest_sessionfinish(session, exitstatus):
    """Post-test cleanup: remove temp portfolio files written by integration tests.

    TestPortfolioAPI（backend/tests/test_api_integration.py）直接调用真实路由，
    会经 portfolio_service 把 test_*.json 写到仓库 portfolios/ 目录。这些文件只在
    .gitignore 里被忽略，磁盘上仍会残留（例如 test_update_tmp.json 不会被用例自身
    删除，每跑一次测试就多一份）。这里在会话结束时统一清理，只匹配 .gitignore 同款
    模式 portfolios/test_*.json，不会触碰真实组合文件。
    """
    portfolio_dir = os.path.join(os.path.dirname(__file__), "portfolios")
    if not os.path.isdir(portfolio_dir):
        return
    for name in os.listdir(portfolio_dir):
        if name.startswith("test_") and name.endswith(".json"):
            try:
                os.remove(os.path.join(portfolio_dir, name))
            except OSError:
                pass
