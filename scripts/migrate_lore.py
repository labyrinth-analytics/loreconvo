#!/usr/bin/env python3
"""Lore Product Family Migration Script.

Migrates user data from the old ConvoVault/ProjectVault paths to the
new LoreConvo/LoreDocs paths.

Old paths:
    ~/.convovault/sessions.db      ->  ~/.loreconvo/sessions.db
    ~/.projectvault/projectvault.db ->  ~/.loredocs/loredocs.db  (renamed!)
    ~/.projectvault/...             ->  ~/.loredocs/...

Safe by default:
    - Never overwrites existing files at the new location
    - Copies first, then optionally removes originals (--remove-old)
    - Dry-run mode (--dry-run) shows what would happen without changing anything
    - Creates backups of old directories before removal

Usage:
    python scripts/migrate_lore.py              # interactive, copy only
    python scripts/migrate_lore.py --dry-run    # preview changes
    python scripts/migrate_lore.py --remove-old # copy then remove originals
    python scripts/migrate_lore.py --yes        # skip confirmation prompt
    python scripts/migrate_lore.py --fix-renames # rename DB files in already-migrated dirs
"""

import argparse
import shutil
import sys
from pathlib import Path


# Migration mappings: (old_path, new_path, product_name)
MIGRATIONS = [
    (
        Path.home() / ".convovault",
        Path.home() / ".loreconvo",
        "LoreConvo (was ConvoVault)",
    ),
    (
        Path.home() / ".projectvault",
        Path.home() / ".loredocs",
        "LoreDocs (was ProjectVault)",
    ),
]

# Files that need to be renamed during migration (old_name -> new_name).
# The migration script copies files preserving relative paths, then applies
# these renames so the DB filenames match what the current code expects.
FILE_RENAMES = {
    ".loredocs": {
        "projectvault.db": "loredocs.db",
    },
}


def discover_files(src_dir):
    """Return list of relative paths for all files in src_dir."""
    if not src_dir.is_dir():
        return []
    return sorted(
        p.relative_to(src_dir)
        for p in src_dir.rglob("*")
        if p.is_file()
    )


def get_rename_map(new_dir):
    """Return {old_filename: new_filename} for files that need renaming at new_dir."""
    dir_name = new_dir.name  # e.g. ".loredocs"
    return FILE_RENAMES.get(dir_name, {})


def apply_rename(rel_path, rename_map):
    """If rel_path's filename is in rename_map, return the renamed rel_path."""
    filename = rel_path.name
    if filename in rename_map:
        return rel_path.parent / rename_map[filename]
    return rel_path


def check_migration(old_dir, new_dir, product_name):
    """Check what needs to be migrated. Returns (to_copy, skipped, product_name)."""
    to_copy = []
    skipped = []

    if not old_dir.exists():
        return to_copy, skipped, product_name

    rename_map = get_rename_map(new_dir)
    files = discover_files(old_dir)
    for rel_path in files:
        src = old_dir / rel_path
        # Apply rename so the destination uses the new filename
        dst_rel = apply_rename(rel_path, rename_map)
        dst = new_dir / dst_rel
        if dst.exists():
            skipped.append((rel_path, "already exists at new location"))
        else:
            to_copy.append((src, dst, rel_path))

    return to_copy, skipped, product_name


def print_plan(to_copy, skipped, product_name, old_dir, new_dir):
    """Print migration plan for one product."""
    print(f"\n{'=' * 60}")
    print(f"  {product_name}")
    print(f"  {old_dir} -> {new_dir}")
    print(f"{'=' * 60}")

    if not to_copy and not skipped:
        print("  No old data found. Nothing to migrate.")
        return

    if to_copy:
        print(f"\n  Files to copy ({len(to_copy)}):")
        rename_map = get_rename_map(new_dir)
        for _src, _dst, rel in to_copy:
            renamed_rel = apply_rename(rel, rename_map)
            if renamed_rel != rel:
                print(f"    [COPY+RENAME] {rel} -> {renamed_rel}")
            else:
                print(f"    [COPY] {rel}")

    if skipped:
        print(f"\n  Files skipped ({len(skipped)}):")
        for rel, reason in skipped:
            print(f"    [SKIP] {rel} -- {reason}")


