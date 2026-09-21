import pytest

from scripts.install_codex_operator_kernel import (
    BEGIN,
    END,
    replace_managed_block,
    validate_marker_layout,
)
from scripts.validate_operator_kernel_surfaces import validate


def test_operator_kernel_surfaces_are_consistent() -> None:
    """All projected instruction surfaces must preserve the standing hardlock."""
    assert validate() == []


@pytest.mark.parametrize(
    "existing",
    [
        f"{BEGIN}\nmissing end",
        f"missing begin\n{END}",
        f"{BEGIN}\na\n{BEGIN}\nb\n{END}",
        f"{BEGIN}\na\n{END}\nb\n{END}",
        f"{END}\nmisordered\n{BEGIN}",
    ],
)
def test_marker_validation_rejects_malformed_layout(existing: str) -> None:
    """Malformed managed markers must fail closed before any file mutation."""
    with pytest.raises(ValueError):
        validate_marker_layout(existing)


def test_replace_managed_block_preserves_unmanaged_content() -> None:
    """A valid replacement must preserve content outside the managed block."""
    existing = f"before\n{BEGIN}\nold\n{END}\nafter\n"
    managed = f"{BEGIN}\nnew\n{END}\n"
    result = replace_managed_block(existing, managed)
    assert result.startswith("before\n")
    assert "new" in result
    assert result.endswith("after\n")
