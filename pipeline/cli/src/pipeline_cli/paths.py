"""路径解析：仓库根、pipeline 根、项目目录、SOP / manifest / 规则集定位。

设计原则：**所有路径相对仓库根**，与 SOP 内书写的路径保持同一基准。
这样 SOP 里的 `pipeline/manifests/prd.manifest.yaml` 可以直接用，不需改写。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import ProjectNotFound

# 向上查找的标记文件
_MARKER = "pipeline/sops/_schema.json"


def find_repo_root(start: Path | None = None) -> Path:
    """从 start 向上查找包含 pipeline/sops/_schema.json 的目录。"""
    env = os.environ.get("PIPELINE_REPO_ROOT")
    if env:
        root = Path(env).expanduser().resolve()
        if (root / _MARKER).exists():
            return root

    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        if (candidate / _MARKER).exists():
            return candidate
    # 兜底：本文件位于 pipeline/cli/src/pipeline_cli/paths.py
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / _MARKER).exists():
            return candidate
    raise ProjectNotFound(
        f"未找到仓库根（需包含 {_MARKER}）",
        hint="设置环境变量 PIPELINE_REPO_ROOT 或在仓库内执行",
    )


@dataclass(frozen=True)
class Paths:
    """一次运行所需的全部路径。全部为绝对路径。"""

    root: Path

    @property
    def pipeline(self) -> Path:
        return self.root / "pipeline"

    @property
    def sops(self) -> Path:
        return self.pipeline / "sops"

    @property
    def manifests(self) -> Path:
        return self.pipeline / "manifests"

    @property
    def gates(self) -> Path:
        return self.pipeline / "gates"

    @property
    def templates(self) -> Path:
        return self.pipeline / "templates"

    @property
    def agents(self) -> Path:
        return self.pipeline / "agents"

    @property
    def projects(self) -> Path:
        return self.pipeline / "projects"

    @property
    def scripts(self) -> Path:
        return self.pipeline / "scripts"

    def project_dir(self, project: str, *, must_exist: bool = True) -> Path:
        d = self.projects / project
        if must_exist and not d.is_dir():
            raise ProjectNotFound(
                f"项目不存在: {project}（期望目录 {d}）",
                hint="用 `pipeline init <name>` 创建，或检查项目名拼写",
            )
        return d

    def state_file(self, project: str) -> Path:
        # 不要求项目目录存在：让 StateStore.load() 给出「状态文件不存在」的清晰错误，
        # 而不是「项目不存在」（两者对用户含义不同）
        return self.project_dir(project, must_exist=False) / "pipeline-state.json"

    def rel(self, path: Path) -> str:
        """转成相对仓库根的 posix 字符串（用于状态文件与日志）。"""
        try:
            return path.resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def resolve(self, rel_path: str) -> Path:
        """把 SOP 里的相对路径解析成绝对路径。"""
        return (self.root / rel_path).resolve()

    @classmethod
    def discover(cls, start: Path | None = None) -> "Paths":
        return cls(root=find_repo_root(start))
