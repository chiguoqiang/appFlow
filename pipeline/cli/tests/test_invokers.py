"""invokers 测试：用本地假服务器验证真实 HTTP 路径，无需 API Key。

这层测试的价值：验证请求构造、错误映射、自修复循环、写盘——
这些是接真模型后最容易出问题的地方，且不需要花钱。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from pipeline_cli.agents import InvokeRequest, MockInvoker
from pipeline_cli.config import BackendSpec
from pipeline_cli.errors import PipelineError
from pipeline_cli.invokers import (
    ClaudeCliInvoker,
    OpenAICompatibleInvoker,
    RoutingInvoker,
    build_invoker,
)


# ---------------------------------------------------------------------------
# 假 OpenAI 兼容服务器
# ---------------------------------------------------------------------------

class FakeOpenAI:
    """可编排响应的假服务器。"""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.replies: list[str] = []
        self.status = 200
        self.error_body = ""
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> str:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a: Any) -> None:  # noqa: A003
                pass

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                try:
                    outer.requests.append(json.loads(raw.decode("utf-8")))
                except json.JSONDecodeError:
                    outer.requests.append({})

                if outer.status != 200:
                    body = outer.error_body.encode("utf-8")
                    self.send_response(outer.status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return

                content = outer.replies.pop(0) if outer.replies else "默认内容"
                payload = {
                    "choices": [{"message": {"content": content}}],
                    "usage": {"total_tokens": 123},
                }
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        return f"http://127.0.0.1:{port}"

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()


@pytest.fixture()
def fake(monkeypatch):
    srv = FakeOpenAI()
    base = srv.start()
    monkeypatch.setenv("FAKE_KEY", "sk-test")
    yield srv, base
    srv.stop()


def _spec(base: str, **kw) -> BackendSpec:
    raw = {
        "type": "openai_compatible",
        "base_url": base,
        "model": "deepseek-chat",
        "api_key_env": "FAKE_KEY",
        "temperature": 0.2,
        "max_tokens": 4096,
        "timeout_sec": 30,
    }
    raw.update(kw)
    return BackendSpec(name="fake", type="openai_compatible", raw=raw)


def _req(paths, *, manifest: str | None = None, agent: str = "planner") -> InvokeRequest:
    out = paths.projects / "p1"
    out.mkdir(parents=True, exist_ok=True)
    return InvokeRequest(
        agent=agent,
        task="生成文档",
        output_path=out / "out.md",
        output_manifest=manifest,
        must_read=[],
        focus=[],
        constraints=[],
        agent_definition=None,
    )


# ---------------------------------------------------------------------------
# OpenAICompatibleInvoker
# ---------------------------------------------------------------------------

class TestOpenAIInvoker:
    def test_happy_path_writes_file(self, paths, fake):
        srv, base = fake
        srv.replies = ["# 文档\n\n内容"]
        inv = OpenAICompatibleInvoker(name="fake", raw=_spec(base).raw)
        req = _req(paths)
        res = inv.invoke(req, paths=paths)

        assert res.content == "# 文档\n\n内容"
        assert res.tokens_used == 123
        assert req.output_path.read_text(encoding="utf-8") == res.content

    def test_request_shape(self, paths, fake):
        srv, base = fake
        srv.replies = ["x"]
        OpenAICompatibleInvoker(name="fake", raw=_spec(base).raw).invoke(
            _req(paths), paths=paths
        )
        body = srv.requests[0]
        assert body["model"] == "deepseek-chat"
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"
        assert body["stream"] is False
        assert body["temperature"] == 0.2

    def test_missing_api_key(self, paths, fake, monkeypatch):
        _, base = fake
        monkeypatch.delenv("FAKE_KEY", raising=False)
        with pytest.raises(PipelineError) as exc:
            OpenAICompatibleInvoker(name="fake", raw=_spec(base).raw).invoke(
                _req(paths), paths=paths
            )
        assert "缺少 API Key" in str(exc.value)
        assert "FAKE_KEY" in (exc.value.hint or "")

    def test_401_maps_to_auth_hint(self, paths, fake):
        srv, base = fake
        srv.status = 401
        srv.error_body = '{"error":"invalid key"}'
        with pytest.raises(PipelineError) as exc:
            OpenAICompatibleInvoker(name="fake", raw=_spec(base).raw).invoke(
                _req(paths), paths=paths
            )
        assert "认证失败" in str(exc.value)

    def test_429_maps_to_rate_limit(self, paths, fake):
        srv, base = fake
        srv.status = 429
        with pytest.raises(PipelineError) as exc:
            OpenAICompatibleInvoker(name="fake", raw=_spec(base).raw).invoke(
                _req(paths), paths=paths
            )
        assert "限流" in str(exc.value)

    def test_500_maps_to_server_error(self, paths, fake):
        srv, base = fake
        srv.status = 500
        with pytest.raises(PipelineError) as exc:
            OpenAICompatibleInvoker(name="fake", raw=_spec(base).raw).invoke(
                _req(paths), paths=paths
            )
        assert "服务端错误" in str(exc.value)

    def test_strips_code_fence(self, paths, fake):
        srv, base = fake
        srv.replies = ["```markdown\n# 干净\n```"]
        res = OpenAICompatibleInvoker(name="fake", raw=_spec(base).raw).invoke(
            _req(paths), paths=paths
        )
        assert res.content == "# 干净"
        assert any("剥离" in n for n in res.notes)

    def test_self_repair_on_manifest_failure(self, paths, fake):
        """第一版缺章节 → 触发修复 → 第二版合规。"""
        srv, base = fake
        srv.replies = [
            "# 残缺\n\n## 用户故事\n\n| # | 用户故事 | 优先级 | 验收标准 |\n|---|---|---|---|\n| US-1 | x | P0 | y |\n",
            _COMPLETE_BRIEF,
        ]
        inv = OpenAICompatibleInvoker(
            name="fake",
            raw=_spec(base).raw,
            repair_max_attempts=1,
        )
        req = _req(paths, manifest="pipeline/manifests/project_brief.manifest.yaml")
        res = inv.invoke(req, paths=paths)

        assert len(srv.requests) == 2, "未触发修复请求"
        assert "项目代号" in res.content
        assert any("自修复" in n for n in res.notes)
        # 修复请求里应包含校验失败项
        repair_user = srv.requests[1]["messages"][1]["content"]
        assert "校验失败项" in repair_user
        assert "最小改动" in repair_user

    def test_repair_keeps_better_output(self, paths, fake):
        """修复结果更差时，保留原输出。"""
        srv, base = fake
        srv.replies = ["# 好一点\n\n## 元数据\n\n| 字段 | 值 |\n|---|---|\n| a | b |\n", "# x"]
        inv = OpenAICompatibleInvoker(
            name="fake", raw=_spec(base).raw, repair_max_attempts=1
        )
        res = inv.invoke(
            _req(paths, manifest="pipeline/manifests/project_brief.manifest.yaml"),
            paths=paths,
        )
        assert "元数据" in res.content
        assert any("未改善" in n for n in res.notes)

    def test_no_manifest_skips_repair(self, paths, fake):
        srv, base = fake
        srv.replies = ["随便"]
        OpenAICompatibleInvoker(
            name="fake", raw=_spec(base).raw, repair_max_attempts=3
        ).invoke(_req(paths), paths=paths)
        assert len(srv.requests) == 1


# ---------------------------------------------------------------------------
# ClaudeCliInvoker
# ---------------------------------------------------------------------------

class TestClaudeCliInvoker:
    def test_missing_binary(self, paths):
        inv = ClaudeCliInvoker(name="c", raw={"binary": "definitely-not-a-cmd-xyz"})
        with pytest.raises(PipelineError) as exc:
            inv.invoke(_req(paths), paths=paths)
        assert "未找到 CLI" in str(exc.value)

    def test_uses_binary_and_writes(self, paths, tmp_path):
        # 造一个假 CLI：把参数原样写进输出
        script = tmp_path / "fakeclaude"
        script.write_text(
            "#!/bin/sh\n"
            "echo '# 来自假 CLI'\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
        inv = ClaudeCliInvoker(name="c", raw={"binary": str(script)})
        req = _req(paths)
        res = inv.invoke(req, paths=paths)
        assert "来自假 CLI" in res.content
        assert req.output_path.exists()

    def test_not_logged_in_hint(self, paths, tmp_path):
        script = tmp_path / "notlogin"
        script.write_text("#!/bin/sh\necho 'Not logged in · Please run /login' >&2\nexit 1\n")
        script.chmod(0o755)
        inv = ClaudeCliInvoker(name="c", raw={"binary": str(script)})
        with pytest.raises(PipelineError) as exc:
            inv.invoke(_req(paths), paths=paths)
        assert "未登录" in str(exc.value)
        assert "/login" in (exc.value.hint or "")


# ---------------------------------------------------------------------------
# 工厂与路由
# ---------------------------------------------------------------------------

class TestFactory:
    def test_mock(self, paths):
        inv = build_invoker(BackendSpec(name="m", type="mock", raw={}))
        assert isinstance(inv, MockInvoker)

    def test_openai(self):
        inv = build_invoker(
            BackendSpec(name="d", type="openai_compatible", raw={"base_url": "x"})
        )
        assert isinstance(inv, OpenAICompatibleInvoker)

    def test_claude(self):
        inv = build_invoker(BackendSpec(name="c", type="claude_cli", raw={}))
        assert isinstance(inv, ClaudeCliInvoker)

    def test_unknown_type_raises(self):
        with pytest.raises(PipelineError) as exc:
            build_invoker(BackendSpec(name="x", type="weird", raw={}))
        assert "未知后端类型" in str(exc.value)


class TestRoutingInvoker:
    def test_routes_by_agent(self, paths):
        calls: list[str] = []

        class Recorder:
            def __init__(self, tag: str):
                self.tag = tag

            def invoke(self, request, *, paths):
                calls.append(self.tag)
                from pipeline_cli.agents import InvokeResult

                return InvokeResult(content=self.tag, agent=request.agent)

        router = RoutingInvoker(
            {"developer": Recorder("claude")}, Recorder("deepseek")
        )
        router.invoke(_req(paths, agent="developer"), paths=paths)
        router.invoke(_req(paths, agent="planner"), paths=paths)
        assert calls == ["claude", "deepseek"]

    def test_unknown_agent_falls_back(self, paths):
        from pipeline_cli.agents import InvokeResult

        class R:
            def invoke(self, request, *, paths):
                return InvokeResult(content="default", agent=request.agent)

        assert RoutingInvoker({}, R()).invoke(_req(paths, agent="ghost"), paths=paths).content == "default"


# ---------------------------------------------------------------------------

_COMPLETE_BRIEF = """# 立项简报

## 元数据

| 字段 | 值 |
|------|-----|
| 项目代号 | p1 |
| 简报版本 | v1 |
| 状态 | confirmed |

## 核心想法

一个帮助用户记录日常习惯并可视化进度的极简应用，强调一键操作。

## 目标用户

| 用户群 | 描述 | 核心诉求 |
|--------|------|---------|
| 上班族 | 想养成习惯的人 | 打卡快 |

## 功能清单

| # | 功能 | 优先级 | 验收要点 |
|---|------|--------|---------|
| 1 | 打卡 | P0 | 即时反馈 |

## 明确不做

- 账户体系
- 社交分享
- 推送提醒

## 技术约束

| 约束项 | 值 |
|--------|-----|
| 平台 | Flutter |

## 待澄清

| # | 问题 | 提出方 | 状态 |
|---|------|--------|------|
| - | 无 | - | 已关闭 |

## 决策记录

| 日期 | 版本 | 决策 | 理由 | 提出方 |
|------|------|------|------|--------|
| 2026-11-12 | v1 | 纯本地 | 降成本 | user |
"""
