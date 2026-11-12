"""7 种 SOP 动作的实现（封闭集合）。

每个 handler 返回 `Outcome`，由引擎决定后续动作（继续 / 重试 / 降级 / 停止）。
handler 不允许直接改状态机之外的文件（那是引擎的职责）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from .agents import AgentInvoker, InvokeRequest
from .checks import (
    MarkdownDoc,
    evaluate_ruleset,
    load_manifest,
    load_ruleset,
    summarize,
    validate_manifest,
)
from .errors import InputNotReady, ManifestError, StepFailed
from .models import State
from .paths import Paths
from .sops import Sop, Step
from .state import StateStore


@dataclass
class Outcome:
    status: str  # done | skipped | degraded | needs_human | failed
    detail: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"done", "skipped"}


@dataclass
class ActionContext:
    step: Step
    sop: Sop
    paths: Paths
    store: StateStore
    state: State
    invoker: AgentInvoker
    answers: dict[str, str]
    emit: Callable[[str], None]
    dry_run: bool = False
    # 本阶段已降级的步骤 → 原因（由引擎注入，供 register_backfill 判断）
    degraded_steps: dict[str, str] = field(default_factory=dict)

    def stage_degraded(self) -> bool:
        return bool(self.degraded_steps)

    # ---- 路径与变量 ----

    @property
    def project(self) -> str:
        return self.state.project.codename

    @property
    def target_project(self) -> str:
        return self.state.project.target_project or self.project

    def render(self, text: str) -> str:
        out = text
        out = out.replace("{{project}}", self.project)
        out = out.replace("{{target_project}}", self.target_project)
        out = re.sub(r"\{\{\s*env\.(\w+)\s*\}\}", "", out)
        return out

    def resolve(self, text: str) -> Path:
        return self.paths.resolve(self.render(text))

    # ---- 状态查询 ----

    def deliverable_status(self, deliverable_id: str) -> str | None:
        d = self.state.deliverable(deliverable_id)
        return d.status if d else None


# ---------------------------------------------------------------------------
# 1. validate_inputs
# ---------------------------------------------------------------------------

def _validate_inputs(ctx: ActionContext) -> Outcome:
    requires = ctx.step.param("requires") or []
    problems: list[str] = []

    for item in requires:
        rel = ctx.render(str(item.get("path", "")))
        if not rel:
            continue
        abs_path = ctx.resolve(rel)
        if not abs_path.exists():
            problems.append(f"缺少输入文件: {rel}")
            continue
        did = item.get("deliverable")
        if did:
            d = ctx.state.deliverable(str(did))
            if d is None:
                problems.append(f"交付物未登记在状态机: {did}")
                continue
            min_status = str(item.get("min_status") or "approved")
            order = {"draft": 0, "in-review": 1, "approved": 2, "stale": -1}
            if order.get(d.status, -1) < order.get(min_status, 2):
                problems.append(
                    f"{did} 状态为 {d.status}，要求至少 {min_status}"
                )

    for did in ctx.step.param("forbidden_stale") or []:
        d = ctx.state.deliverable(str(did))
        if d is not None and d.status == "stale":
            problems.append(
                f"{did} 已过期（stale）：{d.stale_reason or '上游已变更'}，需先刷新"
            )

    if problems:
        raise InputNotReady("输入未就绪:\n  - " + "\n  - ".join(problems))
    ctx.emit(f"    ✓ 输入齐备（{len(requires)} 项）")
    return Outcome("done", f"{len(requires)} 项输入通过校验")


# ---------------------------------------------------------------------------
# 2. invoke_agent
# ---------------------------------------------------------------------------

def _invoke_agent(ctx: ActionContext) -> Outcome:
    params = ctx.step.params
    agent = str(params.get("agent", "planner"))
    output_rel = ctx.render(str(params.get("output_path", "")))
    manifest_rel = ctx.render(str(params.get("output_manifest") or "")) or None
    context = params.get("context") or {}
    must_read = [ctx.render(str(p)) for p in context.get("must_read") or []]

    # 必读文件存在性检查（提前失败，避免 Agent 白跑）
    missing = [p for p in must_read if not ctx.resolve(p).exists()]
    if missing:
        ctx.emit(f"    ! 必读文件缺失（仍继续）: {', '.join(missing[:3])}")

    request = InvokeRequest(
        agent=agent,
        task=str(context.get("task") or ctx.step.description),
        output_path=ctx.resolve(output_rel),
        output_manifest=manifest_rel,
        must_read=must_read,
        focus=[str(x) for x in context.get("focus") or []],
        constraints=[str(x) for x in context.get("constraints") or []],
        agent_definition=ctx.render(str(params.get("agent_definition") or "")) or None,
        timeout_sec=int(params.get("timeout_sec") or 600),
    )
    result = ctx.invoker.invoke(request, paths=ctx.paths)

    # 产出即登记版本（新产出 → in-review）
    # 注意：仅当本步骤产出的是 SOP 的**主交付物**时才升版本。
    # SOP 内可能有多个 invoke_agent（如 brief 的 draft-brief 与 check-clarity），
    # 它们共用 output_deliverable，若不判断会导致版本被重复 +1。
    did = ctx.sop.output_deliverable
    sop_output_path = ctx.sop.output_path
    is_primary_output = bool(
        did and sop_output_path and output_rel == ctx.render(str(sop_output_path))
    )
    if did and is_primary_output:
        d = ctx.state.deliverable(str(did))
        if d is not None:
            d.version = max(d.version, 1) if d.version == 0 else d.version + 1
            d.status = "in-review"
            d.stale_reason = None
            d.path = output_rel

    ctx.store.log(
        "deliverable_produced",
        ctx.sop.stage,
        f"{agent} 产出 {output_rel}（{len(result.content)} 字符）",
        actor=agent,
    )
    ctx.emit(f"    ✓ {agent} 产出 {Path(output_rel).name}")
    return Outcome("done", output_rel, {"bytes": len(result.content)})


# ---------------------------------------------------------------------------
# 3. validate_deliverable
# ---------------------------------------------------------------------------

def _validate_deliverable(ctx: ActionContext) -> Outcome:
    params = ctx.step.params
    did = str(params.get("deliverable") or ctx.sop.output_deliverable or "")
    manifest_rel = params.get("manifest")
    if not manifest_rel:
        manifest_rel = ctx.sop.output.get("manifest") or f"pipeline/manifests/{did}.manifest.yaml"
    manifest_rel = ctx.render(str(manifest_rel))
    fail_on = str(params.get("fail_on") or "any")

    # 找目标文件：优先 SOP 输出，其次状态机登记路径
    target_rel = ctx.sop.output_path
    if not target_rel:
        d = ctx.state.deliverable(did)
        target_rel = d.path if d else None
    if not target_rel:
        raise StepFailed(ctx.step.id, f"无法确定 {did} 的文件路径")
    target = ctx.resolve(str(target_rel))
    if not target.exists():
        raise StepFailed(ctx.step.id, f"交付物文件不存在: {target_rel}")

    manifest = load_manifest(ctx.paths, manifest_rel)
    result = validate_manifest(
        target.read_text(encoding="utf-8"), manifest, fail_on=fail_on
    )
    if not result.ok:
        raise StepFailed(
            ctx.step.id,
            "结构校验未通过\n" + "\n".join(f"      {v.render()}" for v in result.violations),
        )
    ctx.emit(f"    ✓ manifest 校验通过（{result.checked_sections} 章节）")
    return Outcome("done", f"{result.checked_sections} 章节")


# ---------------------------------------------------------------------------
# 4. check_rules
# ---------------------------------------------------------------------------

_M3_RULESETS = {"asset.rules", "dod.rules"}


def _check_rules(ctx: ActionContext) -> Outcome:
    params = ctx.step.params
    ruleset_rel = ctx.render(str(params.get("ruleset", "")))
    target = str(params.get("target", ""))
    rule_ids = params.get("rule_ids")

    if any(key in ruleset_rel for key in _M3_RULESETS):
        ctx.emit(
            f"    · {Path(ruleset_rel).name} 需要真实探测（M3 实现），本次跳过"
        )
        return Outcome(
            "skipped",
            f"{Path(ruleset_rel).name} 未实现（M3）",
            {"ruleset": ruleset_rel, "reason": "m3_pending"},
        )

    ruleset = load_ruleset(ctx.paths, ruleset_rel)

    # 解析被检查对象
    doc: MarkdownDoc
    rendered_target = ctx.render(target)
    if rendered_target in {"pipeline-state", "state"}:
        state_doc = json.dumps(ctx.state.model_dump(mode="json"), ensure_ascii=False)
        doc = MarkdownDoc(state_doc)
    elif rendered_target == "env":
        doc = MarkdownDoc("")
    else:
        p = ctx.paths.resolve(rendered_target)
        if not p.exists():
            # 目标缺失时，若规则是针对交付物的，视为失败
            raise StepFailed(ctx.step.id, f"规则检查目标不存在: {rendered_target}")
        doc = MarkdownDoc(p.read_text(encoding="utf-8"))

    results = evaluate_ruleset(
        ruleset=ruleset,
        doc=doc,
        rule_ids=[str(r) for r in rule_ids] if rule_ids else None,
        state=ctx.state,
        paths=ctx.paths,
    )
    ok, text = summarize(results)
    for line in text.splitlines():
        ctx.emit(f"      {line}")
    if not ok:
        raise StepFailed(ctx.step.id, "规则检查未通过")
    return Outcome("done", f"{len(results)} 条规则")


# ---------------------------------------------------------------------------
# 5. collect_human_input
# ---------------------------------------------------------------------------

def _collect_human_input(ctx: ActionContext) -> Outcome:
    params = ctx.step.params
    questions = params.get("questions") or []
    target_rel = ctx.render(str(params.get("write_answers_to", "")))
    section = str(params.get("answer_section") or "已澄清记录")
    allow_empty = bool(params.get("allow_empty", False))

    collected: dict[str, str] = {}
    missing: list[str] = []

    for q in questions:
        qid = str(q.get("id", ""))
        required = bool(q.get("required", True))
        if qid in ctx.answers:
            collected[qid] = ctx.answers[qid]
        elif required:
            missing.append(f"{qid}（{q.get('question', '')}）")

    if missing and not allow_empty:
        ctx.emit("    ⏸ 需要人工输入：")
        for m in missing:
            ctx.emit(f"      - {m}")
        return Outcome(
            "needs_human",
            "缺少必填输入",
            {"questions": [q for q in questions if str(q.get("id")) in {
                m.split("（")[0] for m in missing
            }]},
        )

    if collected and target_rel:
        target = ctx.resolve(target_rel)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {ctx.project}\n", encoding="utf-8")
        lines = [f"\n## {section}（自动采集）\n"]
        for qid, value in collected.items():
            lines.append(f"- **{qid}**：{value}")
        lines.append("")
        with target.open("a", encoding="utf-8") as fh:
            fh.write("\n".join(lines))
        ctx.emit(f"    ✓ 已记录 {len(collected)} 项回答到 {Path(target_rel).name}")

    return Outcome("done", f"{len(collected)} 项")


# ---------------------------------------------------------------------------
# 6. human_gate
# ---------------------------------------------------------------------------

def _human_gate(ctx: ActionContext) -> Outcome:
    params = ctx.step.params
    title = str(params.get("title") or ctx.sop.gate.title or "关卡")
    actions = [str(a) for a in params.get("actions") or ctx.sop.gate.actions]
    package = [ctx.render(str(p)) for p in ctx.sop.gate.review_package]

    stage = ctx.state.stage(ctx.sop.stage)
    if stage is not None:
        stage.status = "awaiting_review"
        stage.gate.actions = actions
        stage.gate.review_package_paths = package
        stage.review_rounds = max(stage.review_rounds, 1)
    ctx.state.current_stage = ctx.sop.stage
    ctx.store.log(
        "review_submitted",
        ctx.sop.stage,
        f"{title} 评审包就绪（{len(package)} 份文件）",
        actor=ctx.sop.owner_agent,
    )
    ctx.emit(f"    ⏸ {title} 已就绪，等待人工确认")
    return Outcome(
        "needs_human",
        title,
        {"title": title, "actions": actions, "review_package": package},
    )


# ---------------------------------------------------------------------------
# 7. register_backfill
# ---------------------------------------------------------------------------

def _register_backfill(ctx: ActionContext) -> Outcome:
    if not ctx.stage_degraded():
        ctx.emit("    · 本阶段无降级项，无需回填")
        return Outcome("skipped", "无降级")

    params = ctx.step.params
    bf = ctx.store.register_backfill(
        item=ctx.render(str(params.get("item", "未命名回填项"))),
        owner=str(params.get("owner", ctx.sop.owner_agent)),
        close_condition=ctx.render(str(params.get("close_condition", "未定义"))),
        source_stage=ctx.sop.stage,
        blocks_acceptance=bool(params.get("blocks_acceptance", False)),
        state=ctx.state,
    )
    ctx.emit(f"    ✓ 登记回填 {bf.id}: {bf.item[:32]}…")
    return Outcome("done", bf.id, {"backfill_id": bf.id})


# ---------------------------------------------------------------------------

HANDLERS: dict[str, Callable[[ActionContext], Outcome]] = {
    "validate_inputs": _validate_inputs,
    "invoke_agent": _invoke_agent,
    "validate_deliverable": _validate_deliverable,
    "check_rules": _check_rules,
    "collect_human_input": _collect_human_input,
    "human_gate": _human_gate,
    "register_backfill": _register_backfill,
}


def dispatch(step: Step, ctx: ActionContext) -> Outcome:
    handler = HANDLERS.get(step.action)
    if handler is None:
        raise StepFailed(step.id, f"未知动作类型: {step.action}")
    return handler(ctx)
