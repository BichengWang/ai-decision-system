"""Input guard: records any model/policy read outside the authorized feature set."""
from __future__ import annotations

import numpy as np

from . import config as C


class GuardedRecords:
    """Dict-like view over raw records that counts unauthorized-field reads.

    Feature builders receive only this view, so an accidental dependency on a
    label, identifier, metadata field, or sensitive proxy is observable.
    """

    def __init__(self, data: dict, authorized=C.AUTHORIZED_FEATURES):
        self._data = data
        self._authorized = set(authorized)
        self.prohibited_access_count = 0
        self.access_log: list[str] = []

    def __getitem__(self, key):
        self.access_log.append(key)
        if key not in self._authorized:
            self.prohibited_access_count += 1
        return self._data[key]

    def __len__(self):
        return len(next(iter(self._data.values())))


def build_ranking_features(records):
    """Ranker feature matrix: sim, pop, fresh, intent-match, q_intent, c_type.

    Reads only C.RANKING_AUTHORIZED_FEATURES through `records`, so a guarded view counts any other read."""
    sim, pop, fresh, q_intent, c_type = (np.asarray(records[k], dtype=float) for k in C.RANKING_AUTHORIZED_FEATURES)
    return np.column_stack([sim, pop, fresh, (q_intent == c_type).astype(float), q_intent, c_type])


def build_features(records, idx=None, discount_override=None):
    cols = []
    for name in C.AUTHORIZED_FEATURES:
        v = np.asarray(records[name], dtype=float)
        if idx is not None:
            v = v[idx]
        if name == "discount" and discount_override is not None:
            v = np.full_like(v, float(discount_override))
        cols.append(v)
    return np.column_stack(cols)
