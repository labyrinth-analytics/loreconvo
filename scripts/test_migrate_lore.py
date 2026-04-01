"""Tests for the Lore migration script."""

import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

# Add scripts dir to path so we can import
sys.path.insert(0, str(Path(__file__).parent))
import migrate_lore


def make_old_tree(tmpdir, product="convovault"):
    """Create a fake old-style directory with test files."""
    old_dir = tmpdir / f".{product}"
    old_dir.mkdir(parents=True)

    if product == "convovault":
        db_file = old_dir / "sessions.db"
        db_file.write_text("fake-sqlite-data-convovault")
    elif product == "projectvault":
        db_file = old_dir / "projectvault.db"
        db_file.write_text("fake-sqlite-data-projectvault")
        vaults_dir = old_dir / "vaults" / "my-project"
        vaults_dir.mkdir(parents=True)
        (vaults_dir / "doc1.md").write_text("# My Doc")
        (old_dir / "config.json").write_text('{"tier": "free"}')

    return old_dir


def test_discover_files_empty():
    """discover_files returns empty list for non-existent dir."""
    result = migrate_lore.discover_files(Path("/nonexistent/path"))
    assert result == []


def test_discover_files_finds_all():
    """discover_files returns all files recursively."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old = make_old_tree(tmpdir, "projectvault")
        files = migrate_lore.discover_files(old)
        names = [str(f) for f in files]
        assert "config.json" in names
        assert "projectvault.db" in names
        assert str(Path("vaults") / "my-project" / "doc1.md") in names


def test_check_migration_no_old_dir():
    """If old dir does not exist, nothing to migrate."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old = tmpdir / ".convovault"
        new = tmpdir / ".loreconvo"
        to_copy, skipped, name = migrate_lore.check_migration(old, new, "Test")
        assert to_copy == []
        assert skipped == []


def test_check_migration_copies_needed():
    """Files in old dir that are not in new dir should be listed for copy."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old = make_old_tree(tmpdir, "convovault")
        new = tmpdir / ".loreconvo"
        to_copy, skipped, name = migrate_lore.check_migration(old, new, "LoreConvo")
        assert len(to_copy) == 1  # sessions.db
        assert len(skipped) == 0
        assert to_copy[0][2] == Path("sessions.db")


def test_check_migration_skips_existing():
    """Files that already exist at the new location are skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old = make_old_tree(tmpdir, "convovault")
        new = tmpdir / ".loreconvo"
        new.mkdir(parents=True)
        (new / "sessions.db").write_text("new-data-already-here")

        to_copy, skipped, name = migrate_lore.check_migration(old, new, "LoreConvo")
        assert len(to_copy) == 0
        assert len(skipped) == 1
        assert skipped[0][0] == Path("sessions.db")


def test_do_copy():
    """do_copy copies files to new locations, creating parent dirs."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old = make_old_tree(tmpdir, "projectvault")
        new = tmpdir / ".loredocs"

        to_copy, _, _ = migrate_lore.check_migration(old, new, "LoreDocs")
        assert len(to_copy) > 0

        copied, errors = migrate_lore.do_copy(to_copy)
        assert errors == []
        assert copied == len(to_copy)

        # Verify files exist at new location
        assert (new / "loredocs.db").exists()
        assert (new / "config.json").exists()
        assert (new / "vaults" / "my-project" / "doc1.md").exists()

        # Verify content preserved
        assert (new / "loredocs.db").read_text() == "fake-sqlite-data-projectvault"
        assert (new / "vaults" / "my-project" / "doc1.md").read_text() == "# My Doc"


def test_do_remove_renames_to_bak():
    """do_remove renames old dir to .bak, does not delete."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old = make_old_tree(tmpdir, "convovault")
        assert old.exists()

        result = migrate_lore.do_remove(old, "LoreConvo")
        assert result is True
        assert not old.exists()
        bak = tmpdir / ".convovault.bak"
        assert bak.exists()
        assert (bak / "sessions.db").exists()


