"""operations 层测试（Web 与 CLI 共用的业务逻辑）。"""

from __future__ import annotations

import pytest

from pipeline_cli import operations as ops
from pipeline_cli.errors import GateError, PipelineError


@pytest.fixture()
def project(paths):
    ops.create_project(paths, codename="web-test")
    return "web-test"


class TestCreateProject:
    def test_creates_state_and_dirs(self, paths):
        r = ops.create_project(paths, codename="p1")
        assert r["ok"] and r["stages"] == 6 and r["deliverables"] == 7
        assert (paths.projects / "p1" / "pipeline-state.json").exists()

    def test_rejects_invalid_codename(self, paths):
        for bad in ["", "with space", "../evil", "a" * 60]:
            with pytest.raises(PipelineError):
                ops.create_project(paths, codename=bad)

    def test_rejects_duplicate(self, paths):
        ops.create_project(paths, codename="dup")
        with pytest.raises(PipelineError):
            ops.create_project(paths, codename="dup")

    def test_force_overwrites(self, paths):
        ops.create_project(paths, codename="dup2")
        r = ops.create_project(paths, codename="dup2", force=True)
        assert r["ok"]

    def test_requirement_flow_needs_target(self, paths):
        with pytest.raises(PipelineError):
            ops.create_project(paths, codename="r1", flow="new_requirement")

    def test_requirement_flow_ok_with_target(self, paths):
        r = ops.create_project(
            paths, codename="r2", flow="new_requirement", target_project="demo-habit"
        )
        assert r["ok"] and r["deliverables"] == 7


class TestListAndDetail:
    def test_list_empty(self, paths):
        assert ops.list_projects(paths) == []

    def test_list_contains_project(self, paths, project):
        projects = ops.list_projects(paths)
        assert len(projects) == 1
        p = projects[0]
        assert p["codename"] == project
        assert p["current_stage"] == "brief"
        assert p["progress"]["total"] == 6
        assert p["awaiting_review"] is False

    def test_detail_structure(self, paths, project):
        d = ops.project_detail(paths, project)
        assert d["codename"] == project
        assert len(d["stages"]) == 6
        assert len(d["deliverables"]) == 7
        assert d["current_sop"]["id"] == "00-brief"
        assert d["actions"]["run"] is True
        assert d["actions"]["gate"] is False

    def test_detail_marks_awaiting_review(self, paths, project):
        ops.write_deliverable(paths, project, "project_brief", _valid_brief(project))
        ops.submit_deliverable(paths, project, stage="brief")
        d = ops.project_detail(paths, project)
        assert d["stages"][0]["status"] == "awaiting_review"
        assert d["actions"]["gate"] is True
        assert d["actions"]["run"] is False


class TestDeliverableIO:
    def test_read_sem_empty_when_no_template(self, paths, project):
        # test_report 在 sandbox 中无模板 → 文件不存在
        r = ops.read_deliverable(paths, project, "test_report")
        assert r["exists"] is False and r["content"] == ""

    def test_read_seeded_from_template(self, paths, project):
        # prd 有模板 → 新建项目时已铺好骨架
        r = ops.read_deliverable(paths, project, "prd")
        assert r["exists"] is True
        assert "PRD" in r["content"]

    def test_write_then_read(self, paths, project):
        ops.write_deliverable(paths, project, "prd", "# 内容")
        r = ops.read_deliverable(paths, project, "prd")
        assert r["exists"] is True and r["content"] == "# 内容"

    def test_write_unknown_deliverable(self, paths, project):
        with pytest.raises(PipelineError):
            ops.write_deliverable(paths, project, "ghost", "x")

    def test_cannot_write_outside_project(self, paths, project):
        """防路径穿越：契约层文件不可写。"""
        from pipeline_cli.state import StateStore

        store = StateStore(paths, project)
        state = store.load()
        state.deliverable("prd").path = "pipeline/manifests/prd.manifest.yaml"
        store.save(state)
        with pytest.raises(PipelineError):
            ops.write_deliverable(paths, project, "prd", "hack")

    def test_template_available(self, paths):
        r = ops.get_template(paths, "prd")
        # sandbox 的 templates 目录只放了 01-prd.template.md
        assert r["available"] is True
        assert "PRD" in r["content"]

    def test_template_missing(self, paths):
        r = ops.get_template(paths, "test_report")
        assert r["available"] is False


class TestValidateOp:
    def test_validate_missing_file(self, paths, project):
        r = ops.validate_deliverable_op(paths, project, "project_brief")
        assert r["ok"] is False
        assert r["violations"][0]["kind"] == "missing_file"

    def test_validate_incomplete(self, paths, project):
        ops.write_deliverable(paths, project, "project_brief", "# 只有标题")
        r = ops.validate_deliverable_op(paths, project, "project_brief")
        assert r["ok"] is False
        assert len(r["violations"]) > 0

    def test_validate_complete(self, paths, project):
        ops.write_deliverable(paths, project, "project_brief", _valid_brief(project))
        r = ops.validate_deliverable_op(paths, project, "project_brief")
        assert r["ok"] is True, r["violations"]

    def test_validate_with_rules(self, paths, project):
        ops.write_deliverable(paths, project, "project_brief", _valid_brief(project))
        r = ops.validate_deliverable_op(
            paths, project, "project_brief", run_rules=True
        )
        assert "rules" in r
        assert isinstance(r["rules"], list)


