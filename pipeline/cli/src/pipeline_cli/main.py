"""CLI 命令面。

设计原则：
- 每条命令只做一件事，输出可读、可管道
- 失败用退出码区分（见 errors.py）
- `run` 跑完必停在 gate，绝不自动连跑
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .agents import MockInvoker
from .checks import (
    MarkdownDoc,
    evaluate_ruleset,
    load_manifest,
    load_ruleset,
    summarize,
    validate_manifest,
)
from .engine import Engine
from .errors import PipelineError
from .gate import GateManager
from .models import (
    Deliverable,
    Gate,
    ProjectMeta,
    Stage,
    State,
)
from .paths import Paths
from .sops import load_sops
from .state import StateStore

app = typer.Typer(
    add_completion=False,
    help="AI 移动应用生产线 · SOP 调度器（M2）",
    no_args_is_help=True,
)
console = Console()


def _paths() -> Paths:
    return Paths.discover()


def _fail(exc: PipelineError) -> None:
    console.print(f"[red]✗[/red] {exc.render()}")
    raise typer.Exit(code=exc.exit_code)


# ---------------------------------------------------------------------------
# 阶段 / 交付物定义表（init 用）
# ---------------------------------------------------------------------------

NEW_PROJECT_STAGES: list[tuple[str, str, str, str]] = [
    # (stage_id, name, owner_agent, sop_id)
    ("brief", "立项简报", "user", "00-brief"),
    ("planning", "规划", "planner", "01-planning"),
    ("design", "设计", "designer", "02-design"),
    ("development", "开发", "developer", "03-development"),
    ("testing", "测试", "tester", "04-testing"),
    ("acceptance", "验收", "acceptor", "05-acceptance"),
]

NEW_PROJECT_DELIVERABLES: list[tuple[str, str, str]] = [
    ("project_brief", "pipeline/projects/{{p}}/00-project-brief.md", "user"),
    ("prd", "pipeline/projects/{{p}}/01-prd.md", "planner"),
    ("design_brief", "pipeline/projects/{{p}}/02-design-brief.md", "designer"),
    ("design_delivery", "pipeline/projects/{{p}}/03-design-delivery.md", "designer"),
    ("dev_report", "pipeline/projects/{{p}}/04-dev-report.md", "developer"),
    ("test_report", "pipeline/projects/{{p}}/05-test-report.md", "tester"),
    ("acceptance_report", "pipeline/projects/{{p}}/06-acceptance-report.md", "acceptor"),
]

NEW_REQUIREMENT_STAGES: list[tuple[str, str, str, str]] = [
    ("intake", "需求分流", "planner", "intake-routing"),
    ("intake", "需求录入", "user", "10-requirement-intake"),
    ("planning_delta", "增量规划", "planner", "11-planning-delta"),
    ("design", "设计增量", "designer", "12a-design-delta"),
    ("development_delta", "增量开发", "developer", "12b-development-delta"),
    ("testing_regression", "增量测试", "tester", "13-testing-regression"),
    ("acceptance_delta", "增量验收", "acceptor", "14-acceptance-delta"),
]

NEW_REQUIREMENT_DELIVERABLES: list[tuple[str, str, str]] = [
    ("intake_routing", "pipeline/projects/{{p}}/intake-routing.md", "planner"),
    ("requirement_brief", "pipeline/projects/{{p}}/10-requirement.md", "user"),
    ("prd_delta", "pipeline/projects/{{p}}/11-prd-delta.md", "planner"),
    ("design_delta", "pipeline/projects/{{p}}/12-design-delta.md", "designer"),
    ("dev_report_delta", "pipeline/projects/{{p}}/13-dev-delta.md", "developer"),
    ("test_report_delta", "pipeline/projects/{{p}}/14-test-delta.md", "tester"),
    ("acceptance_report_delta", "pipeline/projects/{{p}}/15-acceptance-delta.md", "acceptor"),
]


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

@app.command()
def init(
    project: str = typer.Argument(..., help="项目代号（目录名）"),
    flow: str = typer.Option("new_project", "--flow", help="new_project | new_requirement"),
    target_project: Optional[str] = typer.Option(
        None, "--target", help="增量流程的目标项目"
    ),
    app_repo: str = typer.Option("", "--app-repo", help="App 代码目录（相对仓库根）"),
    force: bool = typer.Option(False, "--force", help="覆盖已存在的状态文件"),
) -> None:
    """初始化一个项目的状态机。"""
    try:
        paths = _paths()
        pdir = paths.projects / project
        state_file = pdir / "pipeline-state.json"
        if state_file.exists() and not force:
            console.print(
                f"[yellow]![/yellow] 状态文件已存在: {paths.rel(state_file)}"
                "\n  用 --force 覆盖，或用 `pipeline status` 查看现状"
            )
            raise typer.Exit(code=1)

        if flow not in {"new_project", "new_requirement"}:
            console.print(f"[red]✗[/red] 未知流程类型: {flow}")
            raise typer.Exit(code=2)

        if flow == "new_requirement" and not target_project:
            console.print("[red]✗[/red] 增量流程必须用 --target 指定目标项目")
            raise typer.Exit(code=2)

        stage_defs = NEW_PROJECT_STAGES if flow == "new_project" else NEW_REQUIREMENT_STAGES
        deliv_defs = (
            NEW_PROJECT_DELIVERABLES
            if flow == "new_project"
            else NEW_REQUIREMENT_DELIVERABLES
        )

        stages: list[Stage] = []
        seen: set[str] = set()
        for idx, (sid, name, owner, sop_id) in enumerate(stage_defs):
            if sid in seen and flow == "new_requirement" and sid == "intake":
                # 增量流程有两个 intake（分流 / 录入），合并为一个阶段条目
                continue
            seen.add(sid)
            stages.append(
                Stage(
                    id=sid,
                    name=name,
                    owner_agent=owner,
                    sop=sop_id,
                    status="ready" if idx == 0 else "locked",
                    gate=Gate(),
                )
            )

        deliverables = [
            Deliverable(
                id=did,
                path=path_tpl.replace("{{p}}", project),
                version=0,
                status="draft",
                produced_by=owner,
                stale_reason="未产出",
            )
            for did, path_tpl, owner in deliv_defs
        ]

        state = State(
            project=ProjectMeta(
                codename=project,
                flow=flow,  # type: ignore[arg-type]
                target_project=target_project,
                app_repo_path=app_repo or f"{project}/",
            ),
            current_stage=stages[0].id,
            stages=stages,
            deliverables=deliverables,
        )

        pdir.mkdir(parents=True, exist_ok=True)
        store = StateStore(paths, project)
        store.log(
            "stage_started",
            stages[0].id,
            f"项目初始化（流程 {flow}）",
            actor="system",
            state=state,
        )
        store.save(state)
        console.print(
            f"[green]✓[/green] 已初始化 {project}（{flow}）"
            f"\n  阶段: {len(stages)} · 交付物: {len(deliverables)}"
            f"\n  状态文件: {paths.rel(state_file)}"
        )
    except PipelineError as exc:
        _fail(exc)


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

@app.command()
def run(
    project: str = typer.Argument(..., help="项目代号"),
    stage: Optional[str] = typer.Option(None, "--stage", help="要执行的阶段 id"),
    sop_id: Optional[str] = typer.Option(None, "--sop", help="直接指定 SOP id"),
    answer: Optional[list[str]] = typer.Option(
        None, "--answer", help="人工输入 key=value（可重复）"
    ),
    force: bool = typer.Option(False, "--force", help="忽略已完成步骤，强制重跑"),
    dry_run: bool = typer.Option(False, "--dry-run", help="只走骨架，不实际调用 Agent"),
    agent: str = typer.Option("mock", "--agent", help="mock | headless"),
) -> None:
    """执行一个阶段的 SOP（跑完必停在关卡）。"""
    try:
        paths = _paths()
        catalog = load_sops(paths)

        answers: dict[str, str] = {}
        for item in answer or []:
            if "=" not in item:
                console.print(f"[red]✗[/red] --answer 需要 key=value 形式: {item}")
                raise typer.Exit(code=2)
            k, _, v = item.partition("=")
            answers[k.strip()] = v.strip()

        invoker = MockInvoker()
        if agent == "headless":
            console.print(
                "[yellow]![/yellow] headless 通道将在 M3 接入，本次降级为 mock"
            )
            invoker = MockInvoker()

        engine = Engine(
            paths=paths,
            catalog=catalog,
            invoker=invoker,
            emit=lambda m: console.print(m),
        )
        report = engine.run(
            project=project,
            stage=stage,
            sop_id=sop_id,
            answers=answers,
            force=force,
            dry_run=dry_run,
        )

        console.print("")
        if report.status == "awaiting_review":
            payload = report.needs_human or {}
            title = payload.get("title", "关卡")
            actions = payload.get("actions") or []
            console.print(f"[bold cyan]⏸ {title}[/bold cyan] 等待人工确认")
            package = payload.get("review_package") or []
            if package:
                console.print("  评审包:")
                for p in package:
                    console.print(f"    - {p}")
            if actions:
                console.print(f"  可用动作: {' / '.join(actions)}")
            console.print(
                f"\n  下一步: [bold]pipeline gate {project} --stage={report.stage} "
                f"--action=approve[/bold]"
            )
            raise typer.Exit(code=0)

        if report.status == "failed":
            console.print(f"[red]✗ 执行失败[/red] {report.error}")
            raise typer.Exit(code=5)

        console.print(f"[green]✓[/green] 阶段 {report.stage} 完成")
    except PipelineError as exc:
        _fail(exc)


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------

@app.command()
def gate(
    project: str = typer.Argument(..., help="项目代号"),
    stage: Optional[str] = typer.Option(None, "--stage", help="阶段 id"),
    action: str = typer.Option(..., "--action", help="approve | revise | reject"),
    comment: str = typer.Option("", "--comment", help="意见（revise/reject 必填）"),
    actor: str = typer.Option("user", "--actor", help="操作者"),
) -> None:
    """关卡三态动作：通过 / 调整 / 打回。"""
    try:
        paths = _paths()
        catalog = load_sops(paths)
        store = StateStore(paths, project)
        state = store.load()
        target_stage = stage or state.current_stage

        manager = GateManager(paths=paths, catalog=catalog)
        outcome = manager.act(
            project=project,
            stage=target_stage,
            action=action,
            comment=comment,
            actor=actor,
        )
        console.print(f"[green]✓[/green] {outcome.render()}")

        if outcome.action == "approve" and outcome.next_stage == "done":
            console.print("\n[bold green]🎉 项目已全部完成[/bold green]")
        elif outcome.next_sop:
            console.print(
                f"\n  下一步: [bold]pipeline run {project} --stage={outcome.next_stage}[/bold]"
            )
        elif outcome.action == "revise":
            console.print(
                f"\n  下一步: [bold]pipeline run {project} --stage={outcome.stage} --force[/bold]"
                "\n  （只修改被质疑部分，其余保持不变）"
            )
    except PipelineError as exc:
        _fail(exc)


# ---------------------------------------------------------------------------
# submit（手工交付物提交评审）
# ---------------------------------------------------------------------------

@app.command()
def submit(
    project: str = typer.Argument(..., help="项目代号"),
    stage: Optional[str] = typer.Option(None, "--stage", help="阶段 id（默认当前阶段）"),
    deliverable: Optional[str] = typer.Option(
        None, "--deliverable", help="交付物 id（默认取 SOP 主输出）"
    ),
    skip_validate: bool = typer.Option(
        False, "--skip-validate", help="跳过 manifest 校验（不推荐）"
    ),
) -> None:
    """提交手工编写的交付物，进入关卡待评审。

    用于「混合模式」：你自己写交付物内容 → 机器校验结构 → 进入关卡等人确认。
    等价于 run 阶段，但跳过 invoke_agent（不调用 Agent 生成内容）。
    """
    try:
        paths = _paths()
        catalog = load_sops(paths)
        store = StateStore(paths, project)
        state = store.load()

        target_stage = stage or state.current_stage
        if target_stage == "done":
            console.print("[red]✗[/red] 项目已完成")
            raise typer.Exit(code=2)

        sop = catalog.by_stage(target_stage)
        did = deliverable or sop.output_deliverable
        if not did:
            console.print(f"[red]✗[/red] 阶段 {target_stage} 未定义交付物")
            raise typer.Exit(code=2)

        d = state.deliverable(did)
        if d is None:
            console.print(f"[red]✗[/red] 交付物未登记: {did}")
            raise typer.Exit(code=2)

        target = paths.resolve(d.path)
        if not target.exists():
            console.print(
                f"[red]✗[/red] 文件不存在: {d.path}\n"
                f"  请先创建并写入内容"
            )
            raise typer.Exit(code=1)

        # 1) 机械校验
        if not skip_validate:
            manifest_rel = sop.output.get("manifest") or (
                f"pipeline/manifests/{did}.manifest.yaml"
            )
            if paths.resolve(manifest_rel).exists():
                manifest = load_manifest(paths, manifest_rel)
                result = validate_manifest(
                    target.read_text(encoding="utf-8"), manifest
                )
                console.print(result.render())
                if not result.ok:
                    console.print(
                        "\n[yellow]提示[/yellow] 修正上述问题后重新执行 submit；"
                        "或用 --skip-validate 强制提交（不推荐）"
                    )
                    raise typer.Exit(code=1)
            else:
                console.print(f"[yellow]![/yellow] 无 manifest，跳过校验: {manifest_rel}")

        # 2) 登记版本与状态
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

        console.print(f"[green]✓[/green] 已提交 {did} v{d.version} 进入评审")
        console.print(f"\n  关卡: {sop.gate.title or target_stage}")
        console.print(f"  评审包: {d.path}")
        if sop.gate.actions:
            console.print(f"  可用动作: {' / '.join(sop.gate.actions)}")
        console.print(
            f"\n  下一步: [bold]pipeline gate {project} --stage={target_stage} "
            f"--action=approve[/bold]"
        )
    except PipelineError as exc:
        _fail(exc)


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.command()
def status(
    project: str = typer.Argument(..., help="项目代号"),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="显示交付物明细"),
) -> None:
    """查看项目进度。"""
    try:
        paths = _paths()
        store = StateStore(paths, project)
        state = store.load()

        # 阶段表
        table = Table(title=f"项目 {project}（{state.project.flow}）", show_header=True)
        table.add_column("阶段", style="bold")
        table.add_column("状态")
        table.add_column("轮次", justify="right")
        table.add_column("SOP")

        icons = {
            "locked": "· 未开始",
            "ready": "→ 就绪",
            "running": "▶ 执行中",
            "awaiting_review": "⏸ 待评审",
            "revising": "✎ 调整中",
            "approved": "✓ 已通过",
            "rejected": "✗ 已打回",
        }
        for s in state.stages:
            style = ""
            if s.status == "awaiting_review":
                style = "cyan"
            elif s.status == "approved":
                style = "green"
            elif s.status == "rejected":
                style = "red"
            table.add_row(
                f"{s.name}（{s.id}）",
                f"[{style}]{icons.get(s.status, s.status)}[/{style}]" if style else icons.get(s.status, s.status),
                str(s.review_rounds),
                s.sop or "-",
            )
        console.print(table)

        # 交付物
        if verbose:
            dt = Table(title="交付物", show_header=True)
            dt.add_column("id")
            dt.add_column("版本", justify="right")
            dt.add_column("状态")
            dt.add_column("说明")
            for d in state.deliverables:
                st = d.status
                if st == "approved":
                    st = f"[green]{st}[/green]"
                elif st == "stale":
                    st = f"[red]{st}[/yellow]".replace("[/yellow]", "[/red]")
                elif st == "in-review":
                    st = f"[cyan]{st}[/cyan]"
                dt.add_row(d.id, f"v{d.version}", st, d.stale_reason or "")
            console.print(dt)

        # 回填
        open_bf = state.open_backfills()
        if open_bf:
            console.print(f"\n[yellow]未关闭回填任务 {len(open_bf)} 项:[/yellow]")
            for b in open_bf:
                block = "[red]阻塞验收[/red]" if b.blocks_acceptance else "不阻塞"
                console.print(f"  - {b.id} {b.item} · {b.owner} · {block}")

        console.print(f"\n当前阶段: [bold]{state.current_stage}[/bold]")
        if state.current_stage == "done":
            console.print("[bold green]项目已完成[/bold green]")
        else:
            cur = state.stage(state.current_stage)
            if cur is not None and cur.status == "awaiting_review":
                console.print(
                    f"  [cyan]等待确认[/cyan]: pipeline gate {project} "
                    f"--stage={cur.id} --action=approve"
                )
            elif cur is not None:
                console.print(
                    f"  可执行: pipeline run {project} --stage={cur.id}"
                )
    except PipelineError as exc:
        _fail(exc)


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@app.command()
def validate(
    project: str = typer.Argument(..., help="项目代号"),
    deliverable: str = typer.Option(..., "--deliverable", help="交付物 id"),
    fail_on: str = typer.Option("any", "--fail-on", help="missing_section|missing_field|any"),
    rules: bool = typer.Option(False, "--rules", help="同时跑内容规则（DR-*）"),
) -> None:
    """按 manifest 校验一份交付物。"""
    try:
        paths = _paths()
        store = StateStore(paths, project)
        state = store.load()
        d = state.deliverable(deliverable)
        if d is None:
            console.print(f"[red]✗[/red] 交付物未登记: {deliverable}")
            raise typer.Exit(code=2)

        target = paths.resolve(d.path)
        if not target.exists():
            console.print(f"[red]✗[/red] 文件不存在: {d.path}")
            raise typer.Exit(code=1)

        manifest_rel = f"pipeline/manifests/{deliverable}.manifest.yaml"
        manifest = load_manifest(paths, manifest_rel)
        text = target.read_text(encoding="utf-8")
        result = validate_manifest(text, manifest, fail_on=fail_on)
        console.print(result.render())

        if rules:
            doc = MarkdownDoc(text)
            ruleset = load_ruleset(paths, "pipeline/gates/deliverable.rules.yaml")
            results = evaluate_ruleset(
                ruleset=ruleset, doc=doc, state=state, paths=paths
            )
            ok, text_summary = summarize(results)
            console.print("\n内容规则:")
            for line in text_summary.splitlines():
                console.print(f"  {line}")
            if not ok:
                raise typer.Exit(code=1)

        if not result.ok:
            raise typer.Exit(code=1)
    except PipelineError as exc:
        _fail(exc)


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

@app.command()
def report(
    project: str = typer.Argument(..., help="项目代号"),
    as_json: bool = typer.Option(False, "--json", help="输出 JSON"),
) -> None:
    """输出项目报告（交付物 + 关卡 + 回填 + 事件）。"""
    try:
        paths = _paths()
        store = StateStore(paths, project)
        state = store.load()

        payload = {
            "project": state.project.model_dump(mode="json"),
            "current_stage": state.current_stage,
            "stages": [s.model_dump(mode="json") for s in state.stages],
            "deliverables": [d.model_dump(mode="json") for d in state.deliverables],
            "backfills": [b.model_dump(mode="json") for b in state.backfills],
            "gate_log": [g.model_dump(mode="json") for g in state.gate_log],
            "history_count": len(state.history),
        }
        if as_json:
            console.print_json(json.dumps(payload, ensure_ascii=False))
            return

        console.print(f"[bold]项目 {project}[/bold]")
        console.print(f"  流程: {state.project.flow}")
        console.print(f"  当前阶段: {state.current_stage}")
        console.print(f"  交付物: {len(state.deliverables)}")
        console.print(f"  关卡操作: {len(state.gate_log)} 次")
        console.print(f"  事件日志: {len(state.history)} 条")
        console.print(f"  未关闭回填: {len(state.open_backfills())} 项")
        if state.gate_log:
            console.print("\n关卡轨迹:")
            for g in state.gate_log:
                console.print(
                    f"  {g.ts} {g.stage} → {g.action}"
                    + (f"：{g.comment}" if g.comment else "")
                )
    except PipelineError as exc:
        _fail(exc)


# ---------------------------------------------------------------------------
# preflight（M1 规则集的简化执行版）
# ---------------------------------------------------------------------------

@app.command()
def preflight(
    project: Optional[str] = typer.Argument(None, help="项目代号（可选）"),
) -> None:
    """资产装配检查（M2 实现可执行子集，其余返回 DEGRADED）。"""
    paths = _paths()
    checks: list[tuple[str, str, str]] = []

    def add(item: str, level: str, result: str) -> None:
        checks.append((item, level, result))

    # AR-03 规范体系（可自动装配）
    if project:
        pdir = paths.projects / project if (paths.projects / project).exists() else paths.root / project
        agents_md = pdir / "AGENTS.md"
        rules = pdir / ".github" / "skills" / "flutter-dev-playbook" / "rules"
        if agents_md.exists() and rules.exists():
            add("规范体系（AGENTS.md + rules）", "AUTO-FIX", "OK")
        else:
            add(
                "规范体系（AGENTS.md + rules）",
                "AUTO-FIX",
                f"DEGRADED → 运行 pipeline/scripts/sync-spec.sh {project}",
            )
        # AR-04 集成测试
        it = pdir / "integration_test"
        add(
            "集成测试截图工具链",
            "DEGRADED",
            "OK" if it.exists() else "DEGRADED → UI 对比降级为人工核对",
        )

    # AR-01/02 Figma（M2 无法探测）
    add("Figma MCP 连通性", "DEGRADED", "UNKNOWN → M3 接入探测")
    add("团队组件库/Variables", "DEGRADED", "UNKNOWN → M3 接入探测")

    # AR-06 Flutter SDK
    import shutil

    add(
        "Flutter SDK",
        "BLOCKED",
        "OK" if shutil.which("flutter") else "BLOCKED → 未安装 Flutter",
    )

    # AR-08 Git
    is_git = (paths.root / ".git").exists()
    add("Git 仓库", "DEGRADED", "OK" if is_git else "DEGRADED → 无 PR 链接")

    # AR-10 Agent 通道
    add("Agent 执行通道", "BLOCKED", "OK → mock 可用（headless 待 M3）")

    table = Table(title="preflight 资产装配检查", show_header=True)
    table.add_column("检查项")
    table.add_column("级别")
    table.add_column("结果")
    for item, level, result in checks:
        style = "green" if result.startswith("OK") else (
            "red" if result.startswith("BLOCKED") else "yellow"
        )
        table.add_row(item, level, f"[{style}]{result}[/{style}]")
    console.print(table)

    blocked = [c for c in checks if c[2].startswith("BLOCKED")]
    degraded = [c for c in checks if c[2].startswith(("DEGRADED", "UNKNOWN"))]
    console.print(
        f"\n{len(checks)} 项检查："
        f"[red]{len(blocked)} BLOCKED[/red] · "
        f"[yellow]{len(degraded)} DEGRADED[/yellow] · "
        f"[green]{len(checks) - len(blocked) - len(degraded)} OK[/green]"
    )
    if blocked:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

@app.command()
def version() -> None:
    """显示版本。"""
    console.print(f"pipeline-cli {__version__}")


if __name__ == "__main__":
    app()
