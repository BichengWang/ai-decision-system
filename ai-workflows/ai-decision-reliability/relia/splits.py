"""Time- and group-separated splits with an explicit leakage check."""
from __future__ import annotations

import numpy as np

from . import config as C


def time_group_split(day, group, fractions=C.SPLIT_FRACTIONS, seed=C.GENERATOR_SEED):
    """Split by simulated time, then remove group overlap.

    Rows are first assigned by day quantile. Each group (merchant) is then assigned
    to exactly one partition (deterministically, proportional to the fractions), and
    rows whose time partition disagrees with their group partition are dropped.
    The result is separated in both time and group.
    """
    day = np.asarray(day); group = np.asarray(group)
    lo, hi = day.min(), day.max() + 1
    t1 = lo + int(round((hi - lo) * fractions[0]))
    t2 = lo + int(round((hi - lo) * (fractions[0] + fractions[1])))
    time_part = np.where(day < t1, 0, np.where(day < t2, 1, 2))
    groups = np.unique(group)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(groups)
    n1 = int(round(len(perm) * fractions[0])); n2 = int(round(len(perm) * (fractions[0] + fractions[1])))
    gpart = {g: (0 if i < n1 else 1 if i < n2 else 2) for i, g in enumerate(perm)}
    group_part = np.array([gpart[g] for g in group])
    keep = time_part == group_part
    idx = {name: np.where(keep & (time_part == k))[0] for k, name in enumerate(("train", "calib", "test"))}
    idx["_boundaries"] = (int(t1), int(t2))
    return idx


def assert_no_leakage(idx, day, group, extra_ids=()):
    parts = ("train", "calib", "test")
    day = np.asarray(day); group = np.asarray(group)
    for a in range(3):
        for b in range(a + 1, 3):
            ia, ib = idx[parts[a]], idx[parts[b]]
            assert day[ia].max() < day[ib].min(), f"time overlap {parts[a]}/{parts[b]}"
            assert not set(group[ia]) & set(group[ib]), f"group overlap {parts[a]}/{parts[b]}"
            for ids in extra_ids:
                ids = np.asarray(ids)
                assert not set(ids[ia]) & set(ids[ib]), "identifier overlap"
    return True
