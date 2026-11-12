"""异常类型。调度器所有可预期失败都应抛出这里定义的异常。"""

from __future__ import annotations


class PipelineError(Exception):
    """所有调度器异常的基类。"""

    exit_code = 1

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint

    def render(self) -> str:
        out = self.message
        if self.hint:
            out += f"\n  提示: {self.hint}"
        return out


class ProjectNotFound(PipelineError):
    exit_code = 2


class SopNotFound(PipelineError):
    exit_code = 2


class StateError(PipelineError):
    """状态文件读取 / 校验 / 一致性错误。"""

    exit_code = 3


class GateError(PipelineError):
    """关卡操作非法（如阶段未处于 awaiting_review）。"""

    exit_code = 4


class StepFailed(PipelineError):
    """SOP 步骤执行失败。"""

    exit_code = 5

    def __init__(self, step_id: str, message: str, *, hint: str | None = None) -> None:
        super().__init__(f"步骤 {step_id} 失败: {message}", hint=hint)
        self.step_id = step_id


class InputNotReady(PipelineError):
    """上游输入未就绪（未批准 / 已 stale）。"""

    exit_code = 6


class ManifestError(PipelineError):
    exit_code = 7


class RulesetError(PipelineError):
    exit_code = 7
