"""Evaluator-only controller for deterministic Stage 3 transaction scripts.

Only the action engine receives this object.  Agent-facing tools never expose
the script, its cursor, future events, scenario ground truth, or hidden approval
outcomes.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Callable, TypeVar

from graduation_exception_agent.models.workflow import (
    Approval,
    TransactionAction,
    TransactionResult,
    TransactionScript,
)


class ScriptMismatchError(RuntimeError):
    """Raised internally when an attempted action is not the scripted next step."""


class ScriptExhaustedError(RuntimeError):
    """Raised internally when an action is attempted after the script has ended."""


_T = TypeVar("_T")


class ScenarioController:
    """Own and consume one hidden transaction script atomically."""

    def __init__(
        self,
        *,
        script: TransactionScript,
        approval_seed: Approval | None = None,
    ) -> None:
        if approval_seed is not None and approval_seed.case_id != script.case_id:
            raise ValueError("approval seed and transaction script must share a case")
        self.__script = script.model_copy(deep=True)
        self.__approval_seed = (
            None if approval_seed is None else approval_seed.model_copy(deep=True)
        )
        self.__cursor = 0
        self.__lock = RLock()

    @property
    def consumed_steps(self) -> int:
        """Evaluator diagnostic; do not pass the controller to agent code."""

        with self.__lock:
            return self.__cursor

    @property
    def complete(self) -> bool:
        """Evaluator diagnostic indicating whether all scripted steps ran."""

        with self.__lock:
            return self.__cursor == len(self.__script.steps)

    def approval_seed(self, approval_id: str) -> Approval:
        """Return the hidden initial approval only to the action engine."""

        with self.__lock:
            if (
                self.__approval_seed is None
                or self.__approval_seed.approval_id != approval_id
            ):
                raise KeyError(approval_id)
            return self.__approval_seed.model_copy(deep=True)

    def consume(
        self,
        *,
        action: TransactionAction,
        parameters: dict[str, object],
        execute: Callable[[TransactionResult], _T],
    ) -> _T:
        """Run ``execute`` with the next step and advance only on success.

        The callback normally performs the session's copy-on-write commit.
        Exceptions leave both the script cursor and session state unchanged.
        """

        with self.__lock:
            if self.__cursor >= len(self.__script.steps):
                raise ScriptExhaustedError("no transaction step remains")
            step = self.__script.steps[self.__cursor]
            if step.action is not action or step.action_parameters != parameters:
                raise ScriptMismatchError("attempt does not match the next safe action")
            result = execute(deepcopy(step))
            self.__cursor += 1
            return result


__all__ = [
    "ScenarioController",
    "ScriptExhaustedError",
    "ScriptMismatchError",
]
