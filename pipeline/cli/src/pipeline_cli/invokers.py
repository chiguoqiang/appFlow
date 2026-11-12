"""真实模型后端实现。

两个实现共用同一套流水：
  组装 prompt → 调用后端 → 清洗输出 → （可选）按 manifest 自修复 → 写盘

自修复（repair loop）是这里的核心增值：模型第一次产出结构常常差一点
（少个章节/表头列名不对），与其让引擎整体重试（会重新生成全部内容），
不如把「校验失败项」反馈给模型做**最小改动修复**，一次通过率显著提升。
"""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .agents import AgentInvoker, InvokeRequest, InvokeResult, MockInvoker
from .checks import MarkdownDoc, load_manifest, validate_manifest
from .config import BackendSpec, read_api_key
from .errors import PipelineError
from .paths import Paths
from .prompting import Prompt, build_prompt, build_repair_prompt, clean_output


# ---------------------------------------------------------------------------
# 基类：流水编排（组装 / 清洗 / 自修复 / 写盘）
# ---------------------------------------------------------------------------

@dataclass
class BaseModelInvoker:
    """真实后端的公共流程。子类只需实现 `_generate`。"""

    name: str
    raw: dict[str, Any] = field(default_factory=dict)
    context_cfg: dict[str, Any] = field(default_factory=dict)
    repair_max_attempts: int = 1
    verbose: bool = False

    # ---- 子类实现 ----
    def _generate(self, prompt: Prompt, *, timeout_sec: int) -> tuple[str, int]:
        """返回 (原始文本, 消耗 token 数)。"""
        raise NotImplementedError

    # ---- 公共流程 ----
    def invoke(self, request: InvokeRequest, *, paths: Any) -> InvokeResult:
        assert isinstance(paths, Paths)
        notes: list[str] = []

        prompt = build_prompt(
            request,
            paths,
            max_total_chars=int(
                self.context_cfg.get("max_total_chars", 60000)
            ),
            max_per_file_chars=int(
                self.context_cfg.get("max_per_file_chars", 20000)
            ),
        )
        notes.extend(prompt.notes)

        timeout = int(self.raw.get("timeout_sec") or request.timeout_sec or 300)
        raw_text, tokens = self._generate(prompt, timeout_sec=timeout)
        content, clean_notes = clean_output(raw_text)
        notes.extend(clean_notes)

        # 自修复：仅在给了 manifest 且允许重试时
        manifest = self._load_manifest(paths, request.output_manifest)
        if manifest is not None:
            for attempt in range(1, self.repair_max_attempts + 1):
                violations = self._violations(content, manifest)
                if not violations:
                    break
                notes.append(
                    f"自修复第 {attempt} 轮：{len(violations)} 项结构问题"
                )
                repair_user = build_repair_prompt(content, violations)
                repair_prompt = Prompt(
                    system=prompt.system,
                    user=prompt.user + "\n\n" + repair_user,
                )
                fixed_text, extra_tokens = self._generate(
                    repair_prompt, timeout_sec=timeout
                )
                tokens += extra_tokens
                fixed, cn = clean_output(fixed_text)
                notes.extend(cn)
                # 采纳判据不能只看「违规数变少」——空壳文档违规数可能更少
                # （少一节只算 1 项，而残缺表格能算 4 项）。
                # 因此额外要求：内容长度不得显著缩水。
                new_violations = self._violations(fixed, manifest)
                shorter = len(fixed) < len(content) * 0.5
                if not new_violations:
                    content = fixed
                    notes.append("修复后通过校验")
                    break
                if len(new_violations) < len(violations) and not shorter:
                    content = fixed
                    notes.append(
                        f"修复生效：{len(violations)} → {len(new_violations)} 项"
                    )
                    continue
                notes.append(
                    "修复结果未改善（或内容显著缩水），保留原输出"
                )
                break

        request.output_path.parent.mkdir(parents=True, exist_ok=True)
        request.output_path.write_text(content, encoding="utf-8")

        return InvokeResult(
            content=content,
            agent=request.agent,
            tokens_used=tokens,
            notes=notes,
        )

    @staticmethod
    def _load_manifest(paths: Paths, rel: str | None) -> dict[str, Any] | None:
        if not rel:
            return None
        p = paths.resolve(rel)
        if not p.exists():
            return None
        try:
            return load_manifest(paths, rel)
        except PipelineError:
            return None

    @staticmethod
    def _violations(content: str, manifest: dict[str, Any]) -> list[str]:
        result = validate_manifest(content, manifest)
        return [f"[{v.kind}] {v.section}: {v.message}" for v in result.violations]


# ---------------------------------------------------------------------------
# OpenAI 兼容（DeepSeek / Kimi / 通义 / OpenAI）
# ---------------------------------------------------------------------------

