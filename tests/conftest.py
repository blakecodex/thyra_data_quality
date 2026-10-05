import pytest


@pytest.fixture(scope="session")
def suite():
    from thyra.gate import load_suite
    return load_suite()


@pytest.fixture(scope="session")
def clean_run(suite):
    from thyra.gate import build_run
    return build_run(7, [], suite)
