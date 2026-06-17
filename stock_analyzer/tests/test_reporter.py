"""reporter.py 单元测试 — DOCX 报告生成模块"""

import os
import sys
from datetime import datetime, time
from typing import Any
from unittest.mock import MagicMock, call, patch, PropertyMock

import pandas as pd
import pytest

# ══════════════════════════════════════════════════════════════════════
# Mock python-docx 模块树（必须在 import reporter 之前完成）
# ══════════════════════════════════════════════════════════════════════
_MOCK_DOCX_MODULES = {
    "docx": MagicMock(),
    "docx.enum": MagicMock(),
    "docx.enum.table": MagicMock(),
    "docx.enum.text": MagicMock(),
    "docx.oxml": MagicMock(),
    "docx.oxml.ns": MagicMock(),
    "docx.shared": MagicMock(),
}

# 枚举值 —— 用简单对象而非 MagicMock 以便 isinstance / 属性访问
class _WDTableAlign:
    CENTER = "center"

class _WDAlignParagraph:
    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    JUSTIFY = "justify"

_MOCK_DOCX_MODULES["docx.enum.table"].WD_TABLE_ALIGNMENT = _WDTableAlign()
_MOCK_DOCX_MODULES["docx.enum.text"].WD_ALIGN_PARAGRAPH = _WDAlignParagraph()
_MOCK_DOCX_MODULES["docx.oxml"].OxmlElement = MagicMock(
    return_value=MagicMock()
)
_MOCK_DOCX_MODULES["docx.oxml.ns"].qn = MagicMock(
    side_effect=lambda x: f"ns:{x}"
)
_MOCK_DOCX_MODULES["docx.shared"].Cm = MagicMock(
    side_effect=lambda x: f"cm:{x}"
)
_MOCK_DOCX_MODULES["docx.shared"].Pt = MagicMock(
    side_effect=lambda x: f"pt:{x}"
)
_MOCK_DOCX_MODULES["docx.shared"].RGBColor = MagicMock(
    return_value="mock_rgb"
)

# Document 类 —— 提供一个可用的 mock
_DOCUMENT_CLASS = MagicMock()

for mod_name, mod_val in _MOCK_DOCX_MODULES.items():
    sys.modules[mod_name] = mod_val

_MOCK_DOCX_MODULES["docx"].Document = _DOCUMENT_CLASS
sys.modules["docx"] = _MOCK_DOCX_MODULES["docx"]

# 现在安全导入 reporter
from stock_analyzer import reporter

# ══════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_doc():
    """返回一个可用的 mock Document 实例"""
    doc = MagicMock()
    doc.add_paragraph.return_value = MagicMock()
    doc.add_heading.return_value = MagicMock()
    doc.add_table.return_value = MagicMock()
    doc.sections = [MagicMock()]
    return doc

@pytest.fixture
def sample_sectors():
    """模拟板块 DataFrame"""
    return pd.DataFrame(
        {
            "板块名称": ["银行", "半导体", "新能源"],
            "涨跌幅": [2.5, -1.2, 0.8],
            "上涨家数": [30, 15, 20],
            "下跌家数": [5, 25, 10],
            "总成交额": [5e9, 8e9, 3e9],
            "评分": [85.0, 72.5, 68.0],
        }
    )

@pytest.fixture
def sample_picks():
    """模拟推荐股票 DataFrame"""
    return pd.DataFrame(
        {
            "代码": ["600001", "600002"],
            "名称": ["测试银行", "测试半导体"],
            "板块": ["银行", "半导体"],
            "最新价": [10.5, 25.3],
            "涨跌幅": [1.2, -0.5],
            "量比": [1.5, 0.8],
        }
    )