def test_full_migration_dry_run():
    """Dry run does not modify anything."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old_cv = make_old_tree(tmpdir, "convovault")
        old_pv = make_old_tree(tmpdir, "projectvault")

        new_lc = tmpdir / ".loreconvo"
        new_ld = tmpdir / ".loredocs"

        # Patch MIGRATIONS to use our temp dirs
        test_migrations = [
            (old_cv, new_lc, "LoreConvo"),
            (old_pv, new_ld, "LoreDocs"),
        ]

        with mock.patch.object(migrate_lore, "MIGRATIONS", test_migrations):
            with mock.patch("sys.argv", ["migrate_lore.py", "--dry-run"]):
                ret = migrate_lore.main()

        assert ret == 0
        # New dirs should NOT have been created
        assert not new_lc.exists()
        assert not new_ld.exists()
        # Old dirs should still exist
        assert old_cv.exists()
        assert old_pv.exists()


def test_full_migration_with_yes():
    """Full migration with --yes copies everything."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old_cv = make_old_tree(tmpdir, "convovault")
        old_pv = make_old_tree(tmpdir, "projectvault")

        new_lc = tmpdir / ".loreconvo"
        new_ld = tmpdir / ".loredocs"

        test_migrations = [
            (old_cv, new_lc, "LoreConvo"),
            (old_pv, new_ld, "LoreDocs"),
        ]

        with mock.patch.object(migrate_lore, "MIGRATIONS", test_migrations):
            with mock.patch("sys.argv", ["migrate_lore.py", "--yes"]):
                ret = migrate_lore.main()

        assert ret == 0
        assert (new_lc / "sessions.db").exists()
        assert (new_ld / "loredocs.db").exists()
        assert (new_ld / "vaults" / "my-project" / "doc1.md").exists()
        # Old dirs still exist (no --remove-old)
        assert old_cv.exists()


def test_full_migration_with_remove():
    """Full migration with --remove-old renames old dirs to .bak."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old_cv = make_old_tree(tmpdir, "convovault")

        new_lc = tmpdir / ".loreconvo"

        test_migrations = [
            (old_cv, new_lc, "LoreConvo"),
        ]

        with mock.patch.object(migrate_lore, "MIGRATIONS", test_migrations):
            with mock.patch("sys.argv", ["migrate_lore.py", "--yes", "--remove-old"]):
                ret = migrate_lore.main()

        assert ret == 0
        assert (new_lc / "sessions.db").exists()
        assert not old_cv.exists()
        assert (tmpdir / ".convovault.bak").exists()


def test_migration_renames_db_file():
    """Migration renames projectvault.db to loredocs.db at destination."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        old = make_old_tree(tmpdir, "projectvault")
        new = tmpdir / ".loredocs"

        to_copy, _, _ = migrate_lore.check_migration(old, new, "LoreDocs")
        copied, errors = migrate_lore.do_copy(to_copy)
        assert errors == []

        # The file should be renamed to loredocs.db at the destination
        assert (new / "loredocs.db").exists()
        assert not (new / "projectvault.db").exists()
        assert (new / "loredocs.db").read_text() == "fake-sqlite-data-projectvault"


def test_fix_renames_already_migrated():
    """--fix-renames renames projectvault.db -> loredocs.db in existing dirs."""
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        # Simulate already-migrated state: projectvault.db in .loredocs
        new_dir = tmpdir / ".loredocs"
        new_dir.mkdir(parents=True)
        (new_dir / "projectvault.db").write_text("real-data")

        test_migrations = [
            (tmpdir / ".projectvault", new_dir, "LoreDocs"),
        ]

        with mock.patch.object(migrate_lore, "MIGRATIONS", test_migrations):
            with mock.patch("sys.argv", ["migrate_lore.py", "--fix-renames"]):
                ret = migrate_lore.main()

        assert ret == 0
        assert (new_dir / "loredocs.db").exists()
        assert not (new_dir / "projectvault.db").exists()
        assert (new_dir / "loredocs.db").read_text() == "real-data"


if __name__ == "__main__":
    tests = [
        test_discover_files_empty,
        test_discover_files_finds_all,
        test_check_migration_no_old_dir,
        test_check_migration_copies_needed,
        test_check_migration_skips_existing,
        test_do_copy,
        test_do_remove_renames_to_bak,
        test_full_migration_dry_run,
        test_full_migration_with_yes,
        test_full_migration_with_remove,
        test_migration_renames_db_file,
        test_fix_renames_already_migrated,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  [OK] {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  [FAIL] {t.__name__}: {exc}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
    sys.exit(1 if failed else 0)
