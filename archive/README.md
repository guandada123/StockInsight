# archive/

历史杂物归档（2026-10-18 审计整理）。均为一次性产物或与代码无关的资料，
保留仅为追溯，可整体删除。

- `reading/` — 散户实战学习资料（docx，2026-06 放入）
- `final_picks.txt` / `final_top10_longterm.csv` — 2026-06 选股快照产物
- `overview-ci-fix-sprint.md` — 2026-06 CI 修复 sprint 笔记

注意：根目录 `mainboard_owned_*.json`、`alerts.json`、`.nginx-local.conf` **不在归档范围**
（分别被 cli_core/feishu_push/backend 的 glob"取最新"逻辑与 config.ALERTS_PATH 运行时引用）。

- `deprecated/reporter.py` — 2026-10-18 软删除：docx 周报生成器，零生产调用方
  （唯一消费者是同目录 test_reporter.py 的 31 个测试），无 CLI/__main__/文档引用。
  恢复方式：`git mv archive/deprecated/reporter.py stock_analyzer/reporter.py`
  （测试同理），并在 `stock_analyzer/tests/oversized_functions_baseline.json`
  恢复 `stock_analyzer/reporter.py: 1` 键。python-docx 依赖保留（gen_docx_report.py 仍在用）。
