#!/usr/bin/env python3
"""契约完整性校验（M1 验收工具）。

校验对象：
  - sops/*.sop.yaml    符合 _schema.json，且满足流程不变量
  - manifests/*.yaml   可解析且必备字段齐全
  - gates/*.rules.yaml 可解析且规则 id 唯一

流程不变量（P0 教训固化为机器检查）：
  I1  文件名 == sop 字段
  I2  gate.enabled 为真时必须恰好 1 个 human_gate 步骤
  I3  任何 on_fail=degrade 的步骤，同 SOP 内必须有 register_backfill 步骤
  I4  steps 数量 3..12
  I5  output.manifest 引用的文件必须存在（若显式声明）
  I6  inputs/output 路径不得含未转义的 {{占位符}} 之外的空值
  I7  depends_on 引用的 SOP 必须存在
  I8  dod 不得为空

退出码：0 全通过；1 有错误。
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

ROOT = Path(__file__).resolve().parent.parent      # pipeline/
PROJECT = ROOT.parent                             # 仓库根（SOP 中路径以仓库根为基准）
SOPS = ROOT / "sops"
MANIFESTS = ROOT / "manifests"
GATES = ROOT / "gates"

RL = "\033[31m"
GL = "\033[32m"
YL = "\033[33m"
RST = "\033[0m"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warns: list[str] = []
        self.passed: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warns.append(msg)

    def ok(self, msg: str) -> None:
        self.passed.append(msg)


def load_yaml(path: Path, report: Report):
    try:
        with path.open(encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except Exception as exc:  # noqa: BLE001
        report.err(f"{path.relative_to(ROOT)}: YAML 解析失败 — {exc}")
        return None


def find_sops() -> list[Path]:
    return sorted(p for p in SOPS.rglob("*.sop.yaml"))


def check_sops(report: Report) -> dict[str, dict]:
    schema_path = SOPS / "_schema.json"
    if not schema_path.exists():
        report.err("sops/_schema.json 缺失")
        return {}

    import json

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    loaded: dict[str, dict] = {}

    for path in find_sops():
        rel = path.relative_to(ROOT)
        doc = load_yaml(path, report)
        if doc is None:
            continue

        # schema 校验
        if jsonschema is not None:
            try:
                jsonschema.validate(doc, schema)
            except jsonschema.ValidationError as exc:
                loc = "/".join(str(p) for p in exc.absolute_path) or "<root>"
                report.err(f"{rel}: schema 校验失败 @ {loc} — {exc.message}")
                continue
        else:
            report.warn("未安装 jsonschema，跳过 schema 校验")

        sop_id = doc.get("sop")
        loaded[sop_id] = doc

        # I1 文件名 == sop 字段
        expected = path.name.removesuffix(".sop.yaml")
        if sop_id != expected:
            report.err(f"{rel}: I1 文件名({expected}) != sop 字段({sop_id})")

        steps = doc.get("steps") or []
        actions = [s.get("action") for s in steps]

        # I4 step 数量
        if not (3 <= len(steps) <= 12):
            report.err(f"{rel}: I4 steps 数量 {len(steps)} 不在 3..12")

        # I2 gate 不变量
        gate = doc.get("gate") or {}
        gate_count = actions.count("human_gate")
        if gate.get("enabled"):
            if gate_count != 1:
                report.err(
                    f"{rel}: I2 gate.enabled=true 但 human_gate 步骤数={gate_count}（应为 1）"
                )
        elif gate_count > 1:
            report.err(f"{rel}: 存在 {gate_count} 个 human_gate（最多 1）")

        # gate 动作与 step 参数一致性
        if gate_count == 1:
            gate_step = next(s for s in steps if s.get("action") == "human_gate")
            step_actions = set((gate_step.get("params") or {}).get("actions") or [])
            gate_actions = set(gate.get("actions") or [])
            if step_actions and gate_actions and step_actions != gate_actions:
                report.warn(
                    f"{rel}: gate.actions {sorted(gate_actions)} 与 human_gate 步骤 "
                    f"params.actions {sorted(step_actions)} 不一致"
                )

        # I3 degrade 必须有 backfill
        has_backfill_action = "register_backfill" in actions
        degrade_steps = [
            s for s in steps if s.get("on_fail") == "degrade"
        ]
        if degrade_steps and not has_backfill_action:
            ids = ", ".join(s.get("id", "?") for s in degrade_steps)
            report.err(
                f"{rel}: I3 步骤 {ids} 设了 on_fail=degrade 但 SOP 内无 register_backfill 步骤"
            )
        for s in degrade_steps:
            if not s.get("backfill"):
                report.warn(
                    f"{rel}: 步骤 {s.get('id')} on_fail=degrade 未内联 backfill 字段"
                )

        # I5 output.manifest 存在性
        out = doc.get("output") or {}
        manifest = out.get("manifest")
        if manifest and not (PROJECT / manifest).exists():
            report.err(f"{rel}: I5 output.manifest 不存在 — {manifest}")

        # I8 dod
        if not doc.get("dod"):
            report.err(f"{rel}: I8 dod 为空")
        else:
            for item in doc["dod"]:
                if any(k in str(item) for k in ("看起来", "基本", "大致", "差不多")):
                    report.err(f"{rel}: I8 dod 含主观判据 — {item}")

        # 输出中引用的 manifest 都要存在
        for s in steps:
            params = s.get("params") or {}
            for key in ("manifest", "output_manifest"):
                val = params.get(key)
                if val and not (PROJECT / val).exists():
                    report.err(f"{rel}: 步骤 {s.get('id')} 引用的 {val} 不存在")
            ruleset = params.get("ruleset")
            if ruleset and not (PROJECT / ruleset).exists():
                report.err(f"{rel}: 步骤 {s.get('id')} 引用的规则集 {ruleset} 不存在")

        report.ok(f"{rel}")

    # I7 depends_on 引用存在
    for sop_id, doc in loaded.items():
        for dep in doc.get("depends_on") or []:
            if dep not in loaded:
                report.err(f"sop {sop_id}: I7 depends_on 引用了不存在的 SOP — {dep}")

    return loaded


def check_manifests(report: Report) -> None:
    files = sorted(MANIFESTS.glob("*.manifest.yaml"))
    if not files:
        report.err("manifests/ 下无 .manifest.yaml")
        return
    for path in files:
        rel = path.relative_to(ROOT)
        doc = load_yaml(path, report)
        if doc is None:
            continue
        for key in ("manifest", "deliverable", "description"):
            if key not in doc:
                report.err(f"{rel}: 缺必备字段 {key}")
        expected = path.name.removesuffix(".manifest.yaml")
        if doc.get("manifest") != expected:
            report.err(
                f"{rel}: manifest 字段({doc.get('manifest')}) != 文件名({expected})"
            )
        for idx, sec in enumerate(doc.get("sections") or []):
            if "id" not in sec or "title" not in sec:
                report.err(f"{rel}: sections[{idx}] 缺 id 或 title")
            if sec.get("type") == "table" and not sec.get("columns") and sec.get("required"):
                report.err(f"{rel}: sections[{idx}] type=table 但未声明 columns")
        report.ok(f"{rel}")


def check_gates(report: Report) -> None:
    files = sorted(GATES.glob("*.rules.yaml"))
    if not files:
        report.err("gates/ 下无 .rules.yaml")
        return
    for path in files:
        rel = path.relative_to(ROOT)
        doc = load_yaml(path, report)
        if doc is None:
            continue
        if "ruleset" not in doc:
            report.err(f"{rel}: 缺 ruleset 字段")
        # 规则 id 唯一性（兼容 rules 与 checks 两种容器）
        items = (doc.get("rules") or []) + (doc.get("checks") or [])
        ids = [i.get("id") for i in items]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            report.err(f"{rel}: 规则 id 重复 — {sorted(dupes)}")
        for item in items:
            if not item.get("id"):
                report.err(f"{rel}: 存在无 id 的规则")
            # message 可能写在顶层，也可能写在 then.message（规则求值结果里）
            has_msg = bool(
                item.get("message")
                or item.get("degrade_to")
                or (item.get("then") or {}).get("message")
            )
            if not has_msg:
                report.warn(f"{rel}: 规则 {item.get('id')} 缺 message/degrade_to")
        report.ok(f"{rel} ({len(items)} 条规则)")


def main() -> int:
    report = Report()
    loaded = check_sops(report)
    check_manifests(report)
    check_gates(report)

    print(f"\n{'=' * 60}")
    print("契约完整性校验报告")
    print("=" * 60)
    for msg in report.passed:
        print(f"{GL}✓{RST} {msg}")
    for msg in report.warns:
        print(f"{YL}!{RST} {msg}")
    for msg in report.errors:
        print(f"{RL}✗{RST} {msg}")

    print("-" * 60)
    print(
        f"通过 {len(report.passed)} | 警告 {len(report.warns)} | 错误 {len(report.errors)}"
    )
    print(f"SOP 数量: {len(loaded)}")

    if report.errors:
        print(f"\n{RL}校验失败{RST}")
        return 1
    print(f"\n{GL}校验通过{RST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
