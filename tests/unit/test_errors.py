"""ErrorClass is set at the raise site, not grepped from logs."""

from __future__ import annotations

import pytest

from frank.domain.errors import (
    ErrorClass,
    ModelTimeout,
    ModelUnreachable,
    SchemaInvalid,
)


@pytest.mark.unit
def test_subclasses_pin_error_class() -> None:
    assert ModelUnreachable("x").error_class is ErrorClass.MODEL_UNREACHABLE
    assert ModelTimeout("x").error_class is ErrorClass.TIMEOUT
    assert SchemaInvalid("x").error_class is ErrorClass.SCHEMA_INVALID