class OpenAICompatibleInvoker(BaseModelInvoker):
    """走 /chat/completions 协议的后端。

    仅用标准库 urllib，避免为一次 HTTP 请求引入 httpx/requests 依赖。
    """

    def _generate(self, prompt: Prompt, *, timeout_sec: int) -> tuple[str, int]:
        api_key = read_api_key(
            BackendSpec(name=self.name, type="openai_compatible", raw=self.raw)
        )
        if not api_key:
            env_name = self.raw.get("api_key_env", "API_KEY")
            raise PipelineError(
                f"后端 {self.name} 缺少 API Key",
                hint=f"设置环境变量 {env_name}（不要写进配置文件）",
            )

        base_url = str(self.raw.get("base_url") or "").rstrip("/")
        if not base_url:
            raise PipelineError(f"后端 {self.name} 缺少 base_url")
        url = f"{base_url}/chat/completions"

        payload = {
            "model": str(self.raw.get("model") or "deepseek-chat"),
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "temperature": float(self.raw.get("temperature", 0.2)),
            "max_tokens": int(self.raw.get("max_tokens", 8192)),
            "stream": False,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:400]
            except Exception:  # noqa: BLE001
                pass
            raise PipelineError(
                _http_hint(exc.code, self.name, detail),
                hint=f"HTTP {exc.code} · {url}",
            ) from exc
        except urllib.error.URLError as exc:
            raise PipelineError(
                f"无法连接后端 {self.name}: {exc.reason}",
                hint="检查网络/代理，或确认 base_url 是否正确",
            ) from exc
        except TimeoutError as exc:
            raise PipelineError(
                f"后端 {self.name} 请求超时（{timeout_sec}s）",
                hint="可增大 timeout_sec，或减小 context.max_total_chars",
            ) from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise PipelineError(
                f"后端返回非 JSON: {body[:160]}",
                hint="base_url 是否缺少 /v1 或指向了网页？",
            ) from exc

        choices = data.get("choices") or []
        if not choices:
            err = data.get("error") or data
            raise PipelineError(f"后端未返回内容: {json.dumps(err, ensure_ascii=False)[:300]}")

        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        usage = data.get("usage") or {}
        tokens = int(usage.get("total_tokens") or 0)
        return str(content), tokens


def _http_hint(code: int, backend: str, detail: str) -> str:
    if code == 401:
        return f"{backend} 认证失败：API Key 无效或已过期"
    if code == 402:
        return f"{backend} 余额不足，请充值"
    if code == 429:
        return f"{backend} 触发限流，请稍后重试或降低并发"
    if code == 400:
        return f"{backend} 请求非法（常见：模型名错误 / max_tokens 超限）：{detail}"
    if code >= 500:
        return f"{backend} 服务端错误（{code}），可重试"
    return f"{backend} 请求失败（HTTP {code}）：{detail}"


# ---------------------------------------------------------------------------
# Claude CLI headless
# ---------------------------------------------------------------------------

class ClaudeCliInvoker(BaseModelInvoker):
    """调用 `claude -p` 无头模式。

    优点：自带工具（可写代码、跑测试），适合 developer 岗位。
    缺点：依赖本机登录状态与订阅额度，单次调用有启动开销。
    """

    def _generate(self, prompt: Prompt, *, timeout_sec: int) -> tuple[str, int]:
        binary = str(self.raw.get("binary") or "claude")
        if not shutil.which(binary):
            raise PipelineError(
                f"未找到 CLI: {binary}",
                hint="安装 Claude Code，或把 binary 指向可执行文件路径",
            )

        # 把 system 提示并入 prompt：headless 模式用 --append-system-prompt 更规范，
        # 但不同版本支持度不一，这里合并进正文以保证兼容。
        full_prompt = (
            prompt.system
            + "\n\n---\n\n"
            + prompt.user
            + "\n\n（直接输出文档本体，不要包裹代码块，不要额外解释）"
        )

        cmd = [binary, "-p", full_prompt, "--output-format", "text"]
        extra = self.raw.get("extra_args") or []
        if isinstance(extra, list):
            cmd.extend(str(x) for x in extra)

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise PipelineError(
                f"claude CLI 超时（{timeout_sec}s）",
                hint="增大 timeout_sec，或减小上下文预算",
            ) from exc
        except OSError as exc:
            raise PipelineError(f"无法执行 {binary}: {exc}") from exc

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            if "Not logged in" in stderr or "login" in stderr.lower():
                raise PipelineError(
                    "claude CLI 未登录",
                    hint="在终端执行 `claude` 后按提示 /login（需要订阅）",
                )
            raise PipelineError(
                f"claude CLI 失败（exit {proc.returncode}）: {stderr[:300]}",
                hint="可先用 `claude -p '测试'` 单独验证",
            )

        content = (proc.stdout or "").strip()
        # CLI 不返回 token 用量，按字符粗略估算（中文 1 字 ≈ 1 token）
        approx_tokens = prompt.total_chars + len(content)
        return content, approx_tokens


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------

def build_invoker(
    spec: BackendSpec,
    *,
    cfg: dict[str, Any] | None = None,
    verbose: bool = False,
) -> AgentInvoker:
    """按配置构造后端实例。"""
    cfg = cfg or {}
    context_cfg = dict(cfg.get("context") or {})
    repair_max = int((cfg.get("repair") or {}).get("max_attempts", 1))

    if spec.type == "mock":
        return MockInvoker()

    if spec.type == "openai_compatible":
        return OpenAICompatibleInvoker(
            name=spec.name,
            raw=spec.raw,
            context_cfg=context_cfg,
            repair_max_attempts=repair_max,
            verbose=verbose,
        )

    if spec.type == "claude_cli":
        return ClaudeCliInvoker(
            name=spec.name,
            raw=spec.raw,
            context_cfg=context_cfg,
            repair_max_attempts=repair_max,
            verbose=verbose,
        )

    raise PipelineError(
        f"未知后端类型: {spec.type}",
        hint="支持：mock | openai_compatible | claude_cli",
    )


class RoutingInvoker:
    """按岗位路由到不同后端（混合模式的核心）。

    例如：planner/designer/tester/acceptor 走便宜的 API，
    developer 走有工具能力的 CLI。
    """

    def __init__(self, mapping: dict[str, AgentInvoker], default: AgentInvoker) -> None:
        self._mapping = mapping
        self._default = default

    def invoke(self, request: InvokeRequest, *, paths: Any) -> InvokeResult:
        invoker = self._mapping.get(request.agent, self._default)
        return invoker.invoke(request, paths=paths)
