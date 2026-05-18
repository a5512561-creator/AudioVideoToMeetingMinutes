"""Global test fixtures."""
import pytest


@pytest.fixture(autouse=True, scope="session")
def _mock_heavy_libs():
    yield
