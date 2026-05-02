from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "e2e: end-to-end tests that may depend on live model/provider availability")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    allow_live_e2e = os.getenv("AGENTSYSTEM_RUN_LIVE_E2E") == "1"
    if allow_live_e2e:
        return

    skip_live = pytest.mark.skip(reason="live E2E disabled by default, set AGENTSYSTEM_RUN_LIVE_E2E=1 to enable")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_live)
