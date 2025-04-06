import os
import shutil
import logging


def merge_folder(dir: str, dry_run: bool = True) -> None:
    """
    Merges folders based on name matching rules:
    1. Matches folders starting with digits (B) with folders not starting with digits (A)
    2. Match is made when A's name matches B's non-digit portion exactly
    3. Warns if A could match multiple kinds of B folders (different non-digit portions)
    4. Moves contents of non-digit folder (A) into matching digit folder (B)
    5. Repeats until no more matches are found.

    Args:
        dir (str): Directory path containing folders to merge
        dry_run (bool): If True, only print actions without executing them
    """
    folders = [f for f in os.listdir(dir) if os.path.isdir(os.path.join(dir, f))]
    
    group_a = [f for f in folders if not f[0].isdigit()]
    group_b = [f for f in folders if f[0].isdigit()]
    
    b_mapping = {}
    for b in group_b:
        b_mapping["".join(c for c in b if not c.isdigit() and c != '.')] = b
    
    # Check for duplicate matches
    from collections import Counter
    counter = Counter(b_mapping.keys())
    dedup_b_mapping = {}
    for k, v in b_mapping.items():
        if counter[k] > 1:
            logging.warning(f"Multiple matches found for '{k}': {v}, discard it.")
        else:
            dedup_b_mapping[k] = v
    
    for bk, bv in dedup_b_mapping.items():
        if bk in group_a or bk[:2] in group_a:
            a = group_a[bk] if bk in group_a else group_a[bk[:2]]
            b = bv
            src = os.path.join(dir, a)
            dst = os.path.join(dir, b)
            
            if dry_run:
                print(f"Would merge '{a}' into '{b}'")
            else:
                print(f"Merging '{a}' into '{b}'")
                for item in os.listdir(src):
                    src_path = os.path.join(src, item)
                    dst_path = os.path.join(dst, item)
                    shutil.move(src_path, dst_path)
                os.rmdir(src)
                
                
if __name__ == "__main__":
    merge_folder("/mnt/g/test", dry_run=True)
