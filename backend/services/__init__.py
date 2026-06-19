"""StockInsight — 服务层（业务逻辑下沉）

每个 service 模块封装一个领域的核心逻辑，
router 层只保留路由注册和参数校验，实际处理委托给 service。

模块索引:
    analysis_service   — 个股七层分析（L0-L7 + 多空辩论 + ML）
    market_service     — 大盘行情、板块轮动
    portfolio_service  — 持仓组合 CRUD 与分析
    data_service       — 数据管理（SQLite 统计/缓存/导入导出）
    scan_service       — 批量扫描与进度跟踪
"""
