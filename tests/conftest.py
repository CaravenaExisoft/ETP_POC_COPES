from __future__ import annotations

from pathlib import Path

import pytest

from etl_pmc.config.layouts import load_layout

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REAL_SAMPLE_PATH = FIXTURES_DIR / "real" / "entrada_real_1000.txt"


@pytest.fixture(scope="session")
def poc_pmc_layout():
    return load_layout("poc_pmc")


@pytest.fixture(scope="session")
def real_sample_path() -> Path:
    return REAL_SAMPLE_PATH
