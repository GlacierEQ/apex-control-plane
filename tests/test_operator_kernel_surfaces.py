from scripts.validate_operator_kernel_surfaces import validate


def test_operator_kernel_surfaces_are_consistent() -> None:
    assert validate() == []
