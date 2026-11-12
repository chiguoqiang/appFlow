"""checks 模块测试：markdown 解析、manifest 校验、规则引擎。"""

from __future__ import annotations

import pytest

from pipeline_cli.checks import (
    MarkdownDoc,
    evaluate_ruleset,
    norm_title,
    summarize,
    validate_manifest,
)


class TestNormTitle:
    def test_strips_numbering(self):
        assert norm_title("5. 统计口径") == "统计口径"
        # 编号 + 括号内容 + 填充词全部剥离
        assert norm_title("5.1 统计与业务口径（强制）") == "统计业务口径"

    def test_strips_filler(self):
        # 括号内容整体移除（不保留），填充词也移除
        assert norm_title("数据模型（概念级）") == "数据模型"
        assert norm_title("Figma 链接与 node ID") == "figma链接nodeid"


class TestMarkdownDoc:
    def test_parses_sections(self):
        doc = MarkdownDoc("# T\n\n## A\n\n内容A\n\n### 三级标题\n\n## B\n\n内容B")
        # 一级标题也算一个 section（T），三级标题不切分
        assert [s.title for s in doc.sections] == ["T", "A", "B"]
        assert "### 三级标题" in doc.section("A").body  # 三级标题归入上级

    def test_finds_section_by_normalized_title(self):
        doc = MarkdownDoc("## 5.1 统计与业务口径（强制）\n\n内容")
        assert doc.section("统计口径") is not None
        assert doc.section("统计与业务口径") is not None

    def test_parses_table(self):
        doc = MarkdownDoc(
            "## 表\n\n| # | 名称 |\n|---|------|\n| A-1 | 甲 |\n| A-2 | 乙 |\n"
        )
        t = doc.section("表").table()
        assert t.headers == ["#", "名称"]
        assert len(t.rows) == 2
        assert t.column("名称") == ["甲", "乙"]

    def test_table_column_name_tolerates_space(self):
        doc = MarkdownDoc("## T\n\n| 页面 ID | 名 |\n|---|---|\n| PG-01 | 首页 |\n")
        t = doc.section("T").table()
        assert t.has_column("页面ID")

    def test_extracts_json_block(self):
        doc = MarkdownDoc('## C\n\n```json\n{"a": 1}\n```\n')
        assert doc.section("C").fenced("json") == ['{"a": 1}']

    def test_bullets(self):
        doc = MarkdownDoc("## L\n\n- 一\n- 二\n\n1. 三\n")
        assert doc.section("L").bullets() == ["一", "二", "三"]


class TestValidateManifest:
    def test_passes_on_valid_doc(self, sample_manifest, valid_prd_text):
        result = validate_manifest(valid_prd_text, sample_manifest)
        assert result.ok, result.render()

    def test_detects_missing_section(self, sample_manifest):
        result = validate_manifest("# PRD\n\n## 用户故事\n\n无\n", sample_manifest)
        assert not result.ok
        kinds = {v.kind for v in result.violations}
        assert "missing_section" in kinds
        # 缺的是「任务拆解」
        assert any("任务拆解" in v.message for v in result.violations)

    def test_detects_missing_column(self, sample_manifest):
        text = """## 用户故事

| # | 用户故事 |
|---|---|
| US-1 | 故事 |

## 任务拆解

| # | 任务 | 前置依赖 | 验收方式 |
|---|---|---|---|
| T-01 | 实现 | 无 | 测试 |
"""
        result = validate_manifest(text, sample_manifest)
        assert not result.ok
        assert any(v.kind == "missing_column" for v in result.violations)

    def test_detects_bad_row_id(self, sample_manifest):
        text = """## 用户故事

| # | 用户故事 | 优先级 | 验收标准 |
|---|---|---|---|
| 第1条 | 故事 | P0 | 标准 |

## 任务拆解

| # | 任务 | 前置依赖 | 验收方式 |
|---|---|---|---|
| T-01 | 实现 | 无 | 测试 |
"""
        result = validate_manifest(text, sample_manifest)
        assert any(v.kind == "bad_row_id" for v in result.violations)

    def test_detects_placeholder(self, sample_manifest, valid_prd_text):
        text = valid_prd_text.replace("点击后立即变已打卡", "{{待填}}")
        result = validate_manifest(text, sample_manifest)
        assert any(v.kind == "placeholder" for v in result.violations)

    def test_fail_on_missing_section_only(self, sample_manifest):
        # 只有列缺失，没有章节缺失 → fail_on=missing_section 应通过
        text = """## 用户故事

| # | 用户故事 |
|---|---|
| US-1 | 故事 |

## 任务拆解

| # | 任务 | 前置依赖 | 验收方式 |
|---|---|---|---|
| T-01 | 实现 | 无 | 测试 |
"""
        result = validate_manifest(text, sample_manifest, fail_on="missing_section")
        assert result.ok


