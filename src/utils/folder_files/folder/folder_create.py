"""
Simple task:
create empty folders in current directory, with the name as source directory folders.
"""

from pathlib import Path


def create_folders_from(source_dir: str, target_dir: str = ".", dry_run: bool = True) -> None:
    """Re-create the top-level folder names of *source_dir* as empty folders inside *target_dir*."""
    src = Path(source_dir)
    dst = Path(target_dir)

    if not src.is_dir():
        raise NotADirectoryError(f"Not a directory: {src}")
    dst.mkdir(parents=True, exist_ok=True)

    for child in sorted(src.iterdir()):
        if not child.is_dir():
            continue
        new_folder = dst / child.name
        if new_folder.exists():
            print(f"Already exists, skipping: {new_folder}")
            continue
        if dry_run:
            print(f"Would create: {new_folder}")
        else:
            new_folder.mkdir()
            print(f"Created: {new_folder}")


if __name__ == "__main__":
    create_folders_from("E:\\0.0", target_dir="G:\\", dry_run=False)
