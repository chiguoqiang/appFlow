"""StateStore 测试：原子写、版本、stale 传播、回填登记、一致性。"""

from __future__ import annotations

import json

import pytest

from pipeline_cli.errors import StateError
from pipeline_cli.state import StateStore


class TestLoadSave:
    def test_roundtrip(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        assert state.project.codename == "p1"
        store.save()
        again = StateStore(paths, "p1").load()
        assert again.project.codename == "p1"
        assert len(again.stages) == len(state.stages)

    def test_no_temp_files_left(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        store.load()
        store.save()
        leftovers = list((paths.projects / "p1").glob(".state-*.tmp"))
        assert leftovers == []

    def test_missing_state_raises(self, paths):
        with pytest.raises(StateError) as exc:
            StateStore(paths, "ghost").load()
        assert "状态文件不存在" in str(exc.value)

    def test_invalid_json_raises(self, paths):
        pdir = paths.projects / "broken"
        pdir.mkdir(parents=True)
        (pdir / "pipeline-state.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(StateError) as exc:
            StateStore(paths, "broken").load()
        assert "JSON 解析失败" in str(exc.value)

    def test_invalid_structure_raises(self, paths):
        pdir = paths.projects / "bad"
        pdir.mkdir(parents=True)
        (pdir / "pipeline-state.json").write_text('{"foo": 1}', encoding="utf-8")
        with pytest.raises(StateError) as exc:
            StateStore(paths, "bad").load()
        assert "结构非法" in str(exc.value)


class TestVersions:
    def test_bump_version(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        store.load()
        assert store.bump_version("prd") == 1
        assert store.bump_version("prd") == 2

    def test_bump_unknown_deliverable(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        store.load()
        with pytest.raises(StateError):
            store.bump_version("nope")

    def test_set_status_clears_stale_reason(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        store.load()
        d = store.set_deliverable_status("prd", "stale", stale_reason="上游变更")
        assert d.status == "stale"
        assert d.stale_reason == "上游变更"
        d2 = store.set_deliverable_status("prd", "approved")
        assert d2.stale_reason is None


class TestStalePropagation:
    def test_propagates_to_downstream(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        marked = store.propagate_stale(
            ["design_brief", "dev_report"], "PRD 打回", state=state
        )
        assert set(marked) == {"design_brief", "dev_report"}
        assert state.deliverable("design_brief").status == "stale"
        assert state.deliverable("design_brief").stale_reason == "PRD 打回"
        # 已 stale 的不重复标记
        again = store.propagate_stale(["design_brief"], "再打回", state=state)
        assert again == []

    def test_unknown_deliverable_ignored(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        assert store.propagate_stale(["ghost"], "x", state=state) == []

    def test_logs_event(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        before = len(state.history)
        store.propagate_stale(["prd"], "测试", state=state)
        assert len(state.history) == before + 1
        assert state.history[-1].type == "deliverable_staled"


class TestBackfill:
    def test_register_and_idempotent(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        b1 = store.register_backfill(
            item="截图缺失",
            owner="tester",
            close_condition="截图齐备",
            source_stage="testing",
            state=state,
        )
        assert b1.id == "BF-001"
        # 同 item + 同阶段 → 复用
        b2 = store.register_backfill(
            item="截图缺失",
            owner="tester",
            close_condition="截图齐备",
            source_stage="testing",
            state=state,
        )
        assert b2.id == b1.id
        assert len(state.backfills) == 1

    def test_blocks_acceptance_upgrade(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        store.register_backfill(
            item="基线缺失",
            owner="designer",
            close_condition="导出",
            source_stage="design",
            blocks_acceptance=False,
            state=state,
        )
        b = store.register_backfill(
            item="基线缺失",
            owner="designer",
            close_condition="导出",
            source_stage="design",
            blocks_acceptance=True,
            state=state,
        )
        assert b.blocks_acceptance is True

    def test_close_backfill(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        b = store.register_backfill(
            item="x", owner="o", close_condition="c", source_stage="s", state=state
        )
        assert len(state.open_backfills()) == 1
        closed = store.close_backfill(b.id, state=state)
        assert closed.status == "closed"
        assert closed.closed_at is not None
        assert state.open_backfills() == []

    def test_close_unknown_raises(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        with pytest.raises(StateError):
            store.close_backfill("BF-999", state=state)

    def test_blocking_backfills_filter(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        store.register_backfill(
            item="a", owner="o", close_condition="c", source_stage="s",
            blocks_acceptance=False, state=state,
        )
        store.register_backfill(
            item="b", owner="o", close_condition="c", source_stage="s",
            blocks_acceptance=True, state=state,
        )
        assert len(state.open_backfills()) == 2
        assert len(state.blocking_backfills()) == 1
        assert state.blocking_backfills()[0].item == "b"


class TestGateAndProgress:
    def test_record_gate(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        rec = store.record_gate(
            stage="planning", action="approve", comment="OK", state=state
        )
        assert rec.action == "approve"
        assert rec.deliverable_versions  # 快照非空
        assert len(state.gate_log) == 1

    def test_resolve_gate_sets_timestamp(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        store.resolve_gate("brief", state=state)
        assert state.stage("brief").gate.resolved_at is not None

    def test_mark_and_reset_progress(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        store.mark_step("planning", "check-inputs", "done", state=state)
        assert state.progress("planning") == {"check-inputs": "done"}
        store.reset_progress("planning", state=state)
        assert state.progress("planning") == {}


class TestConsistency:
    def test_detects_current_stage_missing(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        state.current_stage = "ghost_stage"
        problems = store.check_consistency()
        assert any("ghost_stage" in p for p in problems)

    def test_detects_approved_but_missing_file(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        state = store.load()
        d = state.deliverable("prd")
        d.status = "approved"  # 文件不存在
        problems = store.check_consistency(check_files=True)
        assert any("prd" in p for p in problems)

    def test_clean_state_has_no_problems(self, paths, make_state):
        make_state(paths, "p1")
        store = StateStore(paths, "p1")
        store.load()
        assert store.check_consistency() == []
