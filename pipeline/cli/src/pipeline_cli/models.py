"""状态模型（pydantic）。

与 `pipeline/templates/pipeline-state.schema.json` 保持兼容，并在 M2 扩展三块内容：

- `flow`          流程类型（new_project / new_requirement）
- `backfills`     降级回填任务登记表（P0 教训：降级即遗忘）
- `gate_log`      关卡操作留痕（谁、何时、什么动作、什么意见）
- `stage_progress` 阶段内步骤执行进度（支持断点续跑）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

StageStatus = Literal[
    "locked",
    "ready",
    "running",
    "awaiting_review",
    "revising",
    "approved",
    "rejected",
]

DeliverableStatus = Literal["draft", "in-review", "approved", "stale"]
DeliverableId = str
Actor = str
StepStatus = Literal["done", "failed", "skipped"]


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


class Gate(BaseModel):
    model_config = ConfigDict(extra="allow")

    actions: list[str] = Field(default_factory=lambda: ["approve", "revise", "reject"])
    review_package_paths: list[str] = Field(default_factory=list)
    require_comment_on: list[str] = Field(default_factory=list)
    resolved_at: Optional[str] = None


class Stage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    owner_agent: str = "user"
    status: StageStatus = "locked"
    sop: Optional[str] = None
    review_rounds: int = 0
    gate: Gate = Field(default_factory=Gate)


class Deliverable(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: DeliverableId
    path: str
    version: int = 0
    status: DeliverableStatus = "draft"
    produced_by: str = "user"
    stale_reason: Optional[str] = None


class HistoryEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str = Field(default_factory=now_iso)
    type: str
    stage: str
    actor: str = "system"
    detail: str = ""
    deliverable_versions: dict[str, int] = Field(default_factory=dict)


class Backfill(BaseModel):
    """降级产生的回填任务。未关闭会影响验收判定上限。"""

    model_config = ConfigDict(extra="allow")

    id: str
    item: str
    owner: str
    close_condition: str
    blocks_acceptance: bool = False
    source_stage: str = ""
    created_at: str = Field(default_factory=now_iso)
    closed_at: Optional[str] = None
    status: Literal["open", "closed"] = "open"


class GateRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    ts: str = Field(default_factory=now_iso)
    stage: str
    action: Literal["approve", "revise", "reject"]
    actor: str = "user"
    comment: str = ""
    review_package: list[str] = Field(default_factory=list)
    deliverable_versions: dict[str, int] = Field(default_factory=dict)


class ProjectMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    codename: str
    platform: str = "flutter"
    flow: Literal["new_project", "new_requirement"] = "new_project"
    target_project: Optional[str] = None
    created_at: str = Field(default_factory=now_iso)
    app_repo_path: str = ""


class State(BaseModel):
    """pipeline-state.json 的完整内存模型。"""

    model_config = ConfigDict(extra="allow")

    project: ProjectMeta
    current_stage: str = "brief"
    stages: list[Stage] = Field(default_factory=list)
    deliverables: list[Deliverable] = Field(default_factory=list)
    history: list[HistoryEvent] = Field(default_factory=list)
    backfills: list[Backfill] = Field(default_factory=list)
    gate_log: list[GateRecord] = Field(default_factory=list)
    stage_progress: dict[str, dict[str, StepStatus]] = Field(default_factory=dict)

    # ---- 查询辅助 ----

    def stage(self, stage_id: str) -> Optional[Stage]:
        for s in self.stages:
            if s.id == stage_id:
                return s
        return None

    def deliverable(self, deliverable_id: str) -> Optional[Deliverable]:
        for d in self.deliverables:
            if d.id == deliverable_id:
                return d
        return None

    def require_stage(self, stage_id: str) -> Stage:
        s = self.stage(stage_id)
        if s is None:
            raise KeyError(stage_id)
        return s

    def open_backfills(self) -> list[Backfill]:
        return [b for b in self.backfills if b.status == "open"]

    def blocking_backfills(self) -> list[Backfill]:
        return [b for b in self.open_backfills() if b.blocks_acceptance]

    def versions(self) -> dict[str, int]:
        return {d.id: d.version for d in self.deliverables}

    def progress(self, stage_id: str) -> dict[str, StepStatus]:
        return self.stage_progress.setdefault(stage_id, {})

    def snapshot(self) -> dict[str, Any]:
        """用于测试与调试的浅快照。"""
        return {
            "current_stage": self.current_stage,
            "stages": {s.id: s.status for s in self.stages},
            "deliverables": {d.id: (d.version, d.status) for d in self.deliverables},
            "open_backfills": len(self.open_backfills()),
        }
