"""本地可视化台（零依赖，只用标准库 http.server）。

设计取舍：
- 不引入 Flask/FastAPI：本机工具，少一个依赖少一处安装失败
- 只做单用户、localhost、只读契约层（写操作限定在 projects/ 下）
- 前端是单文件 HTML（内嵌 CSS/JS），无构建链、无 CDN，离线可用

启动：
    pipeline serve            # 默认 http://127.0.0.1:8787
    pipeline serve --port 9000 --open
"""

from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlparse

from .errors import PipelineError
from .paths import Paths
from . import operations as ops

STATIC_DIR = Path(__file__).parent / "static"


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.hint = hint


def _routes() -> list[tuple[str, str, Callable[..., Any]]]:
    """路由表：(method, pattern, handler)。pattern 支持 {} 占位。

    顺序敏感：具体路径必须在通配之前。
    """
    return [
        ("GET", "/api/health", lambda p, m, q, b: {"ok": True, "backend": "local"}),
        ("GET", "/api/projects", lambda p, m, q, b: ops.list_projects(p)),
        ("POST", "/api/projects", _post_create_project),
        ("GET", "/api/templates/{did}", _get_template),
        ("GET", "/api/projects/{project}", _get_project),
        ("GET", "/api/projects/{project}/deliverables/{did}", _get_deliverable),
        ("PUT", "/api/projects/{project}/deliverables/{did}", _put_deliverable),
        ("POST", "/api/projects/{project}/validate/{did}", _post_validate),
        ("POST", "/api/projects/{project}/submit", _post_submit),
        ("POST", "/api/projects/{project}/gate", _post_gate),
        ("POST", "/api/projects/{project}/run", _post_run),
    ]


# ---------------------------------------------------------------------------
# handlers
# ---------------------------------------------------------------------------

def _post_create_project(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    return ops.create_project(
        paths,
        codename=str(body.get("codename", "")).strip(),
        flow=str(body.get("flow", "new_project")),
        target_project=body.get("target_project") or None,
        force=bool(body.get("force", False)),
    )


def _get_project(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    return ops.project_detail(paths, m["project"])


def _get_template(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    return ops.get_template(paths, m["did"])


def _get_deliverable(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    return ops.read_deliverable(paths, m["project"], m["did"])


def _put_deliverable(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    content = body.get("content")
    if not isinstance(content, str):
        raise ApiError("content 必须是字符串")
    return ops.write_deliverable(paths, m["project"], m["did"], content)


def _post_validate(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    return ops.validate_deliverable_op(
        paths,
        m["project"],
        m["did"],
        fail_on=str(body.get("fail_on", "any")),
        run_rules=bool(body.get("run_rules", True)),
    )


def _post_submit(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    result = ops.submit_deliverable(
        paths,
        m["project"],
        stage=body.get("stage") or None,
        deliverable_id=body.get("deliverable") or None,
        skip_validate=bool(body.get("skip_validate", False)),
    )
    if not result.get("ok"):
        # 校验未通过：返回 200 + ok=false，让前端渲染违规明细
        return result
    return result


def _post_gate(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    action = str(body.get("action", "")).strip()
    if action not in {"approve", "revise", "reject"}:
        raise ApiError(f"非法动作: {action}")
    return ops.apply_gate(
        paths,
        m["project"],
        stage=body.get("stage") or None,
        action=action,
        comment=str(body.get("comment", "")),
    )


def _post_run(paths: Paths, m: dict, q: dict, body: dict) -> dict:
    answers = body.get("answers") or {}
    if not isinstance(answers, dict):
        raise ApiError("answers 必须是对象")
    return ops.run_stage(
        paths,
        m["project"],
        stage=body.get("stage") or None,
        answers={str(k): str(v) for k, v in answers.items()},
        force=bool(body.get("force", False)),
    )


# ---------------------------------------------------------------------------
# 路由匹配
# ---------------------------------------------------------------------------

def _match(pattern: str, path: str) -> dict[str, str] | None:
    p_parts = pattern.strip("/").split("/")
    a_parts = path.strip("/").split("/")
    if len(p_parts) != len(a_parts):
        return None
    params: dict[str, str] = {}
    for p, a in zip(p_parts, a_parts):
        if p.startswith("{") and p.endswith("}"):
            params[p[1:-1]] = unquote(a)
        elif p != a:
            return None
    return params


class Handler(BaseHTTPRequestHandler):
    server_version = "PipelineLocal/1.0"

    # --- 由 serve() 注入 ---
    paths: Paths

    # ---- 日志：保持安静（单行） ----
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: A003
        print(f"  {self.command} {self.path} → {args[1] if len(args) > 1 else ''}")

    # ---- 响应工具 ----
    def _send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._send_json({"error": "not found"}, 404)
            return
        data = path.read_bytes()
        ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in {"application/javascript", "application/json"}:
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError(f"请求体不是合法 JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ApiError("请求体必须是 JSON 对象")
        return parsed

    # ---- 分发 ----
    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        # 静态资源
        if method == "GET" and (path == "/" or path.startswith("/static/")):
            rel = "index.html" if path == "/" else path[len("/static/"):]
            target = (STATIC_DIR / rel).resolve()
            if not str(target).startswith(str(STATIC_DIR.resolve())):
                self._send_json({"error": "forbidden"}, 403)
                return
            self._send_file(target)
            return

        body: dict = {}
        if method in {"POST", "PUT", "PATCH"}:
            try:
                body = self._read_body()
            except ApiError as exc:
                self._send_json({"error": exc.message}, exc.status)
                return

        for r_method, pattern, fn in _routes():
            if r_method != method:
                continue
            params = _match(pattern, path)
            if params is None:
                continue
            try:
                result = fn(self.paths, params, query, body)
                self._send_json(result)
            except ApiError as exc:
                self._send_json(
                    {"error": exc.message, "hint": exc.hint}, exc.status
                )
            except PipelineError as exc:
                self._send_json(
                    {"error": exc.message, "hint": exc.hint}, 400
                )
            except Exception as exc:  # noqa: BLE001
                self._send_json({"error": f"内部错误: {exc}"}, 500)
            return

        self._send_json({"error": f"未知路由: {method} {path}"}, 404)

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")


def serve(
    *,
    paths: Paths | None = None,
    host: str = "127.0.0.1",
    port: int = 8787,
    open_browser: bool = False,
) -> None:
    resolved = paths or Paths.discover()
    Handler.paths = resolved

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"

    print("")
    print("  ┌────────────────────────────────────────────┐")
    print("  │  AI 应用生产线 · 本地可视化台              │")
    print("  └────────────────────────────────────────────┘")
    print(f"  仓库: {resolved.root}")
    print(f"  地址: {url}")
    print("  停止: Ctrl+C")
    print("")

    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  已停止。")
    finally:
        server.server_close()
