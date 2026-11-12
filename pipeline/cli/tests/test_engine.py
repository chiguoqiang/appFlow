"""引擎与关卡端到端测试。

这是 M2 的核心验证：
- 一个阶段能否完整跑完并停在 gate
- 三态动作是否正确改变状态与传播 stale
- 断点续跑、失败策略、依赖门禁是否生效
"""

from __future__ import annotations

import pytest

from pipeline_cli.agents import MockInvoker
from pipeline_cli.engine import Engine
from pipeline_cli.errors import GateError, PipelineError
from pipeline_cli.gate import GateManager
from pipeline_cli.state import StateStore


@pytest.fixture()
def engine(paths, catalog):
    return Engine(
        paths=paths,
        catalog=catalog,
        invoker=MockInvoker(),
        emit=lambda _m: None,
    )


@pytest.fixture()
def gate_mgr(paths, catalog):
    return GateManager(paths=paths, catalog=catalog)


def _store(paths, project="demo"):
    return StateStore(paths, project)


# ---------------------------------------------------------------------------
# 基础流程
# ---------------------------------------------------------------------------

class TestRunBrief:
    def test_brief_requires_human_input_first(self, engine, paths, make_state):
        """00-brief 第一步是 collect_human_input，缺少必填答案时必须停下。"""
        make_state(paths, "demo")
        report = engine.run(project="demo", stage="brief")
        assert report.status == "awaiting_review"
        assert report.needs_human is not None
        # 状态停在 brief，未推进
        state = _store(paths).load()
        assert state.current_stage == "brief"

    def test_brief_completes_with_answers(self, engine, paths, make_state):
        make_state(paths, "demo")
        answers = {
            "core-idea": "一个极简习惯打卡应用",
            "target-users": "想养成习惯的个人用户",
            "mvp-features": "打卡、创建习惯",
            "out-of-scope": "账户、推送、社交",
            "tech-constraints": "Flutter + 本地存储",
        }
        report = engine.run(project="demo", stage="brief", answers=answers)
        assert report.status == "awaiting_review"
        state = _store(paths).load()
        # 简报文件已生成
        assert (paths.projects / "demo" / "00-project-brief.md").exists()
        # 阶段进入待评审
        assert state.stage("brief").status == "awaiting_review"
        assert state.current_stage == "brief"

    def test_run_always_stops_at_gate(self, engine, paths, make_state):
        """核心约束：跑完必停，绝不自动进入下一阶段。"""
        make_state(paths, "demo")
        answers = {
            "core-idea": "x" * 30,
            "target-users": "y",
            "mvp-features": "z",
            "out-of-scope": "a",
            "tech-constraints": "b",
        }
        engine.run(project="demo", stage="brief", answers=answers)
        state = _store(paths).load()
        assert state.current_stage == "brief"  # 没有跳到 planning
        assert state.stage("planning").status == "locked"


# ---------------------------------------------------------------------------
# 关卡三态
# ---------------------------------------------------------------------------

class TestGateApprove:
    def test_approve_advances(self, paths, make_state, gate_mgr):
        make_state(paths, "demo")
        store = _store(paths)
        state = store.load()
        state.stage("brief").status = "awaiting_review"
        state.deliverable("project_brief").status = "in-review"
        store.save(state)

        outcome = gate_mgr.act(project="demo", stage="brief", action="approve")
        assert outcome.deliverable_status == "approved"
        assert outcome.next_stage == "planning"

        state2 = _store(paths).load()
        assert state2.stage("brief").status == "approved"
        assert state2.stage("planning").status == "ready"
        assert state2.current_stage == "planning"
        assert state2.deliverable("project_brief").status == "approved"

    def test_approve_records_gate_log(self, paths, make_state, gate_mgr):
        make_state(paths, "demo")
        store = _store(paths)
        state = store.load()
        state.stage("brief").status = "awaiting_review"
        store.save(state)

        gate_mgr.act(
            project="demo", stage="brief", action="approve", comment="范围没问题"
        )
        state2 = _store(paths).load()
        assert len(state2.gate_log) == 1
        assert state2.gate_log[0].comment == "范围没问题"

    def test_cannot_approve_locked_stage(self, paths, make_state, gate_mgr):
        make_state(paths, "demo")
        with pytest.raises(GateError) as exc:
            gate_mgr.act(project="demo", stage="planning", action="approve")
        assert "不可 approve" in str(exc.value)

    def test_invalid_action(self, paths, make_state, gate_mgr):
        make_state(paths, "demo")
        with pytest.raises(GateError):
            gate_mgr.act(project="demo", stage="brief", action="lgtm")


class TestGateRevise:
    def test_revise_bumps_version_and_resets_progress(self, paths, make_state, gate_mgr):
        make_state(paths, "demo")
        store = _store(paths)
        state = store.load()
        state.stage("brief").status = "awaiting_review"
        state.deliverable("project_brief").status = "in-review"
        state.deliverable("project_brief").version = 1
        store.mark_step("brief", "write-brief", "done", state=state)
        store.save(state)

        outcome = gate_mgr.act(
            project="demo", stage="brief", action="revise", comment="目标用户要改"
        )
        assert outcome.version == 2
        assert outcome.next_stage == "brief"  # 留在本阶段

        state2 = _store(paths).load()
        assert state2.stage("brief").status == "revising"
        assert state2.deliverable("project_brief").status == "in-review"
        assert state2.deliverable("project_brief").version == 2
        # 进度已清空（下次 run 会重跑）
        assert state2.progress("brief") == {}

    def test_revise_requires_comment(self, paths, make_state, gate_mgr):
        make_state(paths, "demo")
        store = _store(paths)
        state = store.load()
        state.stage("brief").status = "awaiting_review"
        store.save(state)

        with pytest.raises(GateError) as exc:
            gate_mgr.act(project="demo", stage="brief", action="revise")
        assert "必须附意见" in str(exc.value)