@pytest.fixture
def sample_details():
    """模拟股票详情"""
    return {
        "600001": {
            "kline_chart": "/tmp/kline_600001.png",
            "indicator_chart": "/tmp/ind_600001.png",
            "fundflow_chart": "/tmp/flow_600001.png",
            "technical": {
                "最新收盘": 10.5,
                "涨跌幅": 1.2,
                "近5日涨跌幅": 3.5,
                "近20日涨跌幅": 8.2,
                "MACD": {"DIF": 0.5, "DEA": 0.3, "信号": "金叉"},
                "RSI": {"值": 65, "信号": "中性"},
                "KDJ": {"K": 80, "D": 70, "J": 100, "信号": "超买"},
                "均线": {
                    "MA5": {"值": 10.2, "股价位置": "上方"},
                    "MA10": {"值": 9.8, "股价位置": "上方"},
                    "MA20": {"值": 9.5, "股价位置": "上方"},
                },
            },
            "fundamentals": {"ROE": 15.5, "营收增长": 20.3, "毛利率": 45.0},
            "fundamental_score": 75,
            "tech_score": 80,
        },
        "600002": {
            "kline_chart": "",
            "indicator_chart": "",
            "fundflow_chart": "",
            "technical": {},
            "fundamentals": {},
            "fundamental_score": None,
            "tech_score": None,
        },
    }

# ══════════════════════════════════════════════════════════════════════
# Tests — add_title
# ══════════════════════════════════════════════════════════════════════

class TestAddTitle:
    def test_level_0_calls_heading_level_1(self, mock_doc):
        """level=0 → doc.add_heading(text, level=1)"""
        result = reporter.add_title(mock_doc, "标题", level=0)
        mock_doc.add_heading.assert_called_once_with("标题", level=1)
        assert result == mock_doc.add_heading.return_value

    def test_level_1_calls_heading_level_2(self, mock_doc):
        """level=1 → doc.add_heading(text, level=2)"""
        result = reporter.add_title(mock_doc, "子标题", level=1)
        mock_doc.add_heading.assert_called_once_with("子标题", level=2)
        assert result == mock_doc.add_heading.return_value

    def test_level_2_calls_heading_level_3(self, mock_doc):
        """level=2 → doc.add_heading(text, level=3)"""
        result = reporter.add_title(mock_doc, "子子标题", level=2)
        mock_doc.add_heading.assert_called_once_with("子子标题", level=3)

    def test_default_level_is_0(self, mock_doc):
        """默认 level=0"""
        reporter.add_title(mock_doc, "默认")
        mock_doc.add_heading.assert_called_once_with("默认", level=1)

# ══════════════════════════════════════════════════════════════════════
# Tests — add_para
# ══════════════════════════════════════════════════════════════════════

class TestAddPara:
    def test_basic(self, mock_doc):
        """基本段落"""
        result = reporter.add_para(mock_doc, "Hello")
        mock_doc.add_paragraph.assert_called_once()
        p = mock_doc.add_paragraph.return_value
        p.add_run.assert_called_once_with("Hello")
        run = p.add_run.return_value
        assert run.font.size == "pt:10"
        assert run.bold is False
        assert result == p

    def test_bold(self, mock_doc):
        """加粗"""
        reporter.add_para(mock_doc, "粗体", bold=True)
        p = mock_doc.add_paragraph.return_value
        run = p.add_run.return_value
        assert run.bold is True

    def test_custom_size(self, mock_doc):
        """自定义字号"""
        reporter.add_para(mock_doc, "大字", size=14)
        run = mock_doc.add_paragraph.return_value.add_run.return_value
        assert run.font.size == "pt:14"

    def test_with_color(self, mock_doc):
        """带颜色"""
        color = "mock_rgb"
        reporter.add_para(mock_doc, "彩色", color=color)
        run = mock_doc.add_paragraph.return_value.add_run.return_value
        assert run.font.color.rgb == color

    def test_with_alignment(self, mock_doc):
        """带对齐方式"""
        align = _MOCK_DOCX_MODULES["docx.enum.text"].WD_ALIGN_PARAGRAPH.CENTER
        reporter.add_para(mock_doc, "居中", align=align)
        p = mock_doc.add_paragraph.return_value
        assert p.alignment == align

# ══════════════════════════════════════════════════════════════════════
# Tests — add_image
# ══════════════════════════════════════════════════════════════════════

