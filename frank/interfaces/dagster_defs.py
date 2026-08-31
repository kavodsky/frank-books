"""Dagster skeleton: resources + one trivial asset (roadmap 0.5.4)."""

from __future__ import annotations

from pathlib import Path

from dagster import ConfigurableResource, Definitions, asset
from sqlalchemy import text
from sqlalchemy.engine import Engine

from frank.config import Settings, load_settings
from frank.infrastructure.llm.client import OpenAiChatClient, chat_client_from_settings
from frank.infrastructure.persistence.tables import create_book_db


class BookDbResource(ConfigurableResource):
    path: str = "books/_health/book.db"

    def engine(self) -> Engine:
        return create_book_db(Path(self.path))


class LlmResource(ConfigurableResource):
    config_path: str = "config.toml"
    log_dir: str = "books/_health/logs"

    def settings(self) -> Settings:
        return load_settings(Path(self.config_path))

    def client(self) -> OpenAiChatClient:
        return chat_client_from_settings(self.settings(), Path(self.log_dir))


@asset
def pipeline_health(book_db: BookDbResource) -> str:
    """Prove Dagster can materialize an asset against the book DB resource."""
    engine = book_db.engine()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return "ok"


defs = Definitions(
    assets=[pipeline_health],
    resources={
        "book_db": BookDbResource(),
        "llm": LlmResource(),
    },
)
