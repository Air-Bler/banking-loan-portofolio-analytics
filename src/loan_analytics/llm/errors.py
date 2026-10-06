"""Domain errors of the analytics assistant.

Every error carries a short, safe ``message`` (no SQL text, no payloads, no secrets) and a stable
``category`` that is written to the trace and returned to the model inside the ToolMessage.
"""
from __future__ import annotations


class AssistantError(Exception):
    category = "assistant_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ConfigError(AssistantError):
    """A required setting is missing or invalid (names the setting, never its value)."""

    category = "configuration"


class ToolArgumentError(AssistantError):
    """Malformed, unsupported or unknown tool arguments. The query is never executed."""

    category = "invalid_arguments"


class UnsupportedRequestError(AssistantError):
    """A well-formed request that the approved semantic layer cannot answer (e.g. profit)."""

    category = "unsupported"


class ToolExecutionError(AssistantError):
    """The approved query could not be executed (Databricks/network/warehouse failure)."""

    category = "tool_failure"