# ---------------------------------------------------------------------------
# 规则引擎
# ---------------------------------------------------------------------------

def _rules(rule: dict) -> dict:
    return {"ruleset": "test", "rules": [rule]}


class TestRuleEngine:
    def test_qg01_blocks_high_severity(self):
        doc = MarkdownDoc(
            """## 缺陷清单

| # | 缺陷 | 严重度 | 复现步骤 | 关联用例 | 状态 |
|---|---|---|---|---|---|
| BUG-01 | 死页面 | 高 | 点删除 | TC-01 | 待修复 |
| BUG-02 | 文案错 | 低 | 看 | TC-02 | 待修复 |
"""
        )
        ruleset = _rules(
            {
                "id": "QG-01",
                "name": "高严重度必须清零",
                "severity": "blocker",
                "when": {
                    "table": "缺陷清单",
                    "column": "严重度",
                    "equals": "高",
                    "count_gt": 0,
                },
                "then": {"message": "有高严重度缺陷"},
            }
        )
        results = evaluate_ruleset(ruleset=ruleset, doc=doc)
        assert len(results) == 1
        assert results[0].verdict == "fail"
        assert "1 行" in results[0].detail

    def test_qg01_passes_when_no_high(self):
        doc = MarkdownDoc(
            """## 缺陷清单

| # | 缺陷 | 严重度 |
|---|---|---|
| BUG-01 | 文案错 | 低 |
"""
        )
        ruleset = _rules(
            {
                "id": "QG-01",
                "name": "高严重度必须清零",
                "severity": "blocker",
                "when": {
                    "table": "缺陷清单",
                    "column": "严重度",
                    "equals": "高",
                    "count_gt": 0,
                },
                "then": {"message": "有高严重度缺陷"},
            }
        )
        assert evaluate_ruleset(ruleset=ruleset, doc=doc)[0].verdict == "pass"

    def test_qg04_edge_case_count(self):
        doc = MarkdownDoc(
            """## 边界用例

| # | 边界场景 | 结果 |
|---|---|---|
| TC-E1 | 空数据 | ✅ |
"""
        )
        ruleset = _rules(
            {
                "id": "QG-04",
                "name": "边界用例下限",
                "severity": "major",
                "when": {"table": "边界用例", "row_count_lt": 3},
                "then": {"message": "边界用例不足"},
            }
        )
        r = evaluate_ruleset(ruleset=ruleset, doc=doc)[0]
        assert r.verdict == "fail"
        assert "1 行" in r.detail

    def test_dr06_impossible_claim_without_proof(self):
        doc = MarkdownDoc(
            """## 已知问题与风险

K-4：当 done>due 的可能性不存在，逻辑自洽。
"""
        )
        ruleset = _rules(
            {
                "id": "DR-06",
                "name": "不可能断言须证明",
                "severity": "blocker",
                "when": {
                    "claim_without_proof": {
                        "triggers": ["不可能", "不存在"],
                        "evidence_required_any": ["证明", "构造", "反例", "测试验证", "假设待验证"],
                        "window_lines": 3,
                    }
                },
                "then": {"message": "未证明"},
            }
        )
        r = evaluate_ruleset(ruleset=ruleset, doc=doc)[0]
        assert r.verdict == "fail"

    def test_dr06_passes_with_proof(self):
        doc = MarkdownDoc(
            """## 已知问题与风险

K-4：done>due 不可能（构造性证明：已穷举 N∈1..7，见 TC-02）。
"""
        )
        ruleset = _rules(
            {
                "id": "DR-06",
                "name": "不可能断言须证明",
                "severity": "blocker",
                "when": {
                    "claim_without_proof": {
                        "triggers": ["不可能"],
                        "evidence_required_any": ["证明", "构造", "反例"],
                        "window_lines": 3,
                    }
                },
                "then": {"message": "未证明"},
            }
        )
        assert evaluate_ruleset(ruleset=ruleset, doc=doc)[0].verdict == "pass"

    def test_dr01_requires_stats_section(self):
        doc = MarkdownDoc("## 产品概述\n\n用户每天打卡，统计连续天数与完成率。\n")
        ruleset = _rules(
            {
                "id": "DR-01",
                "name": "含计数须定义口径",
                "severity": "major",
                "when": {
                    "document_contains_any": ["每天", "完成率", "连续"],
                    "lacks_section_any": ["统计口径", "统计定义"],
                },
                "then": {"message": "缺口径定义"},
            }
        )
        r = evaluate_ruleset(ruleset=ruleset, doc=doc)[0]
        assert r.verdict == "fail"

    def test_dr01_passes_when_section_present(self):
        doc = MarkdownDoc(
            "## 产品概述\n\n用户每天打卡，统计完成率。\n\n## 统计口径\n\n完成率 = 实际/应打卡。\n"
        )
        ruleset = _rules(
            {
                "id": "DR-01",
                "name": "含计数须定义口径",
                "severity": "major",
                "when": {
                    "document_contains_any": ["每天", "完成率"],
                    "lacks_section_any": ["统计口径"],
                },
                "then": {"message": "缺口径"},
            }
        )
        assert evaluate_ruleset(ruleset=ruleset, doc=doc)[0].verdict == "pass"

    def test_dr05_forbids_hardcoded_grid(self):
        doc = MarkdownDoc("## 逐页设计指令\n\n热力图按 5 行×7 列布局。\n")
        ruleset = _rules(
            {
                "id": "DR-05",
                "name": "网格须写公式",
                "severity": "major",
                "when": {
                    "forbid_pattern": {
                        "scope": "逐页设计指令",
                        "patterns": [
                            "\\d+\\s*行\\s*[×x]\\s*\\d+\\s*列",
                            "\\d+\\s*列\\s*[×x]\\s*\\d+\\s*行",
                        ],
                    }
                },
                "then": {"message": "写死了行列"},
            }
        )
        assert evaluate_ruleset(ruleset=ruleset, doc=doc)[0].verdict == "fail"

    def test_unimplemented_rule_is_skipped_not_passed(self):
        doc = MarkdownDoc("## X\n\n内容")
        ruleset = _rules(
            {
                "id": "XX-99",
                "name": "未知规则",
                "severity": "major",
                "when": {"some_unknown_structure": True},
                "then": {"message": "?"},
            }
        )
        r = evaluate_ruleset(ruleset=ruleset, doc=doc)[0]
        assert r.verdict == "skip"
        assert "未识别" in r.message

    def test_summarize_counts_failures(self):
        doc = MarkdownDoc("## 缺陷清单\n\n| # | 严重度 |\n|---|---|\n| 1 | 高 |\n")
        ruleset = _rules(
            {
                "id": "QG-01",
                "name": "高严重度",
                "severity": "blocker",
                "when": {
                    "table": "缺陷清单",
                    "column": "严重度",
                    "equals": "高",
                    "count_gt": 0,
                },
                "then": {"message": "有高严重度"},
            }
        )
        results = evaluate_ruleset(ruleset=ruleset, doc=doc)
        ok, summary = summarize(results)
        assert not ok
        assert "1 条规则失败" in summary
