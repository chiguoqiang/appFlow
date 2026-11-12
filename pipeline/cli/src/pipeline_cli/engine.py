"""SOP 执行引擎。

职责：
1. 按 SOP 的 steps 顺序执行 7 种动作
2. 失败策略（abort / retry / degrade / continue）
3. 断点续跑（已完成步骤不重跑，除非 --force）
4. 每个 SOP **必然停在 gate**（不自动连跑下一阶段）

刻意不做的事：
- 不调用 LLM（那是 AgentInvoker 的事）
- 不硬编码流程（那是 SOP 的事）
- 不在 gate 处自动推进（那需要人）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .actions import ActionContext, Outcome, dispatch
from .agents import AgentInvoker, MockInvoker
from .errors import PipelineError, StepFailed
from .models import State
from .paths import Paths
from .sops import Sop, SopCatalog, Step
from .state import StateStore


@dataclass
class StepReport:
    step_id: str
    action: str
    status: str
    detail: str = ""
    attempts: int = 1


@dataclass
class RunReport:
    sop_id: str
    stage: str
    status: str  # completed | awaiting_review | failed | degraded
    steps: list[StepReport] = field(default_factory=list)
    degraded: dict[str, str] = field(default_factory=dict)
    needs_human: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"completed", "awaiting_review"}

    def render(self) -> str:
        lines = [f"SOP {self.sop_id}（阶段 {self.stage}）→ {self.status}"]
        for s in self.steps:
            icon = {
                "done": "✓",
                "skipped": "·",
                "degraded": "!",
                "needs_human": "⏸",
                "failed": "✗",
            }.get(s.status, "?")
            extra = f" [{s.status}]" if s.status not in {"done"} else ""
            lines.append(f"  {icon} {s.step_id} ({s.action}){extra} {s.detail}")
        if self.degraded:
            lines.append(f"  降级项: {', '.join(self.degraded)}")
        if self.error:
            lines.append(f"  错误: {self.error}")
        return "\n".join(lines)


class Engine:
    def __init__(
        self,
        *,
        paths: Paths,
        catalog: SopCatalog,
        invoker: AgentInvoker | None = None,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        self.paths = paths
        self.catalog = catalog
        self.invoker: AgentInvoker = invoker or MockInvoker()
        self._emit = emit or (lambda _msg: None)

    # ------------------------------------------------------------------

    def emit(self, msg: str) -> None:
        self._emit(msg)

    def run(
        self,
        *,
        project: str,
        stage: str | None = None,
        sop_id: str | None = None,
        answers: dict[str, str] | None = None,
        force: bool = False,
        dry_run: bool = False,
        max_attempts: int = 2,
    ) -> RunReport:
        store = StateStore(self.paths, project)
        state = store.load()

        sop = self._resolve_sop(state, stage=stage, sop_id=sop_id)
        self._assert_not_blocked(state, sop)

        report = RunReport(sop_id=sop.id, stage=sop.stage, status="completed")
        state.current_stage = sop.stage

        st = state.stage(sop.stage)
        if st is not None:
            st.status = "running"
            st.sop = sop.id
        store.log("stage_started", sop.stage, f"执行 SOP {sop.id}", actor=sop.owner_agent)

        ctx = ActionContext(
            step=sop.steps[0],
            sop=sop,
            paths=self.paths,
            store=store,
            state=state,
            invoker=self.invoker,
            answers=answers or {},
            emit=self.emit,
            dry_run=dry_run,
        )

        progress = state.progress(sop.stage)
        if force:
            store.reset_progress(sop.stage, state=state)
            progress = state.progress(sop.stage)

        self.emit(f"\n▶ SOP {sop.id} · {sop.name}（阶段 {sop.stage}）")

        for step in sop.steps:
            if progress.get(step.id) == "done" and not force:
                self.emit(f"  · {step.id} 已完成，跳过（断点续跑）")
                report.steps.append(StepReport(step.id, step.action, "skipped", "已完成"))
                continue

            if step.skip_if and self._eval_skip(step.skip_if, state):
                self.emit(f"  · {step.id} 条件跳过（{step.skip_if}）")
                store.mark_step(sop.stage, step.id, "skipped", state=state)
                report.steps.append(StepReport(step.id, step.action, "skipped", step.skip_if))
                continue

            ctx.step = step
            ctx.degraded_steps = report.degraded
            outcome, attempts = self._run_step(
                step, ctx, max_attempts=max_attempts, dry_run=dry_run
            )
            report.steps.append(
                StepReport(step.id, step.action, outcome.status, outcome.detail, attempts)
            )

            if outcome.status == "done":
                store.mark_step(sop.stage, step.id, "done", state=state)
                store.save(state)

            elif outcome.status == "skipped":
                store.mark_step(sop.stage, step.id, "skipped", state=state)
                store.save(state)

            elif outcome.status == "degraded":
                report.degraded[step.id] = outcome.detail
                store.mark_step(sop.stage, step.id, "skipped", state=state)
                store.log(
                    "step_degraded", sop.stage, f"{step.id}: {outcome.detail}"
                )
                store.save(state)

            elif outcome.status == "needs_human":
                report.status = "awaiting_review"
                report.needs_human = outcome.payload or {"title": outcome.detail}
                store.save(state)
                self.emit(f"\n⏸ 暂停：{outcome.detail}")
                return report

            elif outcome.status == "failed":
                report.status = "failed"
                report.error = outcome.detail
                store.log("step_failed", sop.stage, f"{step.id}: {outcome.detail}")
                store.save(state)
                return report

        # 所有步骤完成但未遇 gate（异常情形：SOP 缺 gate）
        if not sop.gate.enabled:
            report.status = "completed"
            store.log("stage_completed", sop.stage, f"SOP {sop.id} 完成（无 gate）")
            store.save(state)
        else:
            # gate 步骤应已把状态置为 awaiting_review 并返回
            report.status = "awaiting_review"
            store.save(state)

        return report

    # ------------------------------------------------------------------

    def _run_step(
        self,
        step: Step,
        ctx: ActionContext,
        *,
        max_attempts: int,
        dry_run: bool,
    ) -> tuple[Outcome, int]:
        attempts = 0
        last_error: Exception | None = None

        while attempts < max_attempts:
            attempts += 1
            try:
                return dispatch(step, ctx), attempts
            except StepFailed as exc:
                last_error = exc
                if step.on_fail == "degrade" and step.backfill:
                    self.emit(f"  ! {step.id} 降级：{exc.message}")
                    return Outcome("degraded", exc.message), attempts
                if step.on_fail == "continue":
                    self.emit(f"  ! {step.id} 失败但继续：{exc.message}")
                    return Outcome("skipped", exc.message), attempts
                if step.on_fail == "retry" and attempts < max_attempts:
                    self.emit(f"  ! {step.id} 第 {attempts} 次失败，重试：{exc.message}")
                    continue
                self.emit(f"  ✗ {step.id} 失败：{exc.message}")
                if exc.hint:
                    self.emit(f"      提示：{exc.hint}")
                return Outcome("failed", exc.message), attempts
            except PipelineError as exc:
                last_error = exc
                self.emit(f"  ✗ {step.id} 失败：{exc.message}")
                if exc.hint:
                    self.emit(f"      提示：{exc.hint}")
                return Outcome("failed", exc.message), attempts

        detail = last_error.message if last_error else "未知错误"
        return Outcome("failed", detail), attempts

    # ------------------------------------------------------------------

    def _resolve_sop(
        self,
        state: State,
        *,
        stage: str | None,
        sop_id: str | None,
    ) -> Sop:
        if sop_id:
            return self.catalog.get(sop_id)
        target_stage = stage or state.current_stage
        if target_stage == "done":
            raise PipelineError("项目已完成，无后续阶段")
        return self.catalog.by_stage(target_stage)

    def _assert_not_blocked(self, state: State, sop: Sop) -> None:
        """依赖未批准时拒绝执行（SOP 的 depends_on 是硬约束）。"""
        for dep_id in sop.depends_on:
            dep = self.catalog.get(dep_id)
            d = state.deliverable(dep.output_deliverable or "")
            if d is None:
                continue
            if d.status == "stale":
                raise PipelineError(
                    f"上游 {dep_id} 已过期（{d.stale_reason or '内容已变更'}）",
                    hint="先重跑上游阶段并重新批准",
                )
            if d.status != "approved":
                raise PipelineError(
                    f"上游 {dep_id} 尚未批准（当前 {d.status}）",
                    hint=f"先执行 `pipeline gate --stage={dep.stage} --action=approve`",
                )

    @staticmethod
    def _eval_skip(expr: str, state: State) -> bool:
        """极简条件求值：支持 `needs_new_pages == false` 这类比较。"""
        if "==" not in expr:
            return False
        left, _, right = expr.partition("==")
        key = left.strip()
        val = right.strip().strip("\"'").lower()
        actual: Any = None
        if key in {"needs_new_pages"}:
            # 由 intake-routing 产物决定；未知时默认 True（保守：走设计）
            actual = getattr(state.project, "needs_new_pages", True)
        if actual is None:
            return False
        if isinstance(actual, bool):
            return str(actual).lower() == val
        return str(actual) == val
