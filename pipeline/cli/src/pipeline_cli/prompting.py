"""Prompt 组装与上下文预算控制。

这是接真模型时最关键的一层。三个必须解决的问题：

1. **上下文爆炸**：`must_read` 可能是十几 KB 的 PRD，5 个阶段累积会撑爆窗口。
   → 保留文档骨架（全部标题），按比例截断各节正文，并显式标注省略。

2. **结构合规**：模型不知道 manifest 要求哪些章节。
   → 把 manifest 的必填章节/表格列翻译成「输出检查清单」写进 prompt。

3. **输出污染**：模型爱包裹 ```markdown 或加解释性前言，导致写盘内容不合法。
   → 明确要求「只输出文档本体」，并在写入前做剥离。

设计选择：**不引入 tokenizer 依赖**。用字符数近似（中文 1 字 ≈ 1 token，
英文 4 字符 ≈ 1 token），保守取上限即可，无需精确。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .agents import InvokeRequest
from .paths import Paths

# 中文为主的场景，1 字符 ≈ 1 token，故 60000 字符 ≈ 20k-30k token 上下
DEFAULT_MAX_TOTAL_CHARS = 60000
DEFAULT_MAX_PER_FILE_CHARS = 20000

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_OPEN = re.compile(r"^```[a-zA-Z]*\s*$")


@dataclass
class Prompt:
    system: str
    user: str
    notes: list[str] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return len(self.system) + len(self.user)


# ---------------------------------------------------------------------------
# 结构感知截断
# ---------------------------------------------------------------------------

def truncate_markdown(text: str, limit: int) -> tuple[str, bool]:
    """按 markdown 结构截断：保留全部标题，等比压缩各节正文。

    返回 (新文本, 是否发生截断)。
    比粗暴 `text[:limit]` 好得多：模型仍能看到完整目录结构，
    只是每节内容变短——这对「要写什么」的判断足够。
    """
    if len(text) <= limit:
        return text, False

    lines = text.splitlines()
    blocks: list[tuple[str | None, list[str]]] = []  # (标题行, 正文行)
    current_heading: str | None = None
    current_body: list[str] = []
    preamble: list[str] = []

    for line in lines:
        m = _HEADING.match(line)
        if m and len(m.group(1)) <= 2:
            if current_heading is None and current_body:
                preamble = current_body
            else:
                blocks.append((current_heading, current_body))
            current_heading = line
            current_body = []
        else:
            current_body.append(line)
    if current_heading is not None or current_body:
        blocks.append((current_heading, current_body))

    # 计算固定开销（标题 + 前导）
    fixed = sum(len(h) + 1 for h, _ in blocks if h) + sum(len(l) + 1 for l in preamble)
    body_budget = max(limit - fixed - 400, 500)  # 预留省略标记空间

    total_body = sum(len("\n".join(b)) for _, b in blocks) or 1
    ratio = min(1.0, body_budget / total_body)

    # 每节保底字符数：节数多时自动降低，避免保底把总预算撑爆
    n_blocks = max(len(blocks), 1)
    floor = max(20, min(120, body_budget // n_blocks // 2))

    out: list[str] = []
    if preamble:
        out.extend(preamble)

    for heading, body in blocks:
        if heading:
            out.append(heading)
        body_text = "\n".join(body)
        if not body_text.strip():
            out.extend(body)
            continue

        cap = max(int(len(body_text) * ratio), floor)
        if len(body_text) <= cap:
            out.extend(body)
        else:
            # 按行累积，但**单行超长时截断该行**而不是整行丢弃
            # （否则"一行 1000 字"的段落会让本节几乎全丢）
            kept: list[str] = []
            used = 0
            for line in body:
                if used >= cap:
                    break
                remaining = cap - used
                if len(line) + 1 <= remaining:
                    kept.append(line)
                    used += len(line) + 1
                else:
                    # 截断当前行，保留可读前缀
                    take = max(remaining - 24, 0)
                    if take > 0:
                        kept.append(line[:take] + "…（截断）")
                        used += take + 8
                    break
            omitted = len(body_text) - used
            out.extend(kept)
            if omitted > 80:
                out.append(f"\n> …（本节已省略约 {omitted} 字符，请按标题语义推断）\n")

    return "\n".join(out), True


# ---------------------------------------------------------------------------
# manifest → 输出检查清单
# ---------------------------------------------------------------------------

def manifest_checklist(paths: Paths, manifest_rel: str | None) -> str:
    """把 manifest 翻译成模型能读懂的硬性要求清单。

    这是提升「一次通过率」性价比最高的一步：模型不需要猜章节名与列名。
    """
    if not manifest_rel:
        return ""
    p = paths.resolve(manifest_rel)
    if not p.exists():
        return ""
    try:
        m = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ""

    lines: list[str] = []
    sections = m.get("sections") or []
    if sections:
        lines.append("### 必须包含的章节（二级标题，名称需可匹配）")
        for s in sections:
            title = s.get("title", s.get("id", "?"))
            required = s.get("required", True)
            mark = "" if required else "（可选）"
            stype = s.get("type", "text")
            extra = ""
            if stype == "table":
                cols = s.get("columns") or []
                if cols:
                    extra = "  表格列：" + " | ".join(str(c) for c in cols)
                min_rows = s.get("min_rows")
                if min_rows:
                    extra += f"  最少 {min_rows} 行数据"
                pattern = s.get("row_id_pattern")
                if pattern:
                    extra += f"  首列编号须匹配 {pattern}"
            elif stype == "list":
                mi = s.get("min_items")
                if mi:
                    extra += f"  至少 {mi} 个列表项"
            elif stype == "mermaid":
                extra += "  需 mermaid 代码块"
            elif stype == "code_block":
                lang = s.get("language")
                if lang:
                    extra += f"  需 {lang} 代码块"
            must = s.get("must_contain") or []
            if must:
                extra += "  正文须包含：" + "、".join(str(x) for x in must)
            lines.append(f"- **{title}**{mark}（{stype}）{extra}")

    rules = m.get("rules") or {}
    if rules.get("forbid_placeholder", True):
        lines.append("- 全文不得残留 `{{占位符}}`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------

_OUTPUT_RULES = """\
### 输出硬性要求
1. **只输出文档本体**（markdown 源码）。不要任何前言、后记、"以下是…"、也**不要用 ``` 代码块包裹全文**。
2. 章节标题使用 `##` 二级标题；名称需与上方的必填章节清单对应。
3. 表格使用标准 markdown 表格语法（含表头分隔行）。
4. 不得残留 `{{占位符}}`；不确定的内容写"待确认"，但不要编造数据。
5. 内容必须与本任务的材料一致，不得引入材料中不存在的需求。
"""


def build_prompt(
    request: InvokeRequest,
    paths: Paths,
    *,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
    max_per_file_chars: int = DEFAULT_MAX_PER_FILE_CHARS,
) -> Prompt:
    notes: list[str] = []

    # ---- system：角色契约 ----
    system_parts: list[str] = []
    if request.agent_definition:
        p = paths.resolve(request.agent_definition)
        if p.exists():
            system_parts.append(p.read_text(encoding="utf-8"))
        else:
            notes.append(f"未找到 Agent 定义: {request.agent_definition}")

    system_parts.append(
        f"\n你现在以 **{request.agent}** 身份工作。"
        "严格遵守上面的职责边界、红线与输出要求。"
        "\n\n工作纪律：\n"
        "- 只依据下方提供的材料作答，不臆造事实\n"
        "- 若材料不足，在对应位置写「待确认：<具体缺什么>」，不要编造\n"
        "- 遵守「明确不做」清单，不得扩张范围\n"
    )
    system = "\n\n".join(system_parts)

    # ---- user：任务 + 材料 + 约束 ----
    user_parts: list[str] = [f"# 任务\n{request.task}\n"]

    checklist = manifest_checklist(paths, request.output_manifest)
    if checklist:
        user_parts.append(f"# 输出结构要求（务必逐项满足）\n{checklist}\n")

    if request.focus:
        user_parts.append(
            "# 本次重点关注\n" + "\n".join(f"- {f}" for f in request.focus) + "\n"
        )
    if request.constraints:
        user_parts.append(
            "# 额外约束\n" + "\n".join(f"- {c}" for c in request.constraints) + "\n"
        )

    # ---- 材料（带预算控制）----
    if request.must_read:
        # 先按单文件上限截断，再检查总量
        budget_per_file = max_per_file_chars
        materials: list[tuple[str, str, int]] = []  # (path, content, original_len)
        for rel in request.must_read:
            p = paths.resolve(rel)
            if not p.exists():
                notes.append(f"材料缺失，已跳过: {rel}")
                continue
            raw = p.read_text(encoding="utf-8")
            content, truncated = truncate_markdown(raw, budget_per_file)
            if truncated:
                notes.append(
                    f"材料已截断: {rel}（{len(raw)} → {len(content)} 字符）"
                )
            materials.append((rel, content, len(raw)))

        total = sum(len(c) for _, c, _ in materials)
        if total > max_total_chars and materials:
            # 总量超限：按比例再压一轮
            ratio = max_total_chars / total
            compressed: list[tuple[str, str, int]] = []
            for rel, content, orig in materials:
                new_cap = max(int(len(content) * ratio), 800)
                new_content, _ = truncate_markdown(content, new_cap)
                compressed.append((rel, new_content, orig))
            materials = compressed
            notes.append(
                f"上下文总长 {total} 超预算 {max_total_chars}，已按比例压缩 {len(materials)} 份材料"
            )

        blocks = ["# 必读材料"]
        for rel, content, orig in materials:
            blocks.append(f"\n## 材料：{rel}（原文 {orig} 字符）\n\n{content}")
        user_parts.append("\n".join(blocks) + "\n")

    user_parts.append(_OUTPUT_RULES)
    user = "\n".join(user_parts)

    return Prompt(system=system, user=user, notes=notes)


# ---------------------------------------------------------------------------
# 输出清洗
# ---------------------------------------------------------------------------

_FENCE_WRAP = re.compile(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", re.DOTALL)


def clean_output(text: str) -> tuple[str, list[str]]:
    """剥离模型常见的输出污染。返回 (干净文本, 处理说明)。"""
    notes: list[str] = []
    out = text.strip()

    m = _FENCE_WRAP.match(out)
    if m:
        out = m.group(1).strip()
        notes.append("已剥离外层 ``` 代码块")

    # 去掉常见的客套前言（仅当出现在文档标题之前）
    leading = re.match(
        r"^(?:好的|当然|以下是|下面是|根据.{0,20}要求)[^\n]{0,60}\n+", out
    )
    if leading and not out.lstrip().startswith("#"):
        out = out[leading.end():].lstrip()
        notes.append("已剥离前置说明")

    return out, notes


# ---------------------------------------------------------------------------
# 修复提示（校验失败时二次生成）
# ---------------------------------------------------------------------------

def build_repair_prompt(previous: str, violations: list[str], *, max_show: int = 20) -> str:
    """把 manifest 校验失败项反馈给模型，要求最小改动修复。"""
    shown = violations[:max_show]
    lines = [
        "# 上一步输出未通过结构校验，请修复",
        "",
        "## 校验失败项",
        *[f"- {v}" for v in shown],
    ]
    if len(violations) > max_show:
        lines.append(f"- ……另有 {len(violations) - max_show} 项未列出")
    lines += [
        "",
        "## 修复要求",
        "1. **最小改动**：只修上面列出的问题，已正确的内容保持原样",
        "2. 缺失章节 → 补上该 `##` 章节并写实质内容",
        "3. 缺列/列名不符 → 修正表头为要求的列名",
        "4. 残留占位符 → 换成具体内容（不确定就写「待确认：…」）",
        "5. 直接输出修复后的**完整文档**（不要只输出 diff，也不要包裹代码块）",
        "",
        "## 上一版输出（供参考）",
        previous,
    ]
    return "\n".join(lines)
