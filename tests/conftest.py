"""Fixtures for the LLM assistant tests. The fakes themselves live in llm_helpers.py."""
from __future__ import annotations

from collections.abc import Callable

import pytest
from llm_helpers import FakeGoldRepository, ScriptedChatModel


@pytest.fixture
def repo() -> FakeGoldRepository:
    return FakeGoldRepository()


@pytest.fixture
def make_model() -> Callable[[list], ScriptedChatModel]:
    return ScriptedChatModel