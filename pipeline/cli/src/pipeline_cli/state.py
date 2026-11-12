"""StateStore：状态机的唯一读写入口。

设计要点（对应 P0 教训）：
1. **原子写**：先写 `.tmp` 再 `os.replace`，避免写一半崩溃导致状态损坏。
2. **单一写入者**：所有状态变更必须经过本类，禁止手改 JSON。
3. **追加式事件日志**：history 只追加不修改，Portal 靠它做时间线。
4. **stale 传播**：上游变更后自动把受影响下游标记 stale（P0 是手工做的）。
5. **一致性校验**：写入前检查 schema；读取时可选校验文件存在性。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from .errors import StateError
from .models import (
    Backfill,
    Deliverable,
    GateRecord,
    HistoryEvent,
    ProjectMeta,
    Stage,
    State,
    now_iso,
)
from .paths import Paths


class StateStore:
    """单项目状态文件的读写器。"""

    def __init__(self, paths: Paths, project: str) -> None:
        self.paths = paths
        self.project = project
        self.file = paths.state_file(project)
        self._state: State | None = None

    # ---------- 读写 ----------

    def load(self) -> State:
        if not self.file.exists():
            raise StateError(
                f"状态文件不存在: {self.file}",
                hint=f"用 `pipeline init {self.project}` 初始化项目",
            )
        try:
            raw = json.loads(self.file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StateError(f"状态文件 JSON 解析失败: {exc}") from exc
        try:
            state = State.model_validate(raw)
        except ValidationError as exc:
            raise StateError(f"状态文件结构非法: {exc.errors()[:3]}") from exc
        self._state = state
        return state

    @property
    def state(self) -> State:
        if self._state is None:
            self.load()
        assert self._state is not None
        return self._state

    def save(self, state: State | None = None) -> None:
        target_state = state or self._state
        if target_state is None:
            raise StateError("无可保存的状态")
        payload = target_state.model_dump(mode="json")
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

        self.file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            dir=self.file.parent, prefix=".state-", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.file)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        self._state = target_state

    # ---------- 事件 ----------

    def log(
        self,
        event_type: str,
        stage: str,
        detail: str = "",
        actor: str = "system",
        *,
        state: State | None = None,
    ) -> HistoryEvent:
        st = state or self.state
        event = HistoryEvent(
            type=event_type,
            stage=stage,
            actor=actor,
            detail=detail,
            deliverable_versions=st.versions(),
        )
        st.history.append(event)
        return event

    # ---------- 交付物 ----------

    def bump_version(self, deliverable_id: str, state: State | None = None) -> int:
        st = state or self.state
        d = st.deliverable(deliverable_id)
        if d is None:
            raise StateError(f"交付物不存在于状态机: {deliverable_id}")
        d.version += 1
        return d.version

    def set_deliverable_status(
        self,
        deliverable_id: str,
        status: str,
        *,
        state: State | None = None,
        stale_reason: str | None = None,
    ) -> Deliverable:
        st = state or self.state
        d = st.deliverable(deliverable_id)
        if d is None:
            raise StateError(f"交付物不存在于状态机: {deliverable_id}")
        d.status = status  # type: ignore[assignment]
        d.stale_reason = stale_reason if status == "stale" else None
        return d

    def propagate_stale(
        self,
        deliverable_ids: Iterable[str],
        reason: str,
        *,
        state: State | None = None,
    ) -> list[str]:
        """把下游交付物标记为 stale（上游变更后必须刷新）。

        返回实际被标记的交付物 id 列表。
        """
        st = state or self.state
        marked: list[str] = []
        for did in deliverable_ids:
            d = st.deliverable(did)
            if d is None:
                continue
            if d.status == "stale":
                continue
            d.status = "stale"
            d.stale_reason = reason
            marked.append(did)
        if marked:
            self.log(
                "deliverable_staled",
                st.current_stage,
                f"标记 stale: {', '.join(marked)}（原因：{reason}）",
                state=st,
            )
        return marked

    # ---------- 回填任务 ----------

    def register_backfill(
        self,
        *,
        item: str,
        owner: str,
        close_condition: str,
        source_stage: str,
        blocks_acceptance: bool = False,
        state: State | None = None,
    ) -> Backfill:
        st = state or self.state
        # 幂等：同 item + 同来源阶段且未关闭时复用
        for b in st.backfills:
            if b.item == item and b.source_stage == source_stage and b.status == "open":
                # 升级 blocks_acceptance（后者更严）
                if blocks_acceptance and not b.blocks_acceptance:
                    b.blocks_acceptance = True
                return b

        seq = len(st.backfills) + 1
        backfill = Backfill(
            id=f"BF-{seq:03d}",
            item=item,
            owner=owner,
            close_condition=close_condition,
            blocks_acceptance=blocks_acceptance,
            source_stage=source_stage,
        )
        st.backfills.append(backfill)
        self.log(
            "backfill_registered",
            source_stage,
            f"登记回填 {backfill.id}: {item}（阻塞验收={blocks_acceptance}）",
            state=st,
        )
        return backfill

    def close_backfill(self, backfill_id: str, *, state: State | None = None) -> Backfill:
        st = state or self.state
        for b in st.backfills:
            if b.id == backfill_id:
                if b.status == "closed":
                    return b
                b.status = "closed"
                b.closed_at = now_iso()
                self.log(
                    "backfill_closed", b.source_stage, f"关闭回填 {b.id}", state=st
                )
                return b
        raise StateError(f"回填任务不存在: {backfill_id}")

    # ---------- 关卡 ----------

    def record_gate(
        self,
        *,
        stage: str,
        action: str,
        comment: str = "",
        actor: str = "user",
        review_package: list[str] | None = None,
        state: State | None = None,
    ) -> GateRecord:
        st = state or self.state
        record = GateRecord(
            stage=stage,
            action=action,  # type: ignore[arg-type]
            actor=actor,
            comment=comment,
            review_package=review_package or [],
            deliverable_versions=st.versions(),
        )
        st.gate_log.append(record)
        return record

    def resolve_gate(self, stage_id: str, *, state: State | None = None) -> None:
        st = state or self.state
        s = st.stage(stage_id)
        if s is None:
            raise StateError(f"阶段不存在: {stage_id}")
        s.gate.resolved_at = now_iso()

    # ---------- 阶段进度（断点续跑） ----------

    def mark_step(
        self,
        stage_id: str,
        step_id: str,
        status: str,
        *,
        state: State | None = None,
    ) -> None:
        st = state or self.state
        st.progress(stage_id)[step_id] = status  # type: ignore[assignment]

    def reset_progress(self, stage_id: str, *, state: State | None = None) -> None:
        st = state or self.state
        st.stage_progress[stage_id] = {}

    # ---------- 一致性 ----------

    def check_consistency(self, *, check_files: bool = False) -> list[str]:
        """返回不一致项（空列表表示一致）。

        P0 教训：状态靠手改会漂移。这里提供主动检查能力。
        """
        st = self.state
        problems: list[str] = []

        seen: set[str] = set()
        for s in st.stages:
            if s.id in seen:
                problems.append(f"阶段 id 重复: {s.id}")
            seen.add(s.id)

        if st.stage(st.current_stage) is None and st.current_stage != "done":
            problems.append(f"current_stage 指向不存在的阶段: {st.current_stage}")

        for d in st.deliverables:
            if check_files and d.status == "approved":
                abs_path = self.paths.resolve(d.path)
                if not abs_path.exists():
                    problems.append(f"交付物 {d.id} 标记 approved 但文件不存在: {d.path}")

        for b in st.backfills:
            if b.status == "open" and b.blocks_acceptance:
                # 只提示，不算错误
                pass

        return problems


def new_state(
    *,
    project: str,
    flow: str = "new_project",
    target_project: str | None = None,
    app_repo_path: str = "",
    stages: list[Stage] | None = None,
    deliverables: list[Deliverable] | None = None,
) -> State:
    """构造一个全新的状态对象（供 init 使用）。"""
    return State(
        project=ProjectMeta(
            codename=project,
            flow=flow,  # type: ignore[arg-type]
            target_project=target_project,
            app_repo_path=app_repo_path or f"{project}/",
            created_at=datetime.now().replace(microsecond=0).isoformat(),
        ),
        current_stage="brief" if flow == "new_project" else "intake",
        stages=stages or [],
        deliverables=deliverables or [],
    )