class TestAddImage:
    def test_path_exists(self, mock_doc):
        """路径存在 → 添加图片"""
        with patch("os.path.exists", return_value=True):
            result = reporter.add_image(mock_doc, "/tmp/img.png", width=14)
        mock_doc.add_picture.assert_called_once_with(
            "/tmp/img.png", width="cm:14"
        )
        assert result is True

    def test_path_none(self, mock_doc):
        """path 为 None → 不添加"""
        result = reporter.add_image(mock_doc, None, width=14)
        mock_doc.add_picture.assert_not_called()
        assert result is False

    def test_path_not_exists(self, mock_doc):
        """路径不存在 → 不添加"""
        with patch("os.path.exists", return_value=False):
            result = reporter.add_image(mock_doc, "/tmp/notexist.png")
        mock_doc.add_picture.assert_not_called()
        assert result is False

    def test_custom_width(self, mock_doc):
        """自定义宽度"""
        with patch("os.path.exists", return_value=True):
            reporter.add_image(mock_doc, "/tmp/img.png", width=10)
        mock_doc.add_picture.assert_called_once_with(
            "/tmp/img.png", width="cm:10"
        )

# ══════════════════════════════════════════════════════════════════════
# Tests — _set_cell_shading
# ══════════════════════════════════════════════════════════════════════

class TestSetCellShading:
    def test_sets_shading(self):
        """设置单元格底色"""
        cell = MagicMock()
        cell._tc.get_or_add_tcPr.return_value = MagicMock()

        reporter._set_cell_shading(cell, "FF0000")

        OxmlElement = _MOCK_DOCX_MODULES["docx.oxml"].OxmlElement
        OxmlElement.assert_called_once_with("w:shd")
        shading_elem = OxmlElement.return_value

        # 验证设置属性
        qn_func = _MOCK_DOCX_MODULES["docx.oxml.ns"].qn
        # qn 被调用了两次：一次 w:fill，一次 w:val
        qn_calls = qn_func.call_args_list
        assert any(c == call("w:fill") for c in qn_calls)
        assert any(c == call("w:val") for c in qn_calls)

        shading_elem.set.assert_any_call("ns:w:fill", "FF0000")
        shading_elem.set.assert_any_call("ns:w:val", "clear")

        tc_pr = cell._tc.get_or_add_tcPr.return_value
        tc_pr.append.assert_called_once_with(shading_elem)

# ══════════════════════════════════════════════════════════════════════
# Tests — _make_header_row
# ══════════════════════════════════════════════════════════════════════

class TestMakeHeaderRow:
    def test_sets_headers(self):
        """设置表头内容、样式、底色"""
        table = MagicMock()
        headers = ["代码", "名称", "价格"]
        row_cells = [MagicMock() for _ in range(3)]
        table.rows = [MagicMock()]
        table.rows[0].cells = row_cells

        reporter._make_header_row(table, headers, color="FF0000")

        for i, h in enumerate(headers):
            cell = row_cells[i]
            assert cell.text == ""
            p = cell.paragraphs[0]
            assert p.alignment == _MOCK_DOCX_MODULES[
                "docx.enum.text"
            ].WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run.return_value
            p.add_run.assert_called_once_with(h)
            assert run.bold is True
            assert run.font.size == "pt:9"
            assert run.font.color.rgb == "mock_rgb"

    def test_default_color(self):
        """默认颜色 4472C4"""
        table = MagicMock()
        table.rows = [MagicMock()]
        table.rows[0].cells = [MagicMock()]

        reporter._make_header_row(table, ["A"])
        OxmlElement = _MOCK_DOCX_MODULES["docx.oxml"].OxmlElement
        OxmlElement.assert_called_with("w:shd")
        shading_elem = OxmlElement.return_value
        shading_elem.set.assert_any_call("ns:w:fill", "4472C4")

# ══════════════════════════════════════════════════════════════════════
# Tests — _add_table_row
# ══════════════════════════════════════════════════════════════════════

