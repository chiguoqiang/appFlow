"""交付物校验与规则求值。

分两层（对应 M1 的契约设计）：

1. **manifest 校验**（`validate_manifest`）——查"有没有"：章节、表格列、编号格式、行数下限。
2. **规则求值**（`evaluate_ruleset`）——查"写了但写错了"：口径缺失、断言无证明、模糊表述等。

未实现的规则种类会显式标记为 `skipped` 并给出原因，**绝不静默通过**。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .errors import ManifestError, RulesetError
from .paths import Paths

# ---------------------------------------------------------------------------
# Markdown 解析
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_LEADING_NUM = re.compile(r"^\s*(\d+(?:\.\d+)*)[.、)]?\s*")
_PAREN = re.compile(r"[（(][^）)]*[）)]")
_FILLER = re.compile(r"[\s与和的、·•\-—_：:，,。.；;\"'`]")
_FENCE = re.compile(r"^```(\w*)\s*$")


def norm_title(text: str) -> str:
    """标题归一化：去编号、去括号内容、去填充词。"""
    t = _LEADING_NUM.sub("", text.strip())
    t = _PAREN.sub("", t)
    t = _FILLER.sub("", t)
    return t.lower()


def _subsequence(needle: str, haystack: str) -> bool:
    it = iter(haystack)
    return all(ch in it for ch in needle)


@dataclass
class Table:
    headers: list[str]
    rows: list[dict[str, str]]

    def column(self, name: str) -> list[str]:
        """取某列全部值；列名按归一化匹配，容忍空格差异。"""
        target = norm_title(name)
        key = None
        for h in self.headers:
            if norm_title(h) == target:
                key = h
                break
        if key is None:
            return []
        return [r.get(key, "") for r in self.rows]

    def has_column(self, name: str) -> bool:
        target = norm_title(name)
        return any(norm_title(h) == target for h in self.headers)

    def count_where(self, column: str, equals: str) -> int:
        return sum(1 for v in self.column(column) if v.strip() == equals)

    def count_empty(self, column: str, empties: Iterable[str]) -> int:
        allowed = {e.strip() for e in empties}
        n = 0
        for v in self.column(column):
            v = v.strip()
            # 去掉 markdown 强调与 emoji 之外的比较噪声
            bare = v.strip("*` ")
            if bare == "" or bare in allowed:
                n += 1
        return n


@dataclass
class Section:
    title: str
    level: int
    lines: list[str] = field(default_factory=list)

    @property
    def body(self) -> str:
        return "\n".join(self.lines)

    @property
    def norm(self) -> str:
        return norm_title(self.title)

    # ---- 内容形态 ----

    def tables(self) -> list[Table]:
        tables: list[Table] = []
        buf: list[str] = []
        for line in self.lines:
            if line.strip().startswith("|"):
                buf.append(line)
            else:
                if buf:
                    t = _parse_table(buf)
                    if t:
                        tables.append(t)
                    buf = []
        if buf:
            t = _parse_table(buf)
            if t:
                tables.append(t)
        return tables

    def table(self) -> Table | None:
        tables = self.tables()
        return tables[0] if tables else None

    def bullets(self) -> list[str]:
        out: list[str] = []
        for line in self.lines:
            m = re.match(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$", line)
            if m:
                out.append(m.group(1).strip())
        return out

    def fenced(self, language: str | None = None) -> list[str]:
        """提取围栏代码块内容。"""
        blocks: list[str] = []
        inside = False
        lang = ""
        buf: list[str] = []
        for line in self.lines:
            m = _FENCE.match(line.strip())
            if m and not inside:
                inside = True
                lang = m.group(1)
                buf = []
                continue
            if line.strip().startswith("```") and inside:
                inside = False
                if language is None or lang == language:
                    blocks.append("\n".join(buf))
                continue
            if inside:
                buf.append(line)
        return blocks

    def is_empty(self) -> bool:
        return not self.body.strip()


def _split_cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def _is_separator(line: str) -> bool:
    cells = _split_cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c != "")


def _parse_table(lines: list[str]) -> Table | None:
    if len(lines) < 2:
        return None
    headers = _split_cells(lines[0])
    start = 1
    if _is_separator(lines[1]):
        start = 2
    rows: list[dict[str, str]] = []
    for line in lines[start:]:
        cells = _split_cells(line)
        if len(cells) < len(headers):
            cells += [""] * (len(headers) - len(cells))
        rows.append({h: cells[i] for i, h in enumerate(headers)})
    return Table(headers=headers, rows=rows)


class MarkdownDoc:
    """轻量 markdown 文档模型：按二级标题切分。"""

    def __init__(self, text: str) -> None:
        self.text = text
        self.sections: list[Section] = []
        current: Section | None = None
        for line in text.splitlines():
            m = _HEADING.match(line)
            if m and len(m.group(1)) <= 2:
                current = Section(title=m.group(2).strip(), level=len(m.group(1)))
                self.sections.append(current)
                continue
            if current is not None:
                current.lines.append(line)
            else:
                # 标题前的内容（如元信息），收进伪章节
                if not self.sections:
                    current = Section(title="__preamble__", level=0)
                    self.sections.append(current)
                current.lines.append(line)

    def section(self, title: str) -> Section | None:
        """按标题查找，支持：完全包含 → 归一化后包含 → 子序列匹配。"""
        if not title:
            return None
        raw = title.strip()
        for s in self.sections:
            if raw in s.title:
                return s
        target = norm_title(raw)
        if not target:
            return None
        for s in self.sections:
            if target in s.norm:
                return s
        for s in self.sections:
            if _subsequence(target, s.norm):
                return s
        return None

    def section_any(self, titles: Iterable[str]) -> Section | None:
        for t in titles:
            s = self.section(t)
            if s is not None:
                return s
        return None

    def find_table(self, name: str) -> Table | None:
        """在任意章节中查找标题匹配的表格（先按章节名，再全文）。"""
        sec = self.section(name)
        if sec is not None:
            t = sec.table()
            if t is not None:
                return t
        # 兜底：全文找表头完全包含目标列名的表
        target = norm_title(name)
        for s in self.sections:
            for t in s.tables():
                if any(norm_title(h) == target for h in t.headers):
                    return t
        return None


# ---------------------------------------------------------------------------
# manifest 校验
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    kind: str
    section: str
    message: str

    def render(self) -> str:
        return f"[{self.kind}] {self.section}: {self.message}"


@dataclass
class ManifestResult:
    deliverable: str
    violations: list[Violation] = field(default_factory=list)
    checked_sections: int = 0

    @property
    def ok(self) -> bool:
        return not self.violations

    def render(self) -> str:
        if self.ok:
            return f"✓ manifest 校验通过（{self.checked_sections} 个章节）"
        lines = [f"✗ manifest 校验失败（{len(self.violations)} 项）"]
        lines += [f"  - {v.render()}" for v in self.violations]
        return "\n".join(lines)


def load_manifest(paths: Paths, manifest_rel: str) -> dict[str, Any]:
    p = paths.resolve(manifest_rel)
    if not p.exists():
        raise ManifestError(f"manifest 不存在: {manifest_rel}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ManifestError(f"manifest 结构非法: {manifest_rel}")
    return data


def validate_manifest(
    text: str,
    manifest: dict[str, Any],
    *,
    fail_on: str = "any",
) -> ManifestResult:
    doc = MarkdownDoc(text)
    result = ManifestResult(deliverable=str(manifest.get("deliverable", "?")))

    sections = manifest.get("sections") or []
    for spec in sections:
        sid = str(spec.get("id", "?"))
        title = str(spec.get("title", ""))
        required = bool(spec.get("required", True))
        sec = doc.section(title)
        result.checked_sections += 1

        if sec is None:
            if required:
                result.violations.append(
                    Violation("missing_section", sid, f"缺少章节「{title}」")
                )
            continue

        stype = str(spec.get("type", "text"))

        if stype == "table":
            table = sec.table()
            if table is None:
                if required:
                    result.violations.append(
                        Violation("not_a_table", sid, f"章节「{title}」应为表格")
                    )
                continue
            for col in spec.get("columns") or []:
                if not table.has_column(str(col)):
                    result.violations.append(
                        Violation(
                            "missing_column",
                            sid,
                            f"表头缺少列「{col}」（现有：{', '.join(table.headers)}）",
                        )
                    )
            min_rows = int(spec.get("min_rows") or 0)
            if min_rows and len(table.rows) < min_rows:
                result.violations.append(
                    Violation(
                        "too_few_rows",
                        sid,
                        f"表格至少需要 {min_rows} 行数据，实际 {len(table.rows)} 行",
                    )
                )
            pattern = spec.get("row_id_pattern")
            if pattern and table.rows:
                rx = re.compile(pattern)
                first_header = table.headers[0]
                for row in table.rows:
                    val = row.get(first_header, "").strip()
                    if not val:
                        continue
                    if not rx.search(val):
                        result.violations.append(
                            Violation(
                                "bad_row_id",
                                sid,
                                f"首列值「{val}」不匹配 {pattern}",
                            )
                        )
                        break
            for col, forbidden in (spec.get("forbid_column_values") or {}).items():
                values = {v.strip().strip("*` ") for v in table.column(str(col))}
                hits = values & {str(f).strip() for f in forbidden if str(f).strip()}
                if hits or "" in values:
                    if hits:
                        result.violations.append(
                            Violation(
                                "forbidden_value",
                                sid,
                                f"列「{col}」出现禁用值 {sorted(hits)}",
                            )
                        )
                    elif "" in values:
                        result.violations.append(
                            Violation("empty_cell", sid, f"列「{col}」存在空值")
                        )

        elif stype == "list":
            items = sec.bullets()
            min_items = int(spec.get("min_items") or 0)
            if min_items and len(items) < min_items:
                result.violations.append(
                    Violation(
                        "too_few_items",
                        sid,
                        f"列表至少需要 {min_items} 项，实际 {len(items)} 项",
                    )
                )

        elif stype == "mermaid":
            if not sec.fenced("mermaid"):
                result.violations.append(
                    Violation("missing_mermaid", sid, "缺少 mermaid 代码块")
                )

        elif stype == "code_block":
            lang = str(spec.get("language") or "")
            blocks = sec.fenced(lang or None)
            if not blocks:
                result.violations.append(
                    Violation("missing_code_block", sid, f"缺少 {lang or ''} 代码块")
                )
            elif lang == "json":
                for i, b in enumerate(blocks):
                    try:
                        json.loads(b)
                    except json.JSONDecodeError as exc:
                        result.violations.append(
                            Violation("invalid_json", sid, f"第 {i + 1} 个 JSON 块非法: {exc}")
                        )

        # must_contain / min_length 对任何类型都生效
        for needle in spec.get("must_contain") or []:
            if str(needle) not in sec.body:
                result.violations.append(
                    Violation("missing_content", sid, f"章节须包含「{needle}」")
                )
        min_len = int(spec.get("min_length") or 0)
        if min_len and len(sec.body.strip()) < min_len:
            result.violations.append(
                Violation(
                    "too_short",
                    sid,
                    f"章节正文过短（{len(sec.body.strip())} < {min_len} 字符）",
                )
            )

    # 全局规则
    rules = manifest.get("rules") or {}
    if rules.get("forbid_placeholder", True):
        for m in re.finditer(r"\{\{[^}]+\}\}", text):
            result.violations.append(
                Violation("placeholder", "全文", f"残留占位符 {m.group(0)}")
            )
            break

    for spec in rules.get("forbid_pattern") or []:
        pattern = str(spec.get("pattern", ""))
        scope = spec.get("scope")
        msg = str(spec.get("message") or f"命中禁用模式 {pattern}")
        if not pattern:
            continue
        targets: list[tuple[str, str]] = []
        if scope:
            sec = doc.section(str(scope))
            if sec is not None:
                targets.append((str(scope), sec.body))
        else:
            targets.append(("全文", text))
        for label, body in targets:
            if re.search(pattern, body, re.MULTILINE):
                result.violations.append(Violation("forbidden_pattern", label, msg))

    if fail_on == "missing_section":
        result.violations = [v for v in result.violations if v.kind == "missing_section"]

    return result


# ---------------------------------------------------------------------------
# 规则求值
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    id: str
    name: str
    severity: str
    verdict: str  # pass | fail | skip
    message: str = ""
    detail: str = ""

    @property
    def blocking(self) -> bool:
        return self.verdict == "fail"

    def render(self) -> str:
        icon = {"pass": "✓", "fail": "✗", "skip": "·"}[self.verdict]
        return f"{icon} {self.id} {self.name}: {self.verdict}" + (
            f" — {self.message}" if self.message and self.verdict != "pass" else ""
        )


def load_ruleset(paths: Paths, rel: str) -> dict[str, Any]:
    p = paths.resolve(rel)
    if not p.exists():
        raise RulesetError(f"规则集不存在: {rel}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RulesetError(f"规则集结构非法: {rel}")
    return data


def evaluate_ruleset(
    *,
    ruleset: dict[str, Any],
    doc: MarkdownDoc,
    rule_ids: list[str] | None = None,
    state: Any = None,
    paths: Paths | None = None,
) -> list[RuleResult]:
    results: list[RuleResult] = []
    wanted = {r.upper() for r in (rule_ids or [])}

    for rule in ruleset.get("rules") or []:
        rid = str(rule.get("id", "?"))
        if wanted and rid.upper() not in wanted:
            continue
        results.append(_eval_rule(rule, doc, state=state, paths=paths))

    return results


def _fail(rule: dict[str, Any], msg: str | None = None, detail: str = "") -> RuleResult:
    then = rule.get("then") or {}
    return RuleResult(
        id=str(rule.get("id")),
        name=str(rule.get("name", "")),
        severity=str(rule.get("severity", "major")),
        verdict="fail",
        message=msg or str(then.get("message", "")),
        detail=detail,
    )


def _pass(rule: dict[str, Any], detail: str = "") -> RuleResult:
    return RuleResult(
        id=str(rule.get("id")),
        name=str(rule.get("name", "")),
        severity=str(rule.get("severity", "major")),
        verdict="pass",
        detail=detail,
    )


def _skip(rule: dict[str, Any], reason: str) -> RuleResult:
    return RuleResult(
        id=str(rule.get("id")),
        name=str(rule.get("name", "")),
        severity=str(rule.get("severity", "major")),
        verdict="skip",
        message=f"M2 未实现该规则种类: {reason}",
    )


def _eval_rule(
    rule: dict[str, Any],
    doc: MarkdownDoc,
    *,
    state: Any = None,
    paths: Paths | None = None,
) -> RuleResult:
    when = rule.get("when") or {}

    # 1) 表格计数等于某值（QG-01 / QG-05 / DR-12）
    if {"table", "column"} <= when.keys() and ("equals" in when) and ("count_gt" in when):
        table = doc.find_table(str(when["table"]))
        if table is None:
            return _pass(rule, "目标表格不存在，视为无违例")
        n = table.count_where(str(when["column"]), str(when["equals"]))
        if n > int(when["count_gt"]):
            return _fail(rule, detail=f"命中 {n} 行")
        return _pass(rule)

    # 2) 表格空值计数（QG-03 / DR-12）
    if {"table", "column", "empty_or_any", "count_gt"} <= when.keys():
        table = doc.find_table(str(when["table"]))
        if table is None:
            return _pass(rule, "目标表格不存在，视为无违例")
        n = table.count_empty(str(when["column"]), when["empty_or_any"])
        if n > int(when["count_gt"]):
            return _fail(rule, detail=f"命中 {n} 行")
        return _pass(rule)

    # 3) 表格行数下限（QG-04）
    if {"table", "row_count_lt"} <= when.keys():
        table = doc.find_table(str(when["table"]))
        rows = len(table.rows) if table else 0
        if rows < int(when["row_count_lt"]):
            return _fail(rule, detail=f"实际 {rows} 行")
        return _pass(rule)

    # 4) 含关键词但缺口径节（DR-01）
    if "document_contains_any" in when and "lacks_section_any" in when:
        hits = [k for k in when["document_contains_any"] if str(k) in doc.text]
        if not hits:
            return _pass(rule, "未涉及计数/比例/时间窗")
        found = doc.section_any([str(t) for t in when["lacks_section_any"]])
        if found is None:
            return _fail(rule, detail=f"触发词: {', '.join(hits)}")
        return _pass(rule, f"口径节: {found.title}")

    # 5) 列值不符合编号模式（DR-02）
    if "table_column_violates_pattern" in when:
        spec = when["table_column_violates_pattern"]
        table = doc.find_table(str(spec.get("table")))
        if table is None:
            return _pass(rule)
        rx = re.compile(str(spec.get("pattern")))
        for v in table.column(str(spec.get("column"))):
            v = v.strip().strip("*` ")
            if v and not rx.match(v):
                return _fail(rule, detail=f"非法值: {v}")
        return _pass(rule)

    # 6) 交叉覆盖（DR-03）
    if "cross_check" in when:
        spec = when["cross_check"]
        src = doc.find_table(str(spec.get("from_table")))
        dst = doc.find_table(str(spec.get("to_table")))
        if src is None or dst is None:
            return _skip(rule, "源表或目标表缺失")
        match_col = str(spec.get("match_column"))
        targets = {v.strip() for v in dst.column(match_col) if v.strip()}
        missing: list[str] = []
        for row in src.rows:
            # 找该行首列（编号）
            key = list(row.values())[0].strip()
            if key and not any(key in t for t in targets):
                missing.append(key)
        if missing:
            return _fail(rule, detail=f"缺少对应记录: {', '.join(missing[:5])}")
        return _pass(rule)

    # 7) 禁用模式（DR-05 / DR-09 / DR-13 等）
    if "forbid_pattern" in when:
        spec = when["forbid_pattern"]
        scope = spec.get("scope")
        patterns = spec.get("patterns") or ([spec["pattern"]] if "pattern" in spec else [])
        body = doc.text
        label = "全文"
        if scope:
            sec = doc.section(str(scope))
            if sec is None:
                return _pass(rule, f"章节「{scope}」不存在，跳过")
            body = sec.body
            label = str(scope)
        for p in patterns:
            m = re.search(str(p), body, re.MULTILINE)
            if m:
                return _fail(rule, detail=f"{label} 命中「{m.group(0)}」")
        return _pass(rule)

    # 8) 断言无证明（DR-06）
    if "claim_without_proof" in when:
        spec = when["claim_without_proof"]
        triggers = [str(t) for t in spec.get("triggers") or []]
        evidence = [str(t) for t in spec.get("evidence_required_any") or []]
        window = int(spec.get("window_lines") or 5)
        lines = doc.text.splitlines()
        for i, line in enumerate(lines):
            if not any(t in line for t in triggers):
                continue
            lo = max(0, i - window)
            hi = min(len(lines), i + window + 1)
            ctx = "\n".join(lines[lo:hi])
            if not any(e in ctx for e in evidence):
                return _fail(rule, detail=f"第 {i + 1} 行断言无证明: {line.strip()[:40]}")
        return _pass(rule)

    # 9) 某列在某条件下缺值（DR-07）
    if "table_column_missing_value" in when:
        spec = when["table_column_missing_value"]
        table = doc.find_table(str(spec.get("table")))
        if table is None:
            return _pass(rule, "目标表格不存在")
        col = str(spec.get("column"))
        if not table.has_column(col):
            return _fail(rule, f"缺少列「{col}」")
        sibling = spec.get("when_sibling_equals") or {}
        sib_col = next(iter(sibling), None)
        sib_val = sibling.get(sib_col) if sib_col else None
        for row in table.rows:
            if sib_col and sib_val is not None:
                if str(row.get(_find_header(table, sib_col), "")).strip() != str(sib_val):
                    continue
            if not str(row.get(_find_header(table, col), "")).strip():
                return _fail(rule, detail=f"列「{col}」在 {sib_col}={sib_val} 时为空")
        return _pass(rule)

    # 10) 列值枚举（DR-11）
    if "table_column_violates_enum" in when:
        spec = when["table_column_violates_enum"]
        table = doc.find_table(str(spec.get("table")))
        if table is None:
            return _pass(rule)
        allowed = {str(a).strip() for a in spec.get("allowed") or []}
        for v in table.column(str(spec.get("column"))):
            v = v.strip().strip("*` ")
            if v and v not in allowed:
                return _fail(rule, detail=f"非法值「{v}」，允许 {sorted(allowed)}")
        return _pass(rule)

    # 11) 必需章节缺失（DR-13 / DR-09 的 section_absent 变体）
    if "section_absent_any" in when:
        titles = [str(t) for t in when["section_absent_any"]]
        found = doc.section_any(titles)
        if found is None:
            return _fail(rule, detail=f"缺少章节之一: {titles}")
        return _pass(rule)

    # 12) token 覆盖（DR-04）
    if "token_coverage" in when:
        spec = when["token_coverage"]
        token_tables = [doc.find_table(str(t)) for t in spec.get("token_tables") or []]
        token_text = "\n".join(
            " ".join(" ".join(r.values()) for r in t.rows)
            for t in token_tables
            if t is not None
        )
        scan = doc.section_any([str(s) for s in spec.get("scan_sections") or []])
        if scan is None:
            return _skip(rule, "扫描章节不存在")
        allow = {str(a) for a in spec.get("allowlist") or []}
        literals = [str(x) for x in spec.get("literals") or []]
        uncovered: list[str] = []
        for lit in literals:
            for m in re.finditer(lit, scan.body):
                raw = m.group(0)
                if raw in allow:
                    continue
                # 颜色/尺寸值需出现在 token 表中
                if raw not in token_text:
                    uncovered.append(raw)
        if uncovered:
            uniq = sorted(set(uncovered))
            return _fail(rule, detail=f"未在 token 表定义: {', '.join(uniq[:8])}")
        return _pass(rule)

    # 13) pending 未登记回填（DR-10）
    if when.get("pending_without_backfill"):
        has_pending = "pending" in doc.text
        if not has_pending:
            return _pass(rule)
        # 检查是否存在回填登记（标题含"回填"或表格列含"关闭条件"）
        registered = doc.section_any(["回填", "pending 与回填登记"])
        if registered is None:
            return _fail(rule, "存在 pending 但无回填登记章节")
        table = registered.table()
        if table is None or not table.rows:
            return _fail(rule, "回填登记表为空")
        blank = [
            r for r in table.rows if not str(list(r.values())[-1]).strip().strip("*` ")
        ]
        if blank:
            return _fail(rule, "回填登记表存在未填行")
        return _pass(rule)

    # 14) 证据旗标（QG-02）
    doc_spec = when.get("document") or {}
    if "requires_flag" in doc_spec:
        evidence = [str(e) for e in doc_spec.get("evidence_any") or []]
        if any(e in doc.text for e in evidence):
            return _pass(rule)
        return _fail(rule, detail="未发现独立用例证据")

    # 15) 回填披露（DR-08）
    if when.get("backfill_disclosure_required"):
        if state is None:
            return _skip(rule, "无状态上下文")
        open_count = len(getattr(state, "open_backfills", lambda: [])())
        if open_count == 0:
            return _pass(rule, "无未关闭回填")
        disclosed = doc.section_any(["未关闭回填任务", "回填任务披露", "回填"])
        if disclosed is None:
            return _fail(rule, f"存在 {open_count} 个未关闭回填但验收报告未披露")
        return _pass(rule)

    return _skip(rule, f"未识别的 when 结构: {sorted(when.keys())}")


def _find_header(table: Table, name: str) -> str:
    target = norm_title(name)
    for h in table.headers:
        if norm_title(h) == target:
            return h
    return name


def summarize(results: list[RuleResult]) -> tuple[bool, str]:
    """返回 (是否全部通过, 可读摘要)。skip 不算失败。"""
    failed = [r for r in results if r.verdict == "fail"]
    skipped = [r for r in results if r.verdict == "skip"]
    lines = [r.render() for r in results]
    if failed:
        lines.append(f"→ {len(failed)} 条规则失败")
    if skipped:
        lines.append(f"→ {len(skipped)} 条规则跳过（M2 未实现或上下文不足）")
    return (not failed, "\n".join(lines))
