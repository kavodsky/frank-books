"""Trivial Dagster asset materializes against a throwaway book DB."""

from __future__ import annotations

import pytest
from dagster import materialize

from frank.interfaces.dagster_defs import BookDbResource, defs, pipeline_health


@pytest.mark.integration
def test_pipeline_health_materializes(tmp_path) -> None:
    result = materialize(
        [pipeline_health],
        resources={"book_db": BookDbResource(path=str(tmp_path / "book.db"))},
    )
    assert result.success
    assert (tmp_path / "book.db").is_file()


@pytest.mark.integration
def test_definitions_load() -> None:
    repo = defs.get_repository_def()
    keys = {key.to_user_string() for key in repo.asset_graph.get_all_asset_keys()}
    assert "pipeline_health" in keys