class TestAddTableRow:
    def test_adds_values(self):
        """添加数据行"""
        table = MagicMock()
        new_row = MagicMock()
        new_row.cells = [MagicMock() for _ in range(5)]
        table.add_row.return_value = new_row

        reporter._add_table_row(table, ["A", "B", "C"])

        table.add_row.assert_called_once()
        for i, val in enumerate(["A", "B", "C"]):
            cell = new_row.cells[i]
            assert cell.text == ""
            run = cell.paragraphs[0].add_run.return_value
            cell.paragraphs[0].add_run.assert_called_once_with(str(val))
            assert run.font.size == "pt:9"

    def test_bold_row(self):
        """加粗行"""
        table = MagicMock()
        new_row = MagicMock()
        new_row.cells = [MagicMock()]
        table.add_row.return_value = new_row

        reporter._add_table_row(table, ["X"], bold=True)
        run = new_row.cells[0].paragraphs[0].add_run.return_value
        assert run.bold is True

    def test_numeric_values(self):
        """数值类型转为字符串"""
        table = MagicMock()
        new_row = MagicMock()
        new_row.cells = [MagicMock() for _ in range(3)]
        table.add_row.return_value = new_row

        reporter._add_table_row(table, [123, 45.6])
        new_row.cells[0].paragraphs[0].add_run.assert_called_once_with(
            "123"
        )
        new_row.cells[1].paragraphs[0].add_run.assert_called_once_with(
            "45.6"
        )

# ══════════════════════════════════════════════════════════════════════
# Tests — _create_table
# ══════════════════════════════════════════════════════════════════════

class TestCreateTable:
    def test_create_basic(self, mock_doc):
        """基本表格创建"""
        headers = ["A", "B"]
        rows = [["1", "2"], ["3", "4"]]

        table = mock_doc.add_table.return_value
        table.rows = [MagicMock()]
        table.rows[0].cells = [MagicMock() for _ in range(2)]

        result = reporter._create_table(mock_doc, headers, rows)

        mock_doc.add_table.assert_called_once_with(rows=1, cols=2)
        assert table.style == "Table Grid"
        assert result == table

    def test_with_col_widths(self, mock_doc):
        """自定义列宽"""
        headers = ["A", "B", "C"]
        rows = [["1", "2", "3"]]
        col_widths = [3, 5, 4]

        table = mock_doc.add_table.return_value
        fake_row1 = MagicMock()
        fake_row1.cells = [MagicMock() for _ in range(3)]
        fake_row2 = MagicMock()
        fake_row2.cells = [MagicMock() for _ in range(3)]
        table.rows = [fake_row1, fake_row2]

        reporter._create_table(mock_doc, headers, rows, col_widths)

        # 两行都设置了列宽
        for row in [fake_row1, fake_row2]:
            for i, w in enumerate(col_widths):
                assert row.cells[i].width == f"cm:{w}"

    def test_col_widths_shorter_than_headers(self, mock_doc):
        """列宽列表比表头短时不越界"""
        headers = ["A", "B", "C"]
        rows = [["1", "2", "3"]]
        col_widths = [3]  # 只有1个

        table = mock_doc.add_table.return_value
        fake_row = MagicMock()
        fake_row.cells = [MagicMock() for _ in range(3)]
        table.rows = [fake_row, fake_row]

        # 不应抛出 IndexError
        reporter._create_table(mock_doc, headers, rows, col_widths)
        assert fake_row.cells[0].width == "cm:3"

# ══════════════════════════════════════════════════════════════════════
# Tests — generate_report
# ══════════════════════════════════════════════════════════════════════

