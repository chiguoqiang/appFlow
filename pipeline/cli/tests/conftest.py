"""测试夹具：在临时目录里搭一个最小可运行的 pipeline 仓库。

为什么不用真实仓库做测试：
- 真实仓库已有 demo-habit 状态文件，测试会互相污染
- 测试需要控制 SOP 内容（验证特定行为）

做法：复制真实 sops / manifests / gates（它们是契约，应该被真实测试），
但用临时 projects 目录与可控的模板文件。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]  # .../project
REAL_PIPELINE = REPO_ROOT / "pipeline"


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    """构造一个隔离的仓库根。"""
    root = tmp_path / "repo"
    pipeline = root / "pipeline"
    pipeline.mkdir(parents=True)

    for sub in ("sops", "manifests", "gates"):
        src = REAL_PIPELINE / sub
        if src.exists():
            shutil.copytree(src, pipeline / sub)

    (pipeline / "projects").mkdir()
    (pipeline / "templates").mkdir()
    (pipeline / "agents").mkdir()

    # 最小模板（MockAgent 不读，但 validate_inputs / must_read 可能引用）
    (pipeline / "templates" / "01-prd.template.md").write_text(
        "# PRD\n\n## 用户故事\n\n## 任务拆解\n", encoding="utf-8"
    )
    (pipeline / "agents" / "planner.md").write_text("planner 契约", encoding="utf-8")
    return root


@pytest.fixture()
def paths(sandbox: Path):
    from pipeline_cli.paths import Paths

    return Paths(root=sandbox)


@pytest.fixture()
def catalog(paths):
    from pipeline_cli.sops import load_sops

    return load_sops(paths)


@pytest.fixture()
def sample_manifest():
    """一个最小 manifest，供 checks 测试使用。"""
    return {
        "manifest": "sample",
        "deliverable": "sample",
        "sections": [
            {
                "id": "stories",
                "title": "用户故事",
                "type": "table",
                "required": True,
                "columns": ["#", "用户故事", "优先级", "验收标准"],
                "min_rows": 1,
                "row_id_pattern": "US-\\d+",
            },
            {
                "id": "tasks",
                "title": "任务拆解",
                "type": "table",
                "required": True,
                "columns": ["#", "任务", "前置依赖", "验收方式"],
                "min_rows": 1,
            },
        ],
        "rules": {"forbid_placeholder": True},
    }


@pytest.fixture()
def valid_prd_text() -> str:
    return """# PRD

## 元数据

| 字段 | 值 |
|------|-----|
| PRD 版本 | v1 |

## 用户故事

| # | 用户故事 | 优先级 | 验收标准 |
|---|---------|--------|---------|
| US-1 | 作为用户我想打卡 | P0 | 点击后立即变已打卡 |

## 任务拆解

| # | 任务 | 前置依赖 | 验收方式 |
|---|------|---------|---------|
| T-01 | 实现打卡 | 无 | 单元测试通过 |
"""


@pytest.fixture()
def make_state():
    """工厂：快速造一个状态文件。"""

    def _make(
        paths,
        project: str = "demo",
        flow: str = "new_project",
        *,
        target: str | None = None,
    ):
        from pipeline_cli.main import NEW_PROJECT_DELIVERABLES, NEW_PROJECT_STAGES
        from pipeline_cli.models import Deliverable, Gate, ProjectMeta, Stage, State

        stages = [
            Stage(
                id=sid,
                name=name,
                owner_agent=owner,
                sop=sop,
                status="ready" if i == 0 else "locked",
                gate=Gate(),
            )
            for i, (sid, name, owner, sop) in enumerate(NEW_PROJECT_STAGES)
        ]
        deliverables = [
            Deliverable(
                id=did,
                path=tpl.replace("{{p}}", project),
                version=0,
                status="draft",
                produced_by=owner,
                stale_reason="未产出",
            )
            for did, tpl, owner in NEW_PROJECT_DELIVERABLES
        ]
        state = State(
            project=ProjectMeta(
                codename=project, flow=flow, target_project=target
            ),
            current_stage=stages[0].id,
            stages=stages,
            deliverables=deliverables,
        )
        pdir = paths.projects / project
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "pipeline-state.json").write_text(
            json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return state

    return _make
