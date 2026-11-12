"""关卡（gate）三态动作与状态传播。

三态语义（M1 已定义，这里落地为代码）：

- approve  通过 → 交付物 approved，解锁下一阶段
- revise   调整 → 交付物 in-review，版本 +1，**重跑本 SOP**（只改被质疑部分）
- reject   打回 → 交付物 stale，按 SOP 的 propagate_stale 标记下游，重开上游 SOP

`revise` 与 `reject` 的关键差别：
- revise 保留本阶段上下文，增量修改
- reject 认为上游有问题，需要重开更早的阶段，且下游全部失效
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import GateError
from .models import State
from .paths import Paths
from .sops import Sop, SopCatalog, Transition
from .state import StateStore

VALID_ACTIONS = {"approve", "revise", "reject"}


@dataclass
class GateOutcome:
    stage: str
    action: str
    deliverable_status: str
    next_stage: str | None = None
    next_sop: str | None = None
    reopened_sop: str | None = None
    staled: list[str] = field(default_factory=list)
    version: int | None = None
    notes: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"阶段 {self.stage} → {self.action}"]
        lines.append(f"  交付物状态: {self.deliverable_status}")
        if self.version is not None:
            lines.append(f"  版本: v{self.version}")
        if self.staled:
            lines.append(f"  标记过期: {', '.join(self.staled)}")
        if self.reopened_sop:
            lines.append(f"  重开: {self.reopened_sop}")
        if self.next_sop:
            lines.append(f"  下一阶段: {self.next_stage}（SOP {self.next_sop}）")
        return "\n".join(lines)


class GateManager:
    def __init__(self, *, paths: Paths, catalog: SopCatalog) -> None:
        self.paths = paths
        self.catalog = catalog

    def act(
        self,
        *,
        project: str,
        stage: str,
        action: str,
        comment: str = "",
        actor: str = "user",
    ) -> GateOutcome:
        if action not in VALID_ACTIONS:
            raise GateError(
                f"非法动作: {action}",
                hint=f"允许: {', '.join(sorted(VALID_ACTIONS))}",
            )

        store = StateStore(self.paths, project)
        state = store.load()
        sop = self.catalog.by_stage(stage)
        st = state.stage(stage)
        if st is None:
            raise GateError(f"阶段不存在于状态机: {stage}")

        # 关卡前置条件
        if action == "approve" and st.status not in {"awaiting_review", "running", "revising"}:
            raise GateError(
                f"阶段 {stage} 当前状态为 {st.status}，不可 approve",
                hint="先执行 `pipeline run --stage=...` 让阶段跑到关卡",
            )
        if action in {"revise", "reject"} and st.status != "awaiting_review":
            raise GateError(
                f"阶段 {stage} 未处于 awaiting_review（当前 {st.status}）",
                hint="只有待评审的阶段才能调整/打回",
            )

        # 意见要求（SOP 声明哪些动作必须带意见）
        require_comment = set(sop.gate.require_comment_on or [])
        if action in require_comment and not comment.strip():
            raise GateError(
                f"动作 {action} 必须附意见（SOP 要求）",
                hint='例如：--comment "目标用户需要改为上班族"',
            )
        # 质量门失败但人工放行 → 强制留痕
        if action == "approve" and comment:
            pass  # 有意见即可

        transition = {
            "approve": sop.on_approve,
            "revise": sop.on_revise,
            "reject": sop.on_reject,
        }[action]

        did = sop.output_deliverable
        outcome = GateOutcome(
            stage=stage,
            action=action,
            deliverable_status=transition.deliverable_status or "draft",
        )

        # ---- 记录关卡操作 ----
        store.record_gate(
            stage=stage,
            action=action,
            comment=comment,
            actor=actor,
            review_package=st.gate.review_package_paths,
            state=state,
        )
        store.resolve_gate(stage, state=state)
        st.review_rounds = max(st.review_rounds, 1)

        # ---- 交付物状态 ----
        if did:
            d = state.deliverable(did)
            if d is not None:
                if transition.increment_version:
                    d.version += 1
                d.status = transition.deliverable_status or d.status  # type: ignore[assignment]
                if d.status != "stale":
                    d.stale_reason = None
                outcome.version = d.version

        if action == "approve":
            st.status = "approved"
            detail = f"关卡通过：{comment}" if comment else "关卡通过"
            store.log("approved", stage, detail, state=state)
            self._advance(state, sop, outcome)
            store.save(state)
            return outcome

        if action == "revise":
            st.status = "revising"
            state.current_stage = stage
            # 重跑本阶段：清进度，但保留交付物内容（增量修改）
            store.reset_progress(stage, state=state)
            store.log("revised", stage, f"调整：{comment}", state=state)
            outcome.next_stage = stage
            outcome.next_sop = sop.id
            outcome.notes.append("重跑本 SOP，只改被质疑部分")
            store.save(state)
            return outcome

        # reject
        st.status = "rejected"
        outcome.deliverable_status = "stale"
        if transition.propagate_stale:
            reason = f"上游 {stage} 被打回：{comment or '内容需重做'}"
            outcome.staled = store.propagate_stale(
                transition.propagate_stale, reason, state=state
            )
        reopened = transition.reopen_sop
        outcome.reopened_sop = reopened
        if reopened:
            reopened_sop = self.catalog.get(reopened)
            state.current_stage = reopened_sop.stage
            rst = state.stage(reopened_sop.stage)
            if rst is not None:
                rst.status = "ready"
            store.reset_progress(reopened_sop.stage, state=state)
            outcome.next_stage = reopened_sop.stage
            outcome.next_sop = reopened_sop.id
        store.log(
            "rejected",
            stage,
            f"打回：{comment or '无意见'}；下游标记 {len(outcome.staled)} 项",
            state=state,
        )
        store.save(state)
        return outcome

    # ------------------------------------------------------------------

    def _advance(self, state: State, sop: Sop, outcome: GateOutcome) -> None:
        nxt = sop.on_approve.next_sop
        if nxt is None:
            state.current_stage = "done"
            st = state.stage(sop.stage)
            if st is not None:
                st.status = "approved"
            # 关闭所有阶段状态
            for s in state.stages:
                if s.status != "approved":
                    s.status = "locked"
            self._close_history(state, sop)
            outcome.next_sop = None
            outcome.next_stage = "done"
            return

        answers = self._routing_answers(state, sop)
        next_sop_id = self.catalog.next_after(sop, answers=answers)
        if next_sop_id is None:
            state.current_stage = "done"
            outcome.next_stage = "done"
            return

        next_sop = self.catalog.get(next_sop_id)
        outcome.next_sop = next_sop_id
        outcome.next_stage = next_sop.stage
        state.current_stage = next_sop.stage
        nst = state.stage(next_sop.stage)
        if nst is not None:
            nst.status = "ready"

    def _close_history(self, state: State, sop: Sop) -> None:
        store = StateStore(self.paths, state.project.codename)
        store.log(
            "stage_completed",
            sop.stage,
            f"流程完成：{sop.id} 为终点",
            state=state,
        )

    def _routing_answers(self, state: State, sop: Sop) -> dict[str, object]:
        """为 __ROUTE__ / __IF_...__ 指令准备答案。"""
        answers: dict[str, object] = {"flow": state.project.flow}
        # 从 intake-routing 产物里读 needs_new_pages
        routing_path = self.paths.project_dir(state.project.codename) / "intake-routing.md"
        if routing_path.exists():
            text = routing_path.read_text(encoding="utf-8")
            if "needs_new_pages: false" in text or "needs_new_pages: **false**" in text:
                answers["needs_new_pages"] = False
            elif "needs_new_pages" in text:
                answers["needs_new_pages"] = True
        return answers