class TestGenerateReport:
    def mk_doc(self):
        """创建一个结构更完善的 mock doc，便于验证调用"""
        doc = MagicMock()
        doc.add_paragraph.return_value = MagicMock()
        doc.add_heading.return_value = MagicMock()
        doc.add_table.return_value = MagicMock()
        doc.sections = [MagicMock()]
        return doc

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    @patch("stock_analyzer.reporter.os.path.exists", return_value=True)
    def test_basic_report_with_all_data(
        self, mock_exists, mock_makedirs, mock_document_class
    ):
        """完整报告：有板块、有推荐、有详情"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        sectors = pd.DataFrame(
            {
                "板块名称": ["银行"],
                "涨跌幅": [2.5],
                "上涨家数": [30],
                "下跌家数": [5],
                "总成交额": [5e9],
                "评分": [85.0],
            }
        )
        picks = pd.DataFrame(
            {
                "代码": ["600001"],
                "名称": ["测试银行"],
                "板块": ["银行"],
                "最新价": [10.5],
                "涨跌幅": [1.2],
                "量比": [1.5],
            }
        )
        details = {
            "600001": {
                "kline_chart": "/tmp/k.png",
                "indicator_chart": "/tmp/i.png",
                "fundflow_chart": "/tmp/f.png",
                "technical": {
                    "最新收盘": 10.5,
                    "涨跌幅": 1.2,
                    "近5日涨跌幅": 3.5,
                    "近20日涨跌幅": 8.2,
                    "MACD": {"DIF": 0.5, "DEA": 0.3, "信号": "金叉"},
                    "RSI": {"值": 65, "信号": "中性"},
                    "KDJ": {"K": 80, "D": 70, "J": 100, "信号": "超买"},
                    "均线": {
                        "MA5": {"值": 10.2, "股价位置": "上方"},
                        "MA10": {"值": 9.8, "股价位置": "上方"},
                    },
                },
                "fundamentals": {"ROE": 15.5},
                "fundamental_score": 75,
                "tech_score": 80,
            }
        }

        result = reporter.generate_report(sectors, picks, details)

        # save 被调用
        doc.save.assert_called_once()
        # REPORT_DIR 被创建
        mock_makedirs.assert_called_once()
        # 返回路径
        assert result is not None
        assert result.endswith(".docx")

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    def test_empty_sectors(
        self, mock_makedirs, mock_document_class
    ):
        """sectors_df 为空 → 跳过排行榜和深度分析"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        empty_sectors = pd.DataFrame()
        picks = pd.DataFrame(
            {
                "代码": ["600001"],
                "名称": ["测试"],
                "板块": ["银行"],
                "最新价": [10.0],
                "涨跌幅": [1.0],
                "量比": [1.0],
            }
        )

        result = reporter.generate_report(empty_sectors, picks, {})
        doc.save.assert_called_once()
        assert result is not None

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    def test_empty_picks(
        self, mock_makedirs, mock_document_class
    ):
        """picks_df 为空 → 跳过推荐汇总"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        sectors = pd.DataFrame(
            {
                "板块名称": ["银行"],
                "涨跌幅": [1.0],
                "上涨家数": [10],
                "下跌家数": [5],
                "总成交额": [1e9],
                "评分": [80.0],
            }
        )

        result = reporter.generate_report(sectors, pd.DataFrame(), {})
        doc.save.assert_called_once()
        assert result is not None

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    def test_three_sectors_top3(
        self, mock_makedirs, mock_document_class
    ):
        """3 个板块 → TOP 3 深度分析生成"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        sectors = pd.DataFrame(
            {
                "板块名称": ["银行", "半导体", "新能源"],
                "涨跌幅": [2.5, -1.2, 0.8],
                "上涨家数": [30, 15, 20],
                "下跌家数": [5, 25, 10],
                "总成交额": [5e9, 8e9, 3e9],
                "评分": [85.0, 72.5, 68.0],
            }
        )

        result = reporter.generate_report(sectors, pd.DataFrame(), {})
        doc.save.assert_called_once()
        assert result is not None

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    def test_custom_output_name(
        self, mock_makedirs, mock_document_class
    ):
        """自定义输出文件名"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        result = reporter.generate_report(
            pd.DataFrame(), pd.DataFrame(), {}, output_name="my_report.docx"
        )
        assert result is not None
        assert "my_report.docx" in result

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    def test_no_images(self, mock_makedirs, mock_document_class):
        """股票详情中图片路径为空"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        sectors = pd.DataFrame(
            {
                "板块名称": ["银行"],
                "涨跌幅": [1.0],
                "上涨家数": [10],
                "下跌家数": [5],
                "总成交额": [1e9],
                "评分": [80.0],
            }
        )
        picks = pd.DataFrame(
            {
                "代码": ["600001"],
                "名称": ["测试"],
                "板块": ["银行"],
                "最新价": [10.0],
                "涨跌幅": [1.0],
                "量比": [1.0],
            }
        )
        details: dict[str, dict[str, Any]] = {
            "600001": {
                "kline_chart": "",
                "indicator_chart": "",
                "fundflow_chart": "",
                "technical": {},
                "fundamentals": {},
                "fundamental_score": None,
                "tech_score": None,
            }
        }

        result = reporter.generate_report(sectors, picks, details)
        doc.save.assert_called_once()
        assert result is not None

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    @patch("stock_analyzer.reporter.os.path.exists", return_value=True)
    def test_images_exist(
        self, mock_exists, mock_makedirs, mock_document_class
    ):
        """所有图片路径都存在"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        sectors = pd.DataFrame(
            {
                "板块名称": ["银行"],
                "涨跌幅": [1.0],
                "上涨家数": [10],
                "下跌家数": [5],
                "总成交额": [1e9],
                "评分": [80.0],
            }
        )
        picks = pd.DataFrame(
            {
                "代码": ["600001"],
                "名称": ["测试"],
                "板块": ["银行"],
                "最新价": [10.0],
                "涨跌幅": [1.0],
                "量比": [1.0],
            }
        )
        details = {
            "600001": {
                "kline_chart": "/tmp/k.png",
                "indicator_chart": "/tmp/i.png",
                "fundflow_chart": "/tmp/f.png",
                "technical": {},
                "fundamentals": {},
            }
        }

        result = reporter.generate_report(sectors, picks, details)
        doc.save.assert_called_once()
        assert result is not None

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    @patch("stock_analyzer.reporter.os.path.exists", return_value=False)
    def test_images_not_exist(
        self, mock_exists, mock_makedirs, mock_document_class
    ):
        """图片路径存在但文件不存在"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        sectors = pd.DataFrame(
            {
                "板块名称": ["银行"],
                "涨跌幅": [1.0],
                "上涨家数": [10],
                "下跌家数": [5],
                "总成交额": [1e9],
                "评分": [80.0],
            }
        )
        picks = pd.DataFrame(
            {
                "代码": ["600001"],
                "名称": ["测试"],
                "板块": ["银行"],
                "最新价": [10.0],
                "涨跌幅": [1.0],
                "量比": [1.0],
            }
        )
        details = {
            "600001": {
                "kline_chart": "/tmp/nope.png",
                "indicator_chart": "/tmp/nope.png",
                "fundflow_chart": "/tmp/nope.png",
                "technical": {},
                "fundamentals": {},
            }
        }

        result = reporter.generate_report(sectors, picks, details)
        doc.save.assert_called_once()
        assert result is not None

    @patch("stock_analyzer.reporter.Document")
    @patch("stock_analyzer.reporter.os.makedirs")
    def test_high_funda_score_green(
        self, mock_makedirs, mock_document_class
    ):
        """基本面评分≥60 显示绿色"""
        doc = self.mk_doc()
        mock_document_class.return_value = doc

        sectors = pd.DataFrame(
            {
                "板块名称": ["银行"],
                "涨跌幅": [1.0],
                "上涨家数": [10],
                "下跌家数": [5],
                "总成交额": [1e9],
                "评分": [80.0],
            }
        )
        picks = pd.DataFrame(
            {
                "代码": ["600001"],
                "名称": ["测试"],
                "板块": ["银行"],
                "最新价": [10.0],
                "涨跌幅": [1.0],
                "量比": [1.0],
            }
        )
        details = {
            "600001": {
                "kline_chart": "",
                "indicator_chart": "",
                "fundflow_chart": "",
                "technical": {},
                "fundamentals": {},
                "fundamental_score": 85,
                "tech_score": 90,
            }
        }

        result = reporter.generate_report(sectors, picks, details)
        doc.save.assert_called_once()
        assert result is not None
