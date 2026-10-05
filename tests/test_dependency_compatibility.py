"""Check the dependency contract exposed by the installed distribution."""

from importlib.metadata import requires

from packaging.requirements import Requirement
import pytest


def lancedb_requirement():
    return next(
        requirement for spec in requires("loreconvo") or []
        if (requirement := Requirement(spec)).name == "lancedb"
    )


@pytest.mark.parametrize("version", ["0.30.2", "0.32.0", "0.33.0", "0.34.0"])
def test_distribution_accepts_verified_lancedb_versions(version):
    assert version in lancedb_requirement().specifier


@pytest.mark.parametrize("version", ["0.30.1", "0.34.1", "0.35.0", "1.0.0"])
def test_distribution_rejects_versions_outside_verified_bounds(version):
    assert version not in lancedb_requirement().specifier
