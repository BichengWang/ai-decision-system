from __future__ import annotations

import os
import shutil
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class MergePair:
    """Represents a merge of folder A -> folder B."""

    src_a: str
    dst_b: str


def merge_folder(dir: str, dry_run: bool = True) -> None:
    """
    Merges folders based on name matching rules:
    1. Matches folders starting with digits (B) with folders not starting with digits (A)
    2. Match is made when A's name matches B's non-digit portion exactly
    3. Warns if A could match multiple kinds of B folders (different non-digit portions)
    4. Moves contents of non-digit folder (A) into matching digit folder (B), keep largest file
    5. Repeats until no more matches are found.

    Args:
        dir (str): Directory path containing folders to merge
        dry_run (bool): If True, only print actions without executing them
    """
    root = Path(dir)
    if not root.exists() or not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    def _normalize_b_folder_name(folder_name: str) -> str:
        """Return B's 'non-digit' portion (also strips dots, per existing logic)."""
        return "".join(c for c in folder_name if (not c.isdigit()) and c != ".")

    def _list_child_folders() -> tuple[list[str], list[str]]:
        folders = [p.name for p in root.iterdir() if p.is_dir()]
        group_a = [name for name in folders if name and not name[0].isdigit()]
        group_b = [name for name in folders if name and name[0].isdigit()]
        return group_a, group_b

    def _build_b_index(group_b: Iterable[str]) -> dict[str, list[str]]:
        """
        Map normalized key -> list of B folders that share that key.
        If a key maps to multiple Bs, it's ambiguous and will be skipped.
        """
        index: dict[str, list[str]] = defaultdict(list)
        for b in group_b:
            index[_normalize_b_folder_name(b)].append(b)
        return dict(index)

    def _find_merge_pairs(group_a: list[str], b_index: dict[str, list[str]]) -> list[MergePair]:
        """
        Find unambiguous (A -> B) merges.

        Keeps the existing behavior that also allows matching A against the first two
        characters of B's normalized key (when that exact A folder exists).
        """
        a_set = set(group_a)
        pairs: list[MergePair] = []

        for key, bs in sorted(b_index.items(), key=lambda kv: kv[0]):
            if len(bs) != 1:
                # Ambiguous B candidates for the same key.
                print(f"Multiple matches found for '{key}': {bs}. Discarding this key.")
                continue

            b = bs[0]
            a: str | None = None
            if key in a_set:
                a = key
            elif len(key) >= 2 and key[:2] in a_set:
                a = key[:2]

            if a is not None:
                pairs.append(MergePair(src_a=a, dst_b=b))

        return pairs

    def _unique_destination_path(dst_dir: Path, name: str) -> Path:
        """
        Returns a non-existing destination path under dst_dir.
        Used for type-mismatch conflicts (file vs dir).
        """
        base, ext = os.path.splitext(name)
        candidate = dst_dir / name
        if not candidate.exists():
            return candidate
        for i in range(1, 10_000):
            candidate = dst_dir / f"{base}__moved{i}{ext}"
            if not candidate.exists():
                return candidate
        raise RuntimeError(f"Could not find unique name for '{name}' in '{dst_dir}'")

    def _merge_path(src_path: Path, dst_path: Path) -> None:
        """
        Merge src_path into dst_path.

        - If dst doesn't exist: move src -> dst
        - If both files: keep the larger one
        - If both dirs: merge recursively, then remove src dir
        - If types differ: move src aside to a unique name under dst's parent
        """
        if not dst_path.exists():
            if dry_run:
                print(f"Would move '{src_path}' -> '{dst_path}'")
            else:
                shutil.move(str(src_path), str(dst_path))
            return

        # Both files: keep the larger one
        if src_path.is_file() and dst_path.is_file():
            src_size = src_path.stat().st_size
            dst_size = dst_path.stat().st_size
            if src_size > dst_size:
                print(
                    f"File dup: '{src_path.name}' "
                    f"(src {src_size}B > dst {dst_size}B) -> "
                    f"{'would replace dst' if dry_run else 'replace dst'}"
                )
                if not dry_run:
                    dst_path.unlink()
                    shutil.move(str(src_path), str(dst_path))
            else:
                print(
                    f"File dup: '{src_path.name}' "
                    f"(dst {dst_size}B >= src {src_size}B) -> "
                    f"{'would keep dst' if dry_run else 'keep dst'}"
                )
                if not dry_run:
                    src_path.unlink()
            return

        # Both dirs: merge recursively
        if src_path.is_dir() and dst_path.is_dir():
            for child in src_path.iterdir():
                _merge_path(child, dst_path / child.name)
            if dry_run:
                print(f"Would remove empty dir '{src_path}'")
            else:
                # should now be empty
                src_path.rmdir()
            return

        # Type mismatch (file vs dir): move src aside with a unique name
        dst_dir = dst_path.parent
        unique_dst = _unique_destination_path(dst_dir, src_path.name)
        print(
            f"Type mismatch dup: '{src_path.name}' exists as different type in dst. "
            f"{'Would move' if dry_run else 'Moving'} src to '{unique_dst.name}'."
        )
        if not dry_run:
            shutil.move(str(src_path), str(unique_dst))

    remove_failures: list[str] = []
    while True and not dry_run:
        group_a, group_b = _list_child_folders()
        b_index = _build_b_index(group_b)
        pairs = _find_merge_pairs(group_a, b_index)
        if not pairs:
            break

        for pair in pairs:
            src_dir = root / pair.src_a
            dst_dir = root / pair.dst_b
            if not src_dir.exists() or not src_dir.is_dir():
                continue
            if not dst_dir.exists() or not dst_dir.is_dir():
                continue

            print(f"{'Would merge' if dry_run else 'Merging'} '{pair.src_a}' into '{pair.dst_b}'")
            for child in src_dir.iterdir():
                _merge_path(child, dst_dir / child.name)

            if dry_run:
                print(f"Would remove source folder '{pair.src_a}'")
            else:
                try:
                    src_dir.rmdir()
                except OSError as e:
                    remove_failures.append(f"{pair.src_a}: {e}")
                    print(f"Failed to remove source folder '{pair.src_a}': {e}")

    if remove_failures:
        print("\nSource folders failed to remove:")
        for msg in remove_failures:
            print(f"- {msg}")
                
                
if __name__ == "__main__":
    merge_folder("G:\\", dry_run=False)