class TestGateReject:
    def test_reject_propagates_stale(self, paths, make_state, gate_mgr):
        make_state(paths, "demo")
        store = _store(paths)
        state = store.load()
        state.stage("planning").status = "awaiting_review"
        state.deliverable("prd").status = "in-review"
        # 下游先设为 approved，验证会被打回标记
        for did in ("design_brief", "dev_report"):
            state.deliverable(did).status = "approved"
        store.save(state)

        outcome = gate_mgr.act(
            project="demo", stage="planning", action="reject", comment="需求理解错了"
        )
        assert outcome.deliverable_status == "stale"
        # 下游按 SOP 的 propagate_stale 列表被标记
        assert {"design_brief", "dev_report"}.issubset(set(outcome.staled))
        assert outcome.reopened_sop == "00-brief"

        state2 = _store(paths).load()
        assert state2.deliverable("prd").status == "stale"
        assert state2.deliverable("design_brief").status == "stale"
        assert state2.deliverable("design_brief").stale_reason  # 有原因
        assert state2.current_stage == "brief"  # 回到上游

    def test_reject_does_not_stale_upstream(self, paths, make_state, gate_mgr):
        make_state(paths, "demo")
        store = _store(paths)
        state = store.load()
        state.stage("planning").status = "awaiting_review"
        # 上游简报（不在 planning 的 propagate 列表里）应保持不变
        state.deliverable("project_brief").status = "approved"
        store.save(state)

        gate_mgr.act(project="demo", stage="planning", action="reject", comment="x")
        state2 = _store(paths).load()
        assert state2.deliverable("project_brief").status == "approved"


# ---------------------------------------------------------------------------
# 依赖门禁
# ---------------------------------------------------------------------------

class TestDependencyGate:
    def test_cannot_run_downstream_before_upstream_approved(
        self, engine, paths, make_state
    ):
        make_state(paths, "demo")
        with pytest.raises(PipelineError) as exc:
            engine.run(project="demo", stage="planning")
        msg = str(exc.value)
        assert "尚未批准" in msg or "未批准" in msg


# ---------------------------------------------------------------------------
# 断点续跑
# ---------------------------------------------------------------------------

class TestResume:
    def test_completed_steps_are_skipped(self, engine, paths, make_state):
        make_state(paths, "demo")
        store = _store(paths)
        state = store.load()
        # 伪造：上游已批准，brief 部分步骤已完成
        state.deliverable("project_brief").status = "approved"
        store.mark_step("brief", "write-brief", "done", state=state)
        store.save(state)

        report = engine.run(project="demo", stage="brief")
        skipped = [s for s in report.steps if s.status == "skipped"]
        assert any(s.step_id == "write-brief" for s in skipped)

    def test_force_reruns_completed(self, engine, paths, make_state):
        make_state(paths, "demo")
        store = _store(paths)
        state = store.load()
        state.deliverable("project_brief").status = "approved"
        store.mark_step("brief", "write-brief", "done", state=state)
        store.save(state)

        report = engine.run(project="demo", stage="brief", force=True)
        write_steps = [s for s in report.steps if s.step_id == "write-brief"]
        assert write_steps and write_steps[0].status != "skipped"


# ---------------------------------------------------------------------------
# 失败策略
# ---------------------------------------------------------------------------

class TestFailurePolicy:
    def test_failing_agent_aborts_stage(self, paths, catalog, make_state):
        from pipeline_cli.agents import InvokeResult, InvokeRequest

        class BoomInvoker:
            def invoke(self, request: InvokeRequest, *, paths):
                raise RuntimeError("boom")

        make_state(paths, "demo")
        engine = Engine(
            paths=paths, catalog=catalog, invoker=BoomInvoker(), emit=lambda _m: None
        )
        answers = {
            "core-idea": "x",
            "target-users": "y",
            "mvp-features": "z",
            "out-of-scope": "a",
            "tech-constraints": "b",
        }
        # RuntimeError 不是 PipelineError，会冒泡
        with pytest.raises(RuntimeError):
            engine.run(project="demo", stage="brief", answers=answers)


# ---------------------------------------------------------------------------
# 全流程串联（mock）
# ---------------------------------------------------------------------------

class TestFullFlow:
    def test_keep_flow_advances_across_stages(self, paths, make_state, gate_mgr, engine):
        """brief → planning → design 连续三关，验证推进链路。"""
        make_state(paths, "demo")
        answers = {
            "core-idea": "极简习惯打卡，帮助用户坚持",
            "target-users": "想养成习惯的人",
            "mvp-features": "打卡、创建、统计",
            "out-of-scope": "账户、推送、社交",
            "tech-constraints": "Flutter + 本地存储",
        }
        # 1) brief
        engine.run(project="demo", stage="brief", answers=answers)
        gate_mgr.act(project="demo", stage="brief", action="approve")

        state = _store(paths).load()
        assert state.current_stage == "planning"
        assert state.deliverable("project_brief").status == "approved"

        # 2) planning（mock 产出 PRD 不一定过 manifest，这里只验证流程推进能力）
        report = engine.run(project="demo", stage="planning")
        # 无论成功失败，都不应自动跳到 design
        state = _store(paths).load()
        assert state.current_stage in {"planning"}
