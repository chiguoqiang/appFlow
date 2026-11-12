"""SOP 加载与目录。

SOP 是可版本化的数据（YAML），调度器只解释它、不硬编码流程。
本模块负责：加载、基础校验、索引、流程路径计算。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal

import yaml

from .errors import SopNotFound
from .paths import Paths

ActionType = Literal[
    "validate_inputs",
    "invoke_agent",
    "validate_deliverable",
    "check_rules",
    "collect_human_input",
    "human_gate",
    "register_backfill",
]

_ACTIONS: set[str] = {
    "validate_inputs",
    "invoke_agent",
    "validate_deliverable",
    "check_rules",
    "collect_human_input",
    "human_gate",
    "register_backfill",
}


@dataclass(frozen=True)
class Step:
    id: str
    action: str
    description: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    on_fail: str = "abort"
    skip_if: str | None = None
    backfill: dict[str, Any] | None = None

    def param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


@dataclass(frozen=True)
class GateSpec:
    enabled: bool
    title: str
    actions: list[str]
    review_package: list[str]
    require_comment_on: list[str]


@dataclass(frozen=True)
class Transition:
    deliverable_status: str | None
    next_sop: str | None
    propagate_stale: list[str]
    reopen_sop: str | None
    increment_version: bool
    require_structured_opinion: bool


@dataclass(frozen=True)
class Sop:
    id: str
    stage: str
    name: str
    flow: str
    owner_agent: str
    description: str
    depends_on: list[str]
    inputs: list[dict[str, Any]]
    output: dict[str, Any]
    steps: list[Step]
    gate: GateSpec
    on_approve: Transition
    on_revise: Transition
    on_reject: Transition
    dod: list[str]
    source_path: Path

    @property
    def output_deliverable(self) -> str | None:
        return self.output.get("deliverable")

    @property
    def output_path(self) -> str | None:
        return self.output.get("path")

    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(step_id)

    def gate_step(self) -> Step | None:
        for s in self.steps:
            if s.action == "human_gate":
                return s
        return None


def _transition(raw: dict[str, Any] | None) -> Transition:
    raw = raw or {}
    return Transition(
        deliverable_status=raw.get("deliverable_status"),
        next_sop=raw.get("next_sop"),
        propagate_stale=list(raw.get("propagate_stale") or []),
        reopen_sop=raw.get("reopen_sop"),
        increment_version=bool(raw.get("increment_version", False)),
        require_structured_opinion=bool(raw.get("require_structured_opinion", False)),
    )


def _gate(raw: dict[str, Any] | None) -> GateSpec:
    raw = raw or {}
    return GateSpec(
        enabled=bool(raw.get("enabled", False)),
        title=str(raw.get("title", "")),
        actions=list(raw.get("actions") or []),
        review_package=list(raw.get("review_package") or []),
        require_comment_on=list(raw.get("require_comment_on") or []),
    )


def _step(raw: dict[str, Any]) -> Step:
    action = str(raw["action"])
    if action not in _ACTIONS:
        raise ValueError(f"未知动作类型: {action}（允许：{sorted(_ACTIONS)}）")
    return Step(
        id=str(raw["id"]),
        action=action,
        description=str(raw.get("description") or ""),
        params=dict(raw.get("params") or {}),
        on_fail=str(raw.get("on_fail") or "abort"),
        skip_if=raw.get("skip_if"),
        backfill=raw.get("backfill"),
    )


class SopCatalog:
    """全部 SOP 的索引与流程计算。"""

    def __init__(self, sops: list[Sop], root: Path) -> None:
        self._by_id: dict[str, Sop] = {s.id: s for s in sops}
        self._by_stage: dict[str, Sop] = {s.stage: s for s in sops if s.stage not in {"intake"}}
        # intake 阶段存在多个（分流 / 需求录入），单独索引
        self._by_id_flow: dict[tuple[str, str], Sop] = {(s.id, s.flow): s for s in sops}
        self.root = root

    # ---------- 查询 ----------

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self) -> Iterator[Sop]:
        return iter(self._by_id.values())

    def get(self, sop_id: str) -> Sop:
        sop = self._by_id.get(sop_id)
        if sop is None:
            raise SopNotFound(
                f"SOP 不存在: {sop_id}",
                hint=f"可用 SOP: {', '.join(sorted(self._by_id))}",
            )
        return sop

    def by_stage(self, stage_id: str) -> Sop:
        """按阶段 id 取 SOP。注意 intake 阶段有多个，需用 get()。"""
        sop = self._by_stage.get(stage_id)
        if sop is None:
            raise SopNotFound(
                f"阶段未定义 SOP: {stage_id}",
                hint=f"可用阶段: {', '.join(sorted(self._by_stage))}",
            )
        return sop

    def ids(self) -> list[str]:
        return sorted(self._by_id)

    def for_flow(self, flow: str) -> list[Sop]:
        return sorted(
            (s for s in self._by_id.values() if s.flow == flow),
            key=lambda s: s.id,
        )

    # ---------- 流程 ----------

    def first_sop(self, flow: str) -> Sop:
        if flow == "new_requirement":
            return self.get("intake-routing")
        return self.get("00-brief")

    def next_after(self, sop: Sop, *, answers: dict[str, Any] | None = None) -> str | None:
        """按 on_approve.next_sop 计算下一 SOP。

        支持三种特殊值：
        - ``__ROUTE__``                       依据分流结果选择新项目/增量首 SOP
        - ``__IF_NEEDS_PAGES_THEN_12a_ELSE_12b__`` 依据是否涉及新页面分支
        - ``null``                            流程终点
        """
        nxt = sop.on_approve.next_sop
        if nxt is None:
            return None
        answers = answers or {}
        if nxt == "__ROUTE__":
            flow = answers.get("flow", "new_project")
            if flow == "new_requirement":
                return "10-requirement-intake"
            return "00-brief"
        if nxt == "__IF_NEEDS_PAGES_THEN_12a_ELSE_12b__":
            needs = answers.get("needs_new_pages", True)
            return "12a-design-delta" if needs else "12b-development-delta"
        return nxt


def load_sops(paths: Paths) -> SopCatalog:
    schema_path = paths.sops / "_schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8")) if schema_path.exists() else None

    try:
        import jsonschema  # type: ignore
    except ImportError:  # pragma: no cover
        jsonschema = None  # type: ignore

    sops: list[Sop] = []
    errors: list[str] = []

    for path in sorted(paths.sops.rglob("*.sop.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"{path.name}: YAML 解析失败 — {exc}")
            continue
        if not isinstance(raw, dict):
            errors.append(f"{path.name}: 根节点不是映射")
            continue

        if schema is not None and jsonschema is not None:
            try:
                jsonschema.validate(raw, schema)
            except jsonschema.ValidationError as exc:  # type: ignore[attr-defined]
                loc = "/".join(str(p) for p in exc.absolute_path) or "<root>"
                errors.append(f"{path.name}: schema 校验失败 @ {loc} — {exc.message}")
                continue

        try:
            sops.append(
                Sop(
                    id=str(raw["sop"]),
                    stage=str(raw["stage"]),
                    name=str(raw["name"]),
                    flow=str(raw.get("flow") or "new_project"),
                    owner_agent=str(raw.get("owner_agent") or "user"),
                    description=str(raw.get("description") or "").strip(),
                    depends_on=list(raw.get("depends_on") or []),
                    inputs=list(raw.get("inputs") or []),
                    output=dict(raw.get("output") or {}),
                    steps=[_step(s) for s in raw.get("steps") or []],
                    gate=_gate(raw.get("gate")),
                    on_approve=_transition(raw.get("on_approve")),
                    on_revise=_transition(raw.get("on_revise")),
                    on_reject=_transition(raw.get("on_reject")),
                    dod=list(raw.get("dod") or []),
                    source_path=path,
                )
            )
        except (KeyError, ValueError) as exc:
            errors.append(f"{path.name}: 结构非法 — {exc}")

    if errors:
        raise SopNotFound("SOP 加载失败:\n  - " + "\n  - ".join(errors))

    return SopCatalog(sops, paths.root)
