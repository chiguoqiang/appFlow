"""后端配置加载。

设计原则：
1. **密钥永不落盘**：配置里只写 `api_key_env: DEEPSEEK_API_KEY`，真值从环境变量读。
2. **可缺省**：没有配置文件时全部走 mock，保证「克隆即可跑」。
3. **可按岗位分流**：`agents.<name>.backend` 允许不同岗位用不同后端
   （例如 planner 用便宜的 API、developer 用有工具的 CLI）。
4. **用户级覆盖**：`~/.config/appflow/config.yaml` 可覆盖仓库级配置（放个人密钥/偏好）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import PipelineError
from .paths import Paths

CONFIG_FILENAME = "config.yaml"
USER_CONFIG = Path.home() / ".config" / "appflow" / CONFIG_FILENAME

# 后备最小配置：无配置文件时生效
DEFAULT_CONFIG: dict[str, Any] = {
    "default_backend": "mock",
    "agents": {},
    "backends": {
        "mock": {"type": "mock"},
        "deepseek": {
            "type": "openai_compatible",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-chat",
            "api_key_env": "DEEPSEEK_API_KEY",
            "temperature": 0.2,
            "max_tokens": 8192,
            "timeout_sec": 300,
        },
        "claude": {
            "type": "claude_cli",
            "binary": "claude",
            "timeout_sec": 600,
        },
    },
    "context": {
        "max_total_chars": 60000,
        "max_per_file_chars": 20000,
        "keep_structure": True,
    },
    "repair": {
        "max_attempts": 1,
    },
}


@dataclass
class BackendSpec:
    """一个后端后端的解析结果（已合并默认值）。"""

    name: str
    type: str
    raw: dict[str, Any] = field(default_factory=dict)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(paths: Paths | None = None) -> dict[str, Any]:
    """加载配置：默认 → 仓库级 → 用户级（后者覆盖前者）。"""
    cfg = dict(DEFAULT_CONFIG)

    candidates: list[Path] = []
    if paths is not None:
        candidates.append(paths.pipeline / CONFIG_FILENAME)
    candidates.append(USER_CONFIG)

    for p in candidates:
        if not p.exists():
            continue
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise PipelineError(
                f"配置文件解析失败: {p} — {exc}",
                hint="检查 YAML 缩进或引号",
            ) from exc
        if not isinstance(data, dict):
            raise PipelineError(f"配置文件根节点必须是映射: {p}")
        cfg = _deep_merge(cfg, data)

    # 环境变量可整体覆盖默认后端（便于临时切换，如 CI）
    env_default = os.environ.get("APPFLOW_BACKEND")
    if env_default:
        cfg["default_backend"] = env_default

    return cfg


def resolve_backend(cfg: dict[str, Any], *, agent: str, override: str | None = None) -> BackendSpec:
    """决定某个岗位用哪个后端。

    优先级：命令行 override > agents.<name>.backend > default_backend
    """
    if override:
        name = override
    else:
        agent_cfg = (cfg.get("agents") or {}).get(agent) or {}
        name = agent_cfg.get("backend") or cfg.get("default_backend") or "mock"

    backends = cfg.get("backends") or {}
    spec = backends.get(name)
    if spec is None:
        raise PipelineError(
            f"未定义的后端: {name}",
            hint=f"可用: {', '.join(sorted(backends))}；"
            f"在 pipeline/{CONFIG_FILENAME} 的 backends 下添加",
        )
    if not isinstance(spec, dict):
        raise PipelineError(f"后端配置必须是映射: {name}")

    backend_type = str(spec.get("type") or "")
    if not backend_type:
        raise PipelineError(f"后端 {name} 缺少 type 字段")

    return BackendSpec(name=name, type=backend_type, raw=spec)


def read_api_key(spec: BackendSpec) -> str | None:
    """从环境变量取密钥。绝不从配置文件读明文。"""
    env_name = spec.raw.get("api_key_env")
    if not env_name:
        return None
    value = os.environ.get(str(env_name))
    return value.strip() if value else None


def describe_backends(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """用于 `pipeline config-check` 的可读清单（不泄露密钥值）。"""
    out: list[dict[str, Any]] = []
    for name, raw in (cfg.get("backends") or {}).items():
        raw = raw or {}
        spec = BackendSpec(name=name, type=str(raw.get("type", "?")), raw=raw)
        api_env = raw.get("api_key_env")
        key_set = bool(api_env and os.environ.get(str(api_env)))
        out.append(
            {
                "name": name,
                "type": spec.type,
                "model": raw.get("model"),
                "base_url": raw.get("base_url"),
                "api_key_env": api_env,
                "api_key_present": key_set,
                "binary": raw.get("binary"),
            }
        )
    return out


def agent_routing(cfg: dict[str, Any]) -> dict[str, str]:
    """每个岗位当前会使用哪个后端。"""
    out: dict[str, str] = {}
    for agent in ("planner", "designer", "developer", "tester", "acceptor"):
        agent_cfg = (cfg.get("agents") or {}).get(agent) or {}
        out[agent] = agent_cfg.get("backend") or cfg.get("default_backend") or "mock"
    return out
