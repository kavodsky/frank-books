"""Fetched original, before normalization. Infrastructure fills this VO."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FetchedSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    location: str
    raw_bytes: bytes
    filename: str
    suggested_slug: str
    lang: str
    title: str
    author: str
    license_note: str
    heading_pattern: str
    plain_text: str
