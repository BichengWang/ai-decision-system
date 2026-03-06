import os
import re
import shutil
import time  # new import


def move_files_out_folder(folder_path, dry_run=True):
    # Move contents from target deleting subfolders and then delete them.
    subfolder_pattern = re.compile(r"^[A-Za-z0-9-\_]+$")
    for entry in os.listdir(folder_path):
        entry_path = os.path.join(folder_path, entry)
        if os.path.isdir(entry_path) and subfolder_pattern.fullmatch(entry):
            for item in os.listdir(entry_path):
                src = os.path.join(entry_path, item)
                dst = os.path.join(folder_path, item)
                if not dry_run:
                    shutil.move(src, dst)
                print(f"Moved: {src} -> {dst}")
            if not dry_run:
                os.rmdir(entry_path)
            print(f"Delete subfolder: {entry_path}")


def rename_files_in_folder(folder_path, dry_run=True):
    # Two renaming patterns:
    pattern_at = re.compile(r"@([A-Za-z0-9-\_]+)\.")
    pattern_bracket = re.compile(r"^\[[^\]]+\](.+)")
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        if os.path.isfile(file_path):
            new_name = None
            match_at = pattern_at.search(filename)
            match_bracket = pattern_bracket.search(filename)
            if match_at:
                new_name = match_at.group(1) + os.path.splitext(filename)[1]
            elif match_bracket:
                new_name = (
                    match_bracket.group(1).strip() + os.path.splitext(filename)[1]
                )
            if new_name:
                new_file = os.path.join(folder_path, new_name)
                if not dry_run:
                    try:
                        os.rename(file_path, new_file)
                        print(f"Renamed file: {file_path} -> {new_file}")
                    except FileExistsError:
                        print(f"File exists: {new_file}")
                        continue


def process_folders_in_directory(root_path, dry_run=True, sleep_time=0.001, excluded={"System Volume Information", "$RECYCLE.BIN"}):
    # Process only folders with names matching the pattern: digit, dot, digits, dot, then anything.
    # Process folders that either match the pattern or start with a regular character
    # folder_pattern = re.compile(r"^[0-3]\.[0-5][0-9]\.")
    # char_pattern = re.compile(r"^[A-Za-z]")
    for entry in os.listdir(root_path):
        entry_path = os.path.join(root_path, entry)
        if os.path.isdir(entry_path):
            if entry in excluded:
                continue
            print(f"Processing folder: {entry_path}")
            move_files_out_folder(entry_path, dry_run=dry_run)
            time.sleep(sleep_time)
            rename_files_in_folder(entry_path, dry_run=dry_run)


if __name__ == "__main__":
    base_path = "G:\\"
    process_folders_in_directory(base_path, dry_run=False, sleep_time=0.01)
    # move_files_out_folder(entry_path, dry_run=False)
    # time.sleep(1)
    # rename_files_in_folder(entry_path, dry_run=False)
