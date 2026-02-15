"""
Smoke tests for CLI module imports.
"""

import pytest

typer = pytest.importorskip("typer")


def test_cli_main_imports():
    import llm_council.cli.main  # noqa: F401