class TestSubmit:
    def test_submit_invalid_returns_violations(self, paths, project):
        ops.write_deliverable(paths, project, "project_brief", "# 残缺")
        r = ops.submit_deliverable(paths, project, stage="brief")
        assert r["ok"] is False
        assert r["validation"]["ok"] is False

    def test_submit_valid_enters_review(self, paths, project):
        ops.write_deliverable(paths, project, "project_brief", _valid_brief(project))
        r = ops.submit_deliverable(paths, project, stage="brief")
        assert r["ok"] is True
        assert r["stage"] == "brief"
        assert r["version"] == 1
        assert "approve" in r["actions"]

    def test_submit_missing_file_raises(self, paths, project):
        with pytest.raises(GateError):
            ops.submit_deliverable(paths, project, stage="brief")

    def test_skip_validate_allows_submit(self, paths, project):
        ops.write_deliverable(paths, project, "project_brief", "# 残缺")
        r = ops.submit_deliverable(
            paths, project, stage="brief", skip_validate=True
        )
        assert r["ok"] is True


class TestGateOp:
    def _prepared(self, paths, project):
        ops.write_deliverable(paths, project, "project_brief", _valid_brief(project))
        ops.submit_deliverable(paths, project, stage="brief")

    def test_approve_advances(self, paths, project):
        self._prepared(paths, project)
        r = ops.apply_gate(paths, project, action="approve")
        assert r["ok"] and r["next_stage"] == "planning"
        assert r["done"] is False

    def test_revise_bumps_version(self, paths, project):
        self._prepared(paths, project)
        r = ops.apply_gate(
            paths, project, action="revise", comment="需要补充目标用户"
        )
        assert r["version"] == 2
        assert r["next_stage"] == "brief"

    def test_reject_propagates_stale(self, paths, project):
        """planning 打回 → 下游交付物全部 stale（brief 是源头，打回无下游可标记）。"""
        self._prepared(paths, project)
        ops.apply_gate(paths, project, action="approve")  # brief → planning

        # 让 planning 进入待评审（跳过校验以聚焦状态传播）
        ops.write_deliverable(paths, project, "prd", "# PRD 草稿")
        ops.submit_deliverable(
            paths, project, stage="planning", skip_validate=True
        )

        r = ops.apply_gate(
            paths, project, stage="planning", action="reject", comment="方向不对"
        )
        assert r["deliverable_status"] == "stale"
        assert "design_brief" in r["staled"]
        assert r["reopened_sop"] == "00-brief"

    def test_gate_requires_review_state(self, paths, project):
        with pytest.raises(GateError):
            ops.apply_gate(paths, project, action="approve")

    def test_comment_required_for_revise(self, paths, project):
        self._prepared(paths, project)
        with pytest.raises(GateError):
            ops.apply_gate(paths, project, action="revise", comment="")


class TestRunStage:
    def test_run_brief_needs_answers(self, paths, project):
        r = ops.run_stage(paths, project, stage="brief", answers={})
        assert r["status"] == "awaiting_review"
        assert r["needs_human"] is not None

    def test_run_brief_with_answers_reaches_gate(self, paths, project):
        r = ops.run_stage(
            paths,
            project,
            stage="brief",
            answers={
                "core-idea": "一个测试用应用",
                "target-users": "测试用户",
                "mvp-features": "核心功能",
                "out-of-scope": "不做的事",
                "tech-constraints": "Flutter",
            },
        )
        assert r["status"] == "awaiting_review"
        assert any(s["action"] == "human_gate" for s in r["steps"])


# ---------------------------------------------------------------------------
# 测试数据
# ---------------------------------------------------------------------------

def _valid_brief(project: str = "web-test") -> str:
    return """# 立项简报

## 元数据

| 字段 | 值 |
|------|-----|
| 项目代号 | web-test |
| 简报版本 | v1 |
| 状态 | confirmed |

## 核心想法

一个帮助用户记录与回顾日常习惯的极简应用，强调一键打卡与可视化进度。

## 目标用户

| 用户群 | 描述 | 核心诉求 |
|--------|------|---------|
| 上班族 | 想养成小习惯的人 | 打卡要快、进度可见 |

## 功能清单

| # | 功能 | 优先级 | 验收要点 |
|---|------|--------|---------|
| 1 | 打卡 | P0 | 点击后立即变更状态 |
| 2 | 统计 | P1 | 展示连续天数 |

## 明确不做

- 账户与云同步
- 社交分享
- 推送提醒

## 技术约束

| 约束项 | 值 |
|--------|-----|
| 平台 | Flutter |
| 存储 | 纯本地 |

## 待澄清

| # | 问题 | 提出方 | 状态 |
|---|------|--------|------|
| - | 无 | - | - |

## 决策记录

| 日期 | 版本 | 决策 | 理由 | 提出方 |
|------|------|------|------|--------|
| 2026-11-12 | v1 | 纯本地存储 | 降低验证成本 | user |
"""