def do_copy(to_copy):
    """Copy files from old location to new location."""
    copied = 0
    errors = []
    for src, dst, rel in to_copy:
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            copied += 1
        except Exception as exc:
            errors.append((rel, str(exc)))
    return copied, errors


def do_remove(old_dir, product_name):
    """Remove old directory after successful copy."""
    backup = old_dir.parent / (old_dir.name + ".bak")
    try:
        if backup.exists():
            shutil.rmtree(str(backup))
        old_dir.rename(backup)
        print(f"  [OK] Renamed {old_dir} -> {backup}")
        print(f"       (delete {backup} manually when you are satisfied)")
        return True
    except Exception as exc:
        print(f"  [ERROR] Could not rename {old_dir}: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Migrate ConvoVault/ProjectVault data to LoreConvo/LoreDocs."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without making changes.",
    )
    parser.add_argument(
        "--remove-old",
        action="store_true",
        help="After copying, rename old directories to .bak.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    parser.add_argument(
        "--fix-renames",
        action="store_true",
        help="Rename DB files in already-migrated dirs (e.g. projectvault.db -> loredocs.db).",
    )
    args = parser.parse_args()

    # --fix-renames: rename DB files in already-migrated directories
    if args.fix_renames:
        print("Lore Migration: Fix Renames")
        print("Renames DB files in already-migrated directories.\n")
        any_fix = False
        for _old_dir, new_dir, product_name in MIGRATIONS:
            rename_map = get_rename_map(new_dir)
            for old_name, new_name in rename_map.items():
                old_path = new_dir / old_name
                new_path = new_dir / new_name
                if old_path.exists() and not new_path.exists():
                    any_fix = True
                    if args.dry_run:
                        print(f"  [DRY RUN] Would rename: {old_path} -> {new_path}")
                    else:
                        old_path.rename(new_path)
                        print(f"  [OK] Renamed: {old_path} -> {new_path}")
                elif old_path.exists() and new_path.exists():
                    print(f"  [SKIP] Both {old_name} and {new_name} exist in {new_dir}")
                    print(f"         Resolve manually -- the old file may contain your data.")
        if not any_fix:
            print("  Nothing to rename. All DB files already use correct names.")
        return 0

    print("Lore Product Family Migration")
    print("Checks for old ConvoVault / ProjectVault data and copies to new locations.\n")

    plans = []
    any_work = False

    for old_dir, new_dir, product_name in MIGRATIONS:
        to_copy, skipped, name = check_migration(old_dir, new_dir, product_name)
        plans.append((to_copy, skipped, name, old_dir, new_dir))
        print_plan(to_copy, skipped, name, old_dir, new_dir)
        if to_copy:
            any_work = True

    if not any_work:
        print("\nNothing to migrate. All data is already in the new locations (or old locations do not exist).")
        return 0

    if args.dry_run:
        print("\n[DRY RUN] No changes made.")
        return 0

    # Confirmation
    if not args.yes:
        print()
        answer = input("Proceed with migration? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1

    # Execute copies
    total_copied = 0
    total_errors = []
    for to_copy, _skipped, product_name, old_dir, new_dir in plans:
        if not to_copy:
            continue
        print(f"\nMigrating {product_name}...")
        copied, errors = do_copy(to_copy)
        total_copied += copied
        total_errors.extend(errors)
        print(f"  [OK] Copied {copied} file(s)")
        if errors:
            for rel, err in errors:
                print(f"  [ERROR] {rel}: {err}")

    # Remove old directories if requested
    if args.remove_old and not total_errors:
        print("\nRenaming old directories to .bak...")
        for _to_copy, _skipped, product_name, old_dir, _new_dir in plans:
            if old_dir.exists():
                do_remove(old_dir, product_name)
    elif args.remove_old and total_errors:
        print("\n[WARN] Skipping removal due to copy errors above. Fix errors first.")

    # Summary
    print(f"\nDone. Copied {total_copied} file(s), {len(total_errors)} error(s).")
    if total_errors:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
