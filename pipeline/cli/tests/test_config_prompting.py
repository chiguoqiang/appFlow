"""config 与 prompting 测试。"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pipeline_cli.config import (
    BackendSpec,
    agent_routing,
    describe_backends,
    load_config,
    read_api_key,
    resolve_backend,
)
from pipeline_cli.errors import PipelineError
from pipeline_cli.prompting import (
    build_prompt,
    build_repair_prompt,
    clean_output,
    manifest_checklist,
    truncate_markdown,
)
from pipeline_cli.agents import InvokeRequest


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_defaults_without_file(self, paths):
        cfg = load_config(paths)
        assert cfg["default_backend"] == "mock"
        assert "deepseek" in cfg["backends"]
        assert cfg["context"]["max_total_chars"] == 60000

    def test_repo_config_overrides(self, paths):
        (paths.pipeline / "config.yaml").write_text(
            "default_backend: deepseek\ncontext:\n  max_total_chars: 1234\n",
            encoding="utf-8",
        )
        cfg = load_config(paths)
        assert cfg["default_backend"] == "deepseek"
        assert cfg["context"]["max_total_chars"] == 1234
        # 未覆盖的键保留默认
        assert cfg["context"]["max_per_file_chars"] == 20000
        # backends 仍来自默认（深合并）
        assert "mock" in cfg["backends"]

    def test_invalid_yaml_raises(self, paths):
        (paths.pipeline / "config.yaml").write_text("a: [1,\n", encoding="utf-8")
        with pytest.raises(PipelineError) as exc:
            load_config(paths)
        assert "解析失败" in str(exc.value)

    def test_non_mapping_raises(self, paths):
        (paths.pipeline / "config.yaml").write_text("- 1\n- 2\n", encoding="utf-8")
        with pytest.raises(PipelineError):
            load_config(paths)

    def test_env_overrides_default_backend(self, paths, monkeypatch):
        monkeypatch.setenv("APPFLOW_BACKEND", "claude")
        cfg = load_config(paths)
        assert cfg["default_backend"] == "claude"

    def test_resolve_backend_default(self, paths):
        cfg = load_config(paths)
        spec = resolve_backend(cfg, agent="planner")
        assert spec.name == "mock" and spec.type == "mock"

    def test_resolve_backend_per_agent(self, paths):
        (paths.pipeline / "config.yaml").write_text(
            "default_backend: mock\nagents:\n  developer: { backend: claude }\n",
            encoding="utf-8",
        )
        cfg = load_config(paths)
        assert resolve_backend(cfg, agent="planner").name == "mock"
        assert resolve_backend(cfg, agent="developer").name == "claude"

    def test_override_wins(self, paths):
        cfg = load_config(paths)
        assert resolve_backend(cfg, agent="planner", override="deepseek").name == "deepseek"

    def test_unknown_backend_raises(self, paths):
        cfg = load_config(paths)
        with pytest.raises(PipelineError) as exc:
            resolve_backend(cfg, agent="planner", override="nope")
        assert "未定义的后端" in str(exc.value)

    def test_read_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("MY_TEST_KEY", "  sk-abc  ")
        spec = BackendSpec(
            name="t", type="openai_compatible", raw={"api_key_env": "MY_TEST_KEY"}
        )
        assert read_api_key(spec) == "sk-abc"

    def test_read_api_key_absent(self, monkeypatch):
        monkeypatch.delenv("MY_TEST_KEY", raising=False)
        spec = BackendSpec(
            name="t", type="openai_compatible", raw={"api_key_env": "MY_TEST_KEY"}
        )
        assert read_api_key(spec) is None

    def test_describe_backends_no_secret_leak(self, paths, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-secret-value-should-not-appear")
        cfg = load_config(paths)
        blob = str(describe_backends(cfg))
        assert "sk-secret-value-should-not-appear" not in blob
        assert "DEEPSEEK_API_KEY" in blob

    def test_agent_routing(self, paths):
        (paths.pipeline / "config.yaml").write_text(
            "default_backend: mock\nagents:\n  developer: { backend: claude }\n",
            encoding="utf-8",
        )
        routing = agent_routing(load_config(paths))
        assert routing["developer"] == "claude"
        assert routing["planner"] == "mock"
        assert len(routing) == 5


# ---------------------------------------------------------------------------
# truncate_markdown
# ---------------------------------------------------------------------------

class TestTruncate:
    def test_no_truncate_when_fits(self):
        text = "# A\n\n## B\n\n短\n"
        out, did = truncate_markdown(text, 10000)
        assert out == text and did is False

    def test_preserves_all_headings(self):
        big = "# Doc\n\n" + "".join(
            f"## S{i}\n\n{('内容' * 400)}\n\n" for i in range(8)
        )
        out, did = truncate_markdown(big, 3000)
        assert did is True
        for i in range(8):
            assert f"## S{i}" in out

    def test_respects_budget(self):
        big = "".join(f"## S{i}\n\n{('内容' * 400)}\n\n" for i in range(8))
        for limit in (2000, 5000, 10000):
            out, _ = truncate_markdown(big, limit)
            assert len(out) <= limit * 1.2, f"limit={limit} 实际={len(out)}"

    def test_single_long_line_keeps_prefix(self):
        """回归：单行超长不应整行丢弃。"""
        text = "## S\n\n" + ("很长的内容" * 500)
        out, did = truncate_markdown(text, 500)
        assert did is True
        assert len(out) > 200, "单行内容被整行丢弃了"
        assert "…（截断）" in out

    def test_omission_marker_present(self):
        big = "## S\n\n" + ("内容" * 3000)
        out, _ = truncate_markdown(big, 1000)
        assert "已省略" in out


# ---------------------------------------------------------------------------
# manifest checklist
# ---------------------------------------------------------------------------

class TestManifestChecklist:
    def test_missing_manifest_returns_empty(self, paths):
        assert manifest_checklist(paths, None) == ""
        assert manifest_checklist(paths, "pipeline/manifests/nope.yaml") == ""

    def test_translates_tables_and_rules(self, paths):
        md = manifest_checklist(paths, "pipeline/manifests/prd.manifest.yaml")
        assert "用户故事" in md
        assert "US-" in md  # 编号正则被翻译
        assert "表格列" in md
        assert "占位符" in md

    def test_marks_optional_sections(self, paths):
        md = manifest_checklist(paths, "pipeline/manifests/prd.manifest.yaml")
        assert "可选" in md  # 统计口径为 required:false


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------

def _req(**kw) -> InvokeRequest:
    base = dict(
        agent="planner",
        task="生成 PRD",
        output_path=Path("/tmp/out.md"),
        output_manifest="pipeline/manifests/prd.manifest.yaml",
        must_read=[],
        focus=[],
        constraints=[],
        agent_definition=None,
    )
    base.update(kw)
    return InvokeRequest(**base)  # type: ignore[arg-type]


class TestBuildPrompt:
    def test_includes_task_and_output_rules(self, paths):
        p = build_prompt(_req(), paths)
        assert "生成 PRD" in p.user
        assert "只输出文档本体" in p.user

    def test_injects_agent_definition_into_system(self, paths):
        p = build_prompt(
            _req(agent_definition="pipeline/agents/planner.md"), paths
        )
        assert "planner" in p.system
        assert "职责边界" in p.system

    def test_missing_agent_definition_notes(self, paths):
        p = build_prompt(_req(agent_definition="pipeline/agents/ghost.md"), paths)
        assert any("未找到 Agent 定义" in n for n in p.notes)

    def test_includes_materials(self, paths):
        p = build_prompt(
            _req(must_read=["pipeline/manifests/prd.manifest.yaml"]), paths
        )
        assert "必读材料" in p.user
        assert "prd.manifest.yaml" in p.user

    def test_missing_material_notes_and_skips(self, paths):
        p = build_prompt(_req(must_read=["pipeline/nope.md"]), paths)
        assert any("材料缺失" in n for n in p.notes)

    def test_includes_focus_and_constraints(self, paths):
        p = build_prompt(
            _req(focus=["统计口径成节"], constraints=["不得扩张范围"]), paths
        )
        assert "统计口径成节" in p.user
        assert "不得扩张范围" in p.user

    def test_respects_total_budget(self, paths):
        big = paths.pipeline / "big.md"
        big.write_text("## S\n\n" + ("内容" * 20000), encoding="utf-8")
        p = build_prompt(
            _req(must_read=["pipeline/big.md"]),
            paths,
            max_total_chars=5000,
            max_per_file_chars=20000,
        )
        assert p.total_chars < 12000, f"实际 {p.total_chars}"
        assert any("压缩" in n or "截断" in n for n in p.notes)


# ---------------------------------------------------------------------------
# clean_output
# ---------------------------------------------------------------------------

class TestCleanOutput:
    def test_strips_fence_wrapper(self):
        out, notes = clean_output("```markdown\n# 标题\n\n内容\n```")
        assert out == "# 标题\n\n内容"
        assert any("剥离" in n for n in notes)

    def test_keeps_inner_fences(self):
        src = "## A\n\n```json\n{}\n```"
        out, _ = clean_output(src)
        assert out == src

    def test_strips_preamble(self):
        out, notes = clean_output("好的，以下是 PRD：\n\n# PRD\n\n内容")
        assert out.startswith("# PRD")
        assert any("前置说明" in n for n in notes)

    def test_plain_passthrough(self):
        src = "# 标题\n\n内容"
        out, notes = clean_output(src)
        assert out == src and notes == []


# ---------------------------------------------------------------------------
# repair prompt
# ---------------------------------------------------------------------------

class TestRepairPrompt:
    def test_lists_violations(self):
        p = build_repair_prompt("# 旧内容", ["[missing_section] a: 缺少章节「X」"])
        assert "缺少章节" in p
        assert "最小改动" in p
        assert "# 旧内容" in p

    def test_truncates_long_violation_list(self):
        violations = [f"问题{i}" for i in range(50)]
        p = build_repair_prompt("x", violations, max_show=5)
        assert "另有 45 项" in p
