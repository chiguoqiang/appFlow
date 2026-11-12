"""Agent 调用层。

M2 只实现 **MockInvoker**：按 manifest 生成结构合法的占位交付物。
它的价值不是"假装很聪明"，而是让**调度器骨架可端到端测试**——
不依赖 LLM 的不确定性，也能验证：SOP 步骤顺序、输入校验、
manifest 校验、规则引擎、关卡暂停、状态流转。

M3 会加 `HeadlessInvoker`（Claude Code headless），接口不变。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import yaml


@dataclass
class InvokeRequest:
    agent: str
    task: str
    output_path: Path
    output_manifest: str | None
    must_read: list[str] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    agent_definition: str | None = None
    timeout_sec: int = 600


@dataclass
class InvokeResult:
    content: str
    agent: str
    tokens_used: int = 0
    notes: list[str] = field(default_factory=list)


class AgentInvoker(Protocol):
    def invoke(self, request: InvokeRequest, *, paths: Any) -> InvokeResult: ...


# ---------------------------------------------------------------------------
# Mock 生成器
# ---------------------------------------------------------------------------

# 列名 → 示例值（关键：避开 manifest 的 forbid_column_values 与规则引擎的触发词）
_COLUMN_VALUES: dict[str, str] = {
    "优先级": "P0",
    "状态": "✅ 完成",
    "严重度": "低",
    "结果": "✅ 通过",
    "关联": "US-1",
    "关联功能": "F-1",
    "关联故事": "US-1",
    "关联用例": "TC-01",
    "关联变更项": "D-1",
    "关联需求": "US-1",
    "验证方式": "单元测试断言",
    "是否回归": "是",
    "必须回归": "是",
    "是否覆盖": "是",
    "是否需新增": "否",
    "影响类型": "新增",
    "变更类型": "新增",
    "核对结果": "✅",
    "判定": "✅",
    "达标": "✅",
    "偏差与理由": "完整还原，无偏差",
    "还原状态": "✅ 完整还原",
    "实现证据": "lib/pages/home_page.dart",
    "测试证据": "TC-01 ✅",
    "证据": "见 TC-01 执行记录",
    "说明": "见实现与用例",
    "备注": "无",
    "版本": "v1",
    "类型": "功能",
    "入口": "首页",
    "页面": "PG-01",
    "页面名": "首页",
    "页面 ID": "PG-01",
    "Token": "color.primary",
    "值": "#4F6BED",
    "用途": "主操作色",
    "约束项": "平台",
    "要求": "Flutter",
    "类别": "性能",
    "指标": "冷启动 < 2s",
    "字段": "项目代号",
    "动作": "通过",
    "决策": "采用最小实现",
    "理由": "控制范围",
    "提出方": "planner",
    "日期": "2026-11-12",
    "阶段": "规划",
    "轮次": "1",
    "Figma 生成时间": "2026-11-12 10:00",
    "校验结果": "通过",
    "缺陷与处理": "无缺陷",
    "缺陷": "无",
    "复现步骤": "不适用",
    "问题": "无",
    "问题/风险": "无",
    "处理建议": "持续观察",
    "影响": "无",
    "建议处理时机": "下个迭代",
    "来源": "测试",
    "原用例编号": "TC-01",
    "受影响功能": "F-1 打卡",
    "影响程度": "低",
    "影响说明": "仅涉及展示层",
    "设计稿": "design/screenshots/PG-01.png",
    "运行时截图": "test/screenshots/PG-01-runtime.png",
    "差异": "无可见差异",
    "自测报告声明": "自测全部通过",
    "验证结果": "复核一致",
    "边界场景": "空数据",
    "用例": "打开首页可见列表",
    "步骤": "启动 App",
    "预期": "展示列表",
    "实际": "展示列表",
    "前置条件": "无",
    "目标项目": "demo-habit",
    "需求编号": "REQ-001",
    "MVP 功能": "打卡",
    "简报功能": "打卡",
    "测试要点": "打卡幂等",
    "功能": "打卡",
    "任务": "实现打卡",
    "改动点": "新增归档按钮",
    "改动文件": "lib/pages/home_page.dart",
    "测试文件": "test/widget/home_page_test.dart",
    "新增用例": "2",
    "修改用例": "0",
    "修改理由": "无",
    "改动前": "65 passed",
    "改动后": "67 passed",
    "关闭条件": "截图齐备",
    "回填项": "设计基线",
    "责任人": "designer",
    "是否影响判定": "否",
    "既有功能编号": "F-1",
    "功能名": "打卡",
    "是否影响": "否",
    "不覆盖的理由": "无",
    "变更项": "新增归档",
    "变更项编号": "D-1",
    "涉及文件": "lib/pages/home_page.dart",
    "验收标准": "点击归档后列表移除该项",
    "用户故事": "作为用户我想归档习惯",
    "详细描述": "按需求实现",
    "数据需求": "复用现有模型",
    "主要元素": "列表与按钮",
    "跳转关系": "无",
    "功能名": "打卡",
    "规范": "见设计系统",
    "组件": "AppCard",
    "入口/出口": "首页",
}

# 编号列（首列）示例值：按 row_id_pattern 前缀决定
_ID_SAMPLES: dict[str, str] = {
    "US": "US-1",
    "F": "F-1",
    "PG": "PG-01",
    "T": "T-01",
    "TS": "TS-1",
    "TC": "TC-01",
    "TCN": "TCN-01",
    "TCR": "TCR-01",
    "D": "D-1",
    "BF": "BF-001",
    "A": "A-1",
    "K": "K-1",
    "L": "L-1",
}


def _id_for(pattern: str | None, index: int = 1) -> str | None:
    if not pattern:
        return None
    m = re.search(r"([A-Z]+)-", pattern)
    if not m:
        return None
    prefix = m.group(1)
    base = _ID_SAMPLES.get(prefix, f"{prefix}-1")
    if index > 1:
        # 递增编号
        num = re.sub(r"^[A-Z]+-", "", base)
        try:
            width = len(num)
            base = f"{prefix}-{str(int(num) + index - 1).zfill(width)}"
        except ValueError:
            base = f"{prefix}-{index}"
    return base


def _cell(header: str, row_index: int) -> str:
    """按列名给出示例值（避开 manifest/规则的禁用值）。"""
    if header in _COLUMN_VALUES:
        return _COLUMN_VALUES[header]
    if "路径" in header:
        return "pipeline/projects/demo/01-prd.md"
    if "编号" in header:
        return "TC-01"
    if "时间" in header or "日期" in header:
        return "2026-11-12"
    return "示例值"


def _id_for_for_row(base: str, row_index: int) -> str:
    if row_index == 1:
        return base
    m = re.match(r"^([A-Z]+)-(.*)$", base)
    if not m:
        return base
    prefix, num = m.group(1), m.group(2)
    try:
        width = len(num)
        return f"{prefix}-{str(int(num) + row_index - 1).zfill(width)}"
    except ValueError:
        return f"{base}-{row_index}"


def _text_body(spec: dict[str, Any]) -> str:
    """生成满足 must_contain 与 min_length 的正文。"""
    must = [str(x) for x in spec.get("must_contain") or []]
    title = str(spec.get("title", ""))
    sentences: list[str] = []
    if must:
        for needle in must:
            sentences.append(f"- **{needle}**：按契约要求给出定义与说明。")
    else:
        sentences.append(f"本节说明「{title}」的内容。")
        sentences.append("说明包含定义、边界与验证方式。")
    body = "\n".join(sentences)
    min_len = int(spec.get("min_length") or 0)
    if len(body) < min_len:
        body += "\n\n补充说明：" + "按需求与契约执行，逐项可验证。" * 3
    return body


def generate_deliverable(manifest: dict[str, Any], *, context: dict[str, Any] | None = None) -> str:
    """按 manifest 生成结构合法的 markdown 交付物。"""
    context = context or {}
    lines: list[str] = []
    title = context.get("title") or manifest.get("deliverable", "交付物")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"> 由 MockAgent 生成（M2 骨架验证用）。task: {context.get('task', '-')}"
    )
    lines.append("")

    for spec in manifest.get("sections") or []:
        sec_title = str(spec.get("title", spec.get("id", "章节")))
        stype = str(spec.get("type", "text"))
        required = bool(spec.get("required", True))
        if not required and stype == "text" and "stats" not in str(spec.get("id")):
            # 可选章节默认也生成（例如统计口径，DR-01 需要）
            pass
        lines.append(f"## {sec_title}")
        lines.append("")

        if stype == "table":
            headers = [str(c) for c in spec.get("columns") or []]
            if not headers:
                lines.append("（无内容）")
                lines.append("")
                continue
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join(["---"] * len(headers)) + "|")

            # 关键：key-value 型表格（如「元数据」）按 must_contain 逐项生成行，
            # 否则 manifest 的 must_contain 校验必然失败。
            must = [str(x) for x in spec.get("must_contain") or []]
            is_kv_table = _looks_like_kv_table(headers)
            if must and is_kv_table:
                for needle in must:
                    row_cells = [needle] + [
                        _kv_value(h) for h in headers[1:]
                    ]
                    lines.append("| " + " | ".join(row_cells) + " |")
                lines.append("")
                continue

            min_rows = int(spec.get("min_rows") or 0)
            # 边界用例等需要更多行；默认至少 1 行（若 min_rows=0 则允许空表）
            row_count = max(min_rows, 1) if min_rows or _needs_row(spec) else 0
            pattern = spec.get("row_id_pattern")
            base_id = _id_for(str(pattern)) if pattern else None
            for i in range(1, row_count + 1):
                row_cells: list[str] = []
                for idx, h in enumerate(headers):
                    if idx == 0 and base_id:
                        row_cells.append(_id_for_for_row(base_id, i))
                    else:
                        row_cells.append(_cell(h, i))
                lines.append("| " + " | ".join(row_cells) + " |")
            lines.append("")

        elif stype == "list":
            min_items = int(spec.get("min_items") or 1)
            for i in range(1, min_items + 1):
                lines.append(f"- 第 {i} 项：按契约要求落实。")
            lines.append("")

        elif stype == "mermaid":
            lines.append("```mermaid")
            lines.append("flowchart LR")
            lines.append("    A[PG-01] --> B[PG-02]")
            lines.append("```")
            lines.append("")

        elif stype == "code_block":
            lang = str(spec.get("language") or "")
            if lang == "json":
                payload = {
                    "color": {"primary": "#4F6BED", "surface": "#FFFFFF"},
                    "spacing": {"s": 8, "m": 16},
                }
                lines.append("```json")
                lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
                lines.append("```")
            else:
                lines.append("```")
                lines.append("示例内容")
                lines.append("```")
            lines.append("")

        else:  # text
            lines.append(_text_body(spec))
            lines.append("")

    # 必备结尾：决策记录通常已在 manifest 中；这里不强加
    return "\n".join(lines).rstrip() + "\n"


def _needs_row(spec: dict[str, Any]) -> bool:
    """有些表格允许为空（如缺陷清单）。根据语义判断。"""
    sid = str(spec.get("id", ""))
    allow_empty = {"defects", "known-issues", "new-tokens", "leftover"}
    return sid not in allow_empty


def _looks_like_kv_table(headers: list[str]) -> bool:
    """判断是否为 key-value 形态的表格（第一列是字段名）。

    元数据 / 技术约束 / 全局规范 等都属于这一类：
    这类表的行不是"数据记录"，而是"字段声明"，应由 must_contain 驱动生成。
    """
    if len(headers) < 2:
        return False
    first = headers[0].strip()
    return first in {"字段", "约束项", "项", "Token", "类别", "指标", "检查项", "规则", "名称"}


def _kv_value(header: str) -> str:
    """key-value 表的值列：给出合理示例值。"""
    h = header.strip()
    if h in _COLUMN_VALUES:
        return _COLUMN_VALUES[h]
    if "版本" in h:
        return "v1"
    if "状态" in h:
        return "draft"
    if "日期" in h or "时间" in h:
        return "2026-11-12"
    if "代号" in h or "名称" in h:
        return "demo"
    return "示例值"


class MockInvoker:
    """按 manifest 生成占位交付物的 Agent 实现。"""

    def __init__(self, *, title: str | None = None) -> None:
        self._title = title

    def invoke(self, request: InvokeRequest, *, paths: Any) -> InvokeResult:
        manifest: dict[str, Any] = {}
        if request.output_manifest:
            p = paths.resolve(request.output_manifest)
            if p.exists():
                manifest = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        notes = [
            f"mock 生成，未实际读取 {len(request.must_read)} 个上下文文件",
        ]
        content = generate_deliverable(
            manifest,
            context={"task": request.task, "title": self._title},
        )
        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_text(content, encoding="utf-8")
        return InvokeResult(
            content=content,
            agent=request.agent,
            tokens_used=len(content) // 4,
            notes=notes,
        )
