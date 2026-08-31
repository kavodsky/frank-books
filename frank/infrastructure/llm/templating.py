"""Versioned Jinja templates for LLM calls. A prompt change is a code change."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_DIR = Path(__file__).resolve().parent / "prompts"
_ENV = Environment(
    loader=FileSystemLoader(_DIR),
    undefined=StrictUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)


def render_prompt(template_name: str, context: Mapping[str, str]) -> str:
    return _ENV.get_template(template_name).render(context)
