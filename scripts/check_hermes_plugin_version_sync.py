#!/usr/bin/env python3
"""Check that integrations/hermes/pyproject.toml version matches the product version.

Usage: python check_hermes_plugin_version_sync.py [--tests]
  Normal mode: exits 0 on match, 2 on mismatch, 1 on error.
  --tests mode: verifies the check itself (mutation test: mismatched version -> red).
"""

import argparse
import os
import sys
import tomllib


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _product_version(root: str = ROOT) -> str:
    product_toml = os.path.join(root, "pyproject.toml")
    with open(product_toml, "rb") as fh:
        data = tomllib.load(fh)
    return str(data["project"]["version"])


def _hermes_version(root: str = ROOT) -> str:
    hermes_toml = os.path.join(root, "integrations", "hermes", "pyproject.toml")
    with open(hermes_toml, "rb") as fh:
        data = tomllib.load(fh)
    return str(data["project"]["version"])


def _hermes_dep_version(root: str = ROOT) -> str:
    hermes_toml = os.path.join(root, "integrations", "hermes", "pyproject.toml")
    with open(hermes_toml, "rb") as fh:
        data = tomllib.load(fh)
    deps = data["project"].get("dependencies", [])
    for dep in deps:
        if dep.startswith("loreconvo=="):
            return dep.split("==", 1)[1].strip()
    return ""


def check(root: str = ROOT) -> bool:
    """Return True if versions match (and dep version matches too)."""
    pv = _product_version(root)
    hv = _hermes_version(root)
    dv = _hermes_dep_version(root)
    if pv != hv:
        print(f"MISMATCH: product version={pv} hermes-plugin version={hv}", file=sys.stderr)
        return False
    if dv and dv != pv:
        print(f"MISMATCH: product version={pv} hermes dep version={dv}", file=sys.stderr)
        return False
    return True


def _test_mode():
    """Mutation test: verify that mismatched version is detected as red (exit 2).

    Mutations are applied to a private copy of the two files the check reads.
    The committed tree is never written (SH-106819: the previous in-place
    mutate-then-restore raced with concurrent suite runs and could leave the
    real integrations/hermes/pyproject.toml mutated).
    """
    import tempfile
    import shutil

    product_version = _product_version()
    hermes_toml = os.path.join(ROOT, "integrations", "hermes", "pyproject.toml")
    with open(hermes_toml, "r", encoding="utf-8") as fh:
        content = fh.read()

    with tempfile.TemporaryDirectory() as td:
        shutil.copy2(os.path.join(ROOT, "pyproject.toml"), os.path.join(td, "pyproject.toml"))
        hermes_dir = os.path.join(td, "integrations", "hermes")
        os.makedirs(hermes_dir)
        hermes_copy = os.path.join(hermes_dir, "pyproject.toml")

        # --- Mutate: hermes version mismatched ---
        bad = product_version + ".999"
        mutated = content.replace(f'version = "{product_version}"', f'version = "{bad}"')
        with open(hermes_copy, "w", encoding="utf-8") as fh:
            fh.write(mutated)

        if check(td):
            print("FAIL: mutation test should have detected version mismatch", file=sys.stderr)
            sys.exit(1)
        print("OK: version mismatch correctly detected (exit 2)")

        # --- Mutate: hermes dep version mismatched ---
        bad = product_version + ".998"
        mutated = content.replace(
            f"loreconvo=={product_version}",
            f"loreconvo=={bad}",
        )
        with open(hermes_copy, "w", encoding="utf-8") as fh:
            fh.write(mutated)

        if check(td):
            print("FAIL: mutation test should have detected dep version mismatch", file=sys.stderr)
            sys.exit(1)
        print("OK: dep version mismatch correctly detected (exit 2)")

    print("ALL MUTATION TESTS PASSED")


def main() -> bool:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests", action="store_true", help="Run mutation tests on the check itself")
    args = parser.parse_args()

    if args.tests:
        _test_mode()
        return True

    ok = check()
    if not ok:
        sys.exit(2)
    print(f"OK: hermes plugin version matches product version {_product_version()}")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
