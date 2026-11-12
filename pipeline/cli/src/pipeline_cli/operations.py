"""业务操作层（CLI 与 Web 共用）。

设计动机：CLI 与 Web 是同一套流程的两个前端。若各自实现一遍
「提交交付物 / 关卡三态 / 新建项目」，迟早行为漂移。

因此把用例抽到这里，两个前端都调用它，返回可直接 JSON 序列化的 dict。

安全约定：
- 所有路径必须是 `pipeline/projects/<project>/` 下的相对路径
- Web 层不得写入 templates / sops / manifests / gates（契约层只读）
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .errors import GateError, PipelineError, ProjectNotFound, StateError
from .gate import GateManager
from .models import State
from .paths import Paths
from .sops import load_sops
from .state import StateStore

# ---------------------------------------------------------------------------
# 安全：可写路径白名单
# ---------------------------------------------------------------------------

_WRITE_SAFE_PREFIX = "pipeline/projects/"


def _assert_writable(paths: Paths, project: str, rel_path: str) -> Path:
    """只允许写项目目录内的文件（防路径穿越与误改契约层）。"""
    rel_path = rel_path.replace("{{project}}", project)
    if not rel_path.startswith(_WRITE_SAFE_PREFIX):
        raise PipelineError(
            f"禁止写入契约层文件: {rel_path}",
            hint=f"只允许写 {_WRITE_SAFE_PREFIX}<project>/ 下的文件",
        )
    abs_path = (paths.root / rel_path).resolve()
    allowed_root = (paths.projects / project).resolve()
    if not str(abs_path).startswith(str(allowed_root)):
        raise PipelineError(f"路径越界: {rel_path}")
    return abs_path


# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------

# 交付物 id → templates/ 下的模板文件名（不含扩展名）
TEMPLATE_MAP: dict[str, str] = {
    "project_brief": "00-project-brief",
    "prd": "01-prd",
    "design_brief": "02-design-brief",
    "design_delivery": "03-design-delivery",
    "dev_report": "04-dev-report",
    "test_report": "05-test-report",
    "acceptance_report": "06-acceptance-report",
}


def get_template(paths: Paths, deliverable_id: str) -> dict[str, Any]:
    """返回某交付物对应的模板骨架（用于空白交付物一键起步）。"""
    stem = TEMPLATE_MAP.get(deliverable_id)
    if not stem:
        return {"available": False, "content": "", "reason": "该交付物无对应模板"}

    path = paths.templates / f"{stem}.template.md"
    if not path.exists():
        return {"available": False, "content": "", "reason": f"模板不存在: {stem}"}

    return {
        "available": True,
        "content": path.read_text(encoding="utf-8"),
        "template": path.name,
    }


# ---------------------------------------------------------------------------
# 项目列表 / 详情
# ---------------------------------------------------------------------------

_STAGE_ICONS = {
    "locked": "·",
    "ready": "→",
    "running": "▶",
    "awaiting_review": "⏸",
    "revising": "✎",
    "approved": "✓",
    "rejected": "✗",
}

_STAGE_LABELS = {
    "locked": "未开始",
    "ready": "就绪",
    "running": "执行中",
    "awaiting_review": "待评审",
    "revising": "调整中",
    "approved": "已通过",
    "rejected": "已打回",
}


def _project_progress(state: State) -> dict[str, Any]:
    total = len(state.stages) or 1
    approved = sum(1 for s in state.stages if s.status == "approved")
    return {
        "approved": approved,
        "total": total,
        "percent": round(approved / total * 100),
    }


def list_projects(paths: Paths) -> list[dict[str, Any]]:
    """扫描 projects 目录，返回项目摘要列表。"""
    if not paths.projects.exists():
        return []

    out: list[dict[str, Any]] = []
    for pdir in sorted(paths.projects.iterdir()):
        if not pdir.is_dir():
            continue
        if not (pdir / "pipeline-state.json").exists():
            continue
        try:
            state = StateStore(paths, pdir.name).load()
        except PipelineError as exc:
            out.append(
                {
                    "codename": pdir.name,
                    "error": exc.message,
                    "current_stage": "?",
                    "stages": [],
                    "progress": {"approved": 0, "total": 0, "percent": 0},
                }
            )
            continue

        cur = state.stage(state.current_stage)
        out.append(
            {
                "codename": state.project.codename,
                "flow": state.project.flow,
                "current_stage": state.current_stage,
                "current_stage_name": cur.name if cur else "已完成",
                "current_status": cur.status if cur else "done",
                "awaiting_review": bool(cur and cur.status == "awaiting_review"),
                "progress": _project_progress(state),
                "stages": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "status": s.status,
                        "icon": _STAGE_ICONS.get(s.status, "?"),
                        "label": _STAGE_LABELS.get(s.status, s.status),
                        "rounds": s.review_rounds,
                    }
                    for s in state.stages
                ],
                "open_backfills": len(state.open_backfills()),
                "blocking_backfills": len(state.blocking_backfills()),
            }
        )
    return out


def project_detail(paths: Paths, project: str) -> dict[str, Any]:
    """项目完整快照：状态 + 交付物 + 当前可做的动作。"""
    store = StateStore(paths, project)
    state = store.load()
    catalog = load_sops(paths)

    cur = state.stage(state.current_stage)
    cur_sop = None
    if cur is not None and cur.sop:
        try:
            cur_sop = catalog.get(cur.sop)
        except PipelineError:
            cur_sop = None
    elif cur is not None:
        try:
            cur_sop = catalog.by_stage(cur.id)
        except PipelineError:
            cur_sop = None

    deliverables = []
    for d in state.deliverables:
        abs_path = paths.root / d.path.replace("{{project}}", project)
        deliverables.append(
            {
                "id": d.id,
                "path": d.path,
                "version": d.version,
                "status": d.status,
                "produced_by": d.produced_by,
                "stale_reason": d.stale_reason,
                "exists": abs_path.exists(),
                "size": abs_path.stat().st_size if abs_path.exists() else 0,
            }
        )

    return {
        "codename": state.project.codename,
        "flow": state.project.flow,
        "target_project": state.project.target_project,
        "current_stage": state.current_stage,
        "progress": _project_progress(state),
        "stages": [
            {
                "id": s.id,
                "name": s.name,
                "status": s.status,
                "icon": _STAGE_ICONS.get(s.status, "?"),
                "label": _STAGE_LABELS.get(s.status, s.status),
                "rounds": s.review_rounds,
                "sop": s.sop,
                "gate": {
                    "actions": s.gate.actions,
                    "review_package": s.gate.review_package_paths,
                    "resolved_at": s.gate.resolved_at,
                },
            }
            for s in state.stages
        ],
        "deliverables": deliverables,
        "backfills": [
            {
                "id": b.id,
                "item": b.item,
                "owner": b.owner,
                "close_condition": b.close_condition,
                "blocks_acceptance": b.blocks_acceptance,
                "source_stage": b.source_stage,
                "status": b.status,
            }
            for b in state.backfills
        ],
        "gate_log": [
            {
                "ts": g.ts,
                "stage": g.stage,
                "action": g.action,
                "comment": g.comment,
                "actor": g.actor,
            }
            for g in state.gate_log[-20:]
        ],
        "current_sop": (
            {
                "id": cur_sop.id,
                "name": cur_sop.name,
                "owner_agent": cur_sop.owner_agent,
                "steps": [
                    {"id": s.id, "action": s.action, "description": s.description}
                    for s in cur_sop.steps
                ],
                "output_deliverable": cur_sop.output_deliverable,
                "gate_title": cur_sop.gate.title,
            }
            if cur_sop
            else None
        ),
        "actions": _available_actions(state, cur),
    }


def _available_actions(state: State, cur: Any) -> dict[str, bool]:
    if cur is None:
        return {"run": False, "submit": False, "gate": False, "done": True}
    return {
        "run": cur.status in {"ready", "revising", "running"},
        "submit": cur.status in {"ready", "revising", "running"},
        "gate": cur.status == "awaiting_review",
        "done": state.current_stage == "done",
    }


# ---------------------------------------------------------------------------
# 交付物读写
# ---------------------------------------------------------------------------

def read_deliverable(paths: Paths, project: str, deliverable_id: str) -> dict[str, Any]:
    store = StateStore(paths, project)
    state = store.load()
    d = state.deliverable(deliverable_id)
    if d is None:
        raise PipelineError(f"交付物未登记: {deliverable_id}")

    abs_path = paths.root / d.path.replace("{{project}}", project)
    return {
        "id": d.id,
        "path": d.path,
        "version": d.version,
        "status": d.status,
        "stale_reason": d.stale_reason,
        "exists": abs_path.exists(),
        "content": abs_path.read_text(encoding="utf-8") if abs_path.exists() else "",
    }


def write_deliverable(
    paths: Paths, project: str, deliverable_id: str, content: str
) -> dict[str, Any]:
    store = StateStore(paths, project)
    state = store.load()
    d = state.deliverable(deliverable_id)
    if d is None:
        raise PipelineError(f"交付物未登记: {deliverable_id}")

    abs_path = _assert_writable(paths, project, d.path)
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(content, encoding="utf-8")

    store.log(
        "deliverable_edited",
        state.current_stage,
        f"手工编辑 {deliverable_id}（{len(content)} 字符）",
        actor="user",
        state=state,
    )
    store.save(state)
    return {"id": deliverable_id, "bytes": len(content), "path": d.path}


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def validate_deliverable_op(
    paths: Paths,
    project: str,
    deliverable_id: str,
    *,
    fail_on: str = "any",
    run_rules: bool = False,
) -> dict[str, Any]:
    from .checks import (
        MarkdownDoc,
        evaluate_ruleset,
        load_manifest,
        load_ruleset,
        validate_manifest,
    )

    store = StateStore(paths, project)
    state = store.load()
    d = state.deliverable(deliverable_id)
    if d is None:
        raise PipelineError(f"交付物未登记: {deliverable_id}")

    abs_path = paths.root / d.path.replace("{{project}}", project)
    if not abs_path.exists():
        return {
            "ok": False,
            "violations": [
                {"kind": "missing_file", "section": "-", "message": f"文件不存在: {d.path}"}
            ],
            "rules": [],
        }

    text = abs_path.read_text(encoding="utf-8")
    manifest_rel = f"pipeline/manifests/{deliverable_id}.manifest.yaml"
    result_payload: dict[str, Any] = {"ok": True, "violations": [], "rules": []}

    if paths.resolve(manifest_rel).exists():
        manifest = load_manifest(paths, manifest_rel)
        vres = validate_manifest(text, manifest, fail_on=fail_on)
        result_payload["ok"] = vres.ok
        result_payload["violations"] = [
            {"kind": v.kind, "section": v.section, "message": v.message}
            for v in vres.violations
        ]
        result_payload["checked_sections"] = vres.checked_sections

    if run_rules:
        ruleset = load_ruleset(paths, "pipeline/gates/deliverable.rules.yaml")
        doc = MarkdownDoc(text)
        results = evaluate_ruleset(ruleset=ruleset, doc=doc, state=state, paths=paths)
        result_payload["rules"] = [
            {
                "id": r.id,
                "name": r.name,
                "severity": r.severity,
                "verdict": r.verdict,
                "message": r.message,
                "detail": r.detail,
            }
            for r in results
        ]
        if any(r["verdict"] == "fail" for r in result_payload["rules"]):
            result_payload["ok"] = False

    return result_payload


# ---------------------------------------------------------------------------
# 提交 / 关卡 / 执行
# ---------------------------------------------------------------------------

def submit_deliverable(
    paths: Paths,
    project: str,
    *,
    stage: str | None = None,
    deliverable_id: str | None = None,
    skip_validate: bool = False,
) -> dict[str, Any]:
    """手工提交交付物 → 校验 → 进入关卡待评审。"""
    store = StateStore(paths, project)
    state = store.load()
    catalog = load_sops(paths)

    target_stage = stage or state.current_stage
    if target_stage == "done":
        raise GateError("项目已完成")

    sop = catalog.by_stage(target_stage)
    did = deliverable_id or sop.output_deliverable
    if not did:
        raise GateError(f"阶段 {target_stage} 未定义交付物")

    d = state.deliverable(did)
    if d is None:
        raise GateError(f"交付物未登记: {did}")

    abs_path = paths.root / d.path.replace("{{project}}", project)
    if not abs_path.exists():
        raise GateError(f"文件不存在: {d.path}", hint="先编写交付物内容再提交")

    if not skip_validate:
        check = validate_deliverable_op(paths, project, did)
        if not check["ok"]:
            return {"ok": False, "stage": target_stage, "validation": check}

    d.version = max(d.version, 1) if d.version == 0 else d.version + 1
    d.status = "in-review"
    d.stale_reason = None

    st = state.stage(target_stage)
    if st is not None:
        st.status = "awaiting_review"
        st.sop = sop.id
        st.review_rounds = max(st.review_rounds, 1)
        st.gate.actions = list(sop.gate.actions or ["approve", "revise", "reject"])
        st.gate.review_package_paths = [
            p.replace("{{project}}", project) for p in sop.gate.review_package
        ] or [d.path]
        st.gate.resolved_at = None
    state.current_stage = target_stage

    store.log(
        "review_submitted",
        target_stage,
        f"手工提交 {did} v{d.version}",
        actor="user",
        state=state,
    )
    store.save(state)

    return {
        "ok": True,
        "stage": target_stage,
        "stage_name": st.name if st else target_stage,
        "deliverable": did,
        "version": d.version,
        "gate_title": sop.gate.title,
        "actions": list(sop.gate.actions),
    }


def apply_gate(
    paths: Paths,
    project: str,
    *,
    stage: str | None = None,
    action: str,
    comment: str = "",
) -> dict[str, Any]:
    store = StateStore(paths, project)
    state = store.load()
    catalog = load_sops(paths)
    target_stage = stage or state.current_stage

    manager = GateManager(paths=paths, catalog=catalog)
    outcome = manager.act(
        project=project,
        stage=target_stage,
        action=action,
        comment=comment,
        actor="user",
    )
    return {
        "ok": True,
        "stage": outcome.stage,
        "action": outcome.action,
        "deliverable_status": outcome.deliverable_status,
        "version": outcome.version,
        "staled": outcome.staled,
        "reopened_sop": outcome.reopened_sop,
        "next_stage": outcome.next_stage,
        "next_sop": outcome.next_sop,
        "done": outcome.next_stage == "done",
    }


def build_router(
    paths: Paths,
    *,
    override_backend: str | None = None,
) -> Any:
    """按配置构造按岗位路由的 invoker。

    优先级：命令行 override > agents.<name>.backend > default_backend
    """
    from .config import load_config, resolve_backend
    from .invokers import RoutingInvoker, build_invoker

    cfg = load_config(paths)
    agents = ("planner", "designer", "developer", "tester", "acceptor")

    mapping: dict[str, Any] = {}
    default_invoker: Any = None
    for agent in agents:
        spec = resolve_backend(cfg, agent=agent, override=override_backend)
        invoker = build_invoker(spec, cfg=cfg)
        mapping[agent] = invoker
        if default_invoker is None:
            default_invoker = invoker

    return RoutingInvoker(mapping, default_invoker or MockInvoker())


def run_stage(
    paths: Paths,
    project: str,
    *,
    stage: str | None = None,
    answers: dict[str, str] | None = None,
    force: bool = False,
    backend: str | None = None,
    emit: Any = None,
) -> dict[str, Any]:
    from .engine import Engine
    from .config import describe_backends, load_config, agent_routing

    catalog = load_sops(paths)
    invoker = build_router(paths, override_backend=backend)
    cfg = load_config(paths)
    routing = agent_routing(cfg)
    if backend:
        routing = {k: backend for k in routing}

    engine = Engine(
        paths=paths,
        catalog=catalog,
        invoker=invoker,
        emit=emit or (lambda _m: None),
    )
    report = engine.run(
        project=project,
        stage=stage,
        answers=answers or {},
        force=force,
    )
    return {
        "ok": report.ok,
        "sop": report.sop_id,
        "stage": report.stage,
        "status": report.status,
        "error": report.error,
        "needs_human": report.needs_human,
        "degraded": list(report.degraded.keys()),
        "backend_routing": routing,
        "steps": [
            {
                "id": s.step_id,
                "action": s.action,
                "status": s.status,
                "detail": s.detail,
            }
            for s in report.steps
        ],
    }


# ---------------------------------------------------------------------------
# 新建项目
# ---------------------------------------------------------------------------

def create_project(
    paths: Paths,
    *,
    codename: str,
    flow: str = "new_project",
    target_project: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    from .models import Deliverable, Gate, ProjectMeta, Stage

    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,40}", codename):
        raise PipelineError(
            f"项目代号非法: {codename}",
            hint="只允许字母、数字、- 和 _，长度 1-41",
        )
    if flow not in {"new_project", "new_requirement"}:
        raise PipelineError(f"未知流程类型: {flow}")
    if flow == "new_requirement" and not target_project:
        raise PipelineError("增量流程必须指定目标项目")

    state_file = paths.projects / codename / "pipeline-state.json"
    if state_file.exists() and not force:
        raise PipelineError(
            f"项目已存在: {codename}", hint="用 force=true 覆盖，或换一个代号"
        )

    # 阶段与交付物定义（与 CLI init 保持同源）
    if flow == "new_project":
        stage_defs = [
            ("brief", "立项简报", "user", "00-brief"),
            ("planning", "规划", "planner", "01-planning"),
            ("design", "设计", "designer", "02-design"),
            ("development", "开发", "developer", "03-development"),
            ("testing", "测试", "tester", "04-testing"),
            ("acceptance", "验收", "acceptor", "05-acceptance"),
        ]
        deliv_defs = [
            ("project_brief", "pipeline/projects/{{project}}/00-project-brief.md", "user"),
            ("prd", "pipeline/projects/{{project}}/01-prd.md", "planner"),
            ("design_brief", "pipeline/projects/{{project}}/02-design-brief.md", "designer"),
            ("design_delivery", "pipeline/projects/{{project}}/03-design-delivery.md", "designer"),
            ("dev_report", "pipeline/projects/{{project}}/04-dev-report.md", "developer"),
            ("test_report", "pipeline/projects/{{project}}/05-test-report.md", "tester"),
            ("acceptance_report", "pipeline/projects/{{project}}/06-acceptance-report.md", "acceptor"),
        ]
    else:
        stage_defs = [
            ("intake", "需求分流/录入", "user", "intake-routing"),
            ("planning_delta", "增量规划", "planner", "11-planning-delta"),
            ("design", "设计增量", "designer", "12a-design-delta"),
            ("development_delta", "增量开发", "developer", "12b-development-delta"),
            ("testing_regression", "增量测试", "tester", "13-testing-regression"),
            ("acceptance_delta", "增量验收", "acceptor", "14-acceptance-delta"),
        ]
        deliv_defs = [
            ("intake_routing", "pipeline/projects/{{project}}/intake-routing.md", "planner"),
            ("requirement_brief", "pipeline/projects/{{project}}/10-requirement.md", "user"),
            ("prd_delta", "pipeline/projects/{{project}}/11-prd-delta.md", "planner"),
            ("design_delta", "pipeline/projects/{{project}}/12-design-delta.md", "designer"),
            ("dev_report_delta", "pipeline/projects/{{project}}/13-dev-delta.md", "developer"),
            ("test_report_delta", "pipeline/projects/{{project}}/14-test-delta.md", "tester"),
            ("acceptance_report_delta", "pipeline/projects/{{project}}/15-acceptance-delta.md", "acceptor"),
        ]

    stages = [
        Stage(
            id=sid,
            name=name,
            owner_agent=owner,
            sop=sop,
            status="ready" if i == 0 else "locked",
            gate=Gate(),
        )
        for i, (sid, name, owner, sop) in enumerate(stage_defs)
    ]
    deliverables = [
        Deliverable(
            id=did,
            path=tpl.replace("{{project}}", codename),
            version=0,
            status="draft",
            produced_by=owner,
            stale_reason="未产出",
        )
        for did, tpl, owner in deliv_defs
    ]

    state = State(
        project=ProjectMeta(
            codename=codename, flow=flow, target_project=target_project  # type: ignore[arg-type]
        ),
        current_stage=stages[0].id,
        stages=stages,
        deliverables=deliverables,
    )

    pdir = paths.projects / codename
    pdir.mkdir(parents=True, exist_ok=True)
    store = StateStore(paths, codename)
    store.log(
        "stage_started", stages[0].id, f"项目初始化（{flow}）", actor="user", state=state
    )
    store.save(state)

    # 用模板铺好初始骨架：用户打开即有结构可改，而不是面对空文件
    seeded = _seed_from_templates(paths, codename, deliverables)
    if seeded:
        # 已铺骨架的交付物不再是「未产出」，改为待填充
        for d in state.deliverables:
            if d.id in seeded and d.status == "draft":
                d.stale_reason = "骨架已就绪，待填充"
        store.save(state)

    return {
        "ok": True,
        "codename": codename,
        "flow": flow,
        "stages": len(stages),
        "deliverables": len(deliverables),
        "seeded": seeded,
    }


def _seed_from_templates(paths: Paths, project: str, deliverables: list[Any]) -> list[str]:
    """把模板内容写入尚未存在的交付物文件（含 {{占位符}}，提交时会被校验拦住）。"""
    seeded: list[str] = []
    for d in deliverables:
        stem = TEMPLATE_MAP.get(d.id)
        if not stem:
            continue
        tpl = paths.templates / f"{stem}.template.md"
        if not tpl.exists():
            continue
        target = paths.root / d.path
        if target.exists():
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(tpl.read_text(encoding="utf-8"), encoding="utf-8")
            seeded.append(d.id)
        except OSError:
            # 铺模板失败不影响项目创建
            continue
    return seeded
