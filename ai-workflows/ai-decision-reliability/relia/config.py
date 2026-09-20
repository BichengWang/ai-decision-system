"""Pre-release v0.1.3 candidate specification constants.

Changing any value after viewing results requires a new SPEC_VERSION, a CHANGELOG entry,
and regenerated results. Maintainer review and a public annotated tag remain pending.
Thresholds are proposed engineering gates, not government or industry standards.
"""
from dataclasses import dataclass, field

GENERATOR_SEED = 20260917
TRAIN_SEEDS = (11, 23, 37, 41, 53)

N_DAYS = 120            # simulated days
SESSIONS_PER_DAY = 2500
N_MERCHANTS = 240
N_CATEGORIES = 6
DRIFT_START_DAY = 96    # controlled covariate + concept shift begins (test period)

DISCOUNT_LEVELS = (0.0, 0.05, 0.10, 0.20)          # 0.0 == no offer
MAX_DISCOUNT_BY_CATEGORY = (0.20, 0.20, 0.10, 0.10, 0.05, 0.20)
MIN_BASKET_FOR_OFFER = 12.0
MARGIN_RATE = 0.22

AUTHORIZED_FEATURES = (
    "basket_value", "hour_sin", "hour_cos", "category", "tenure_bucket",
    "merchant_quality", "distance_km", "is_weekend", "discount",
)
# Present in raw records; the model and policy must never read them.
PROHIBITED_FIELDS = ("zip_income_proxy", "device_price_tier", "inferred_age_band")

SPLIT_FRACTIONS = (0.60, 0.20, 0.20)   # train / calibration / test by simulated time

# Ranking task
N_RANK_QUERIES = 4000
RANK_CANDIDATES = 20
RANK_K = 10


@dataclass(frozen=True)
class Gates:
    max_prohibited_access: int = 0
    max_constraint_violations: int = 0
    min_critical_review_routing: float = 1.0
    min_critical_review_fixture_n: int = 12
    max_noncritical_review_misroutes: int = 0
    max_logloss_degradation: float = 0.0     # candidate - baseline must be <= this
    max_brier_degradation: float = 0.0
    max_ece: float = 0.03
    max_worst_slice_ece: float = 0.05
    min_worst_slice_eligible_count: int = 1
    min_stability: float = 0.995
    min_ndcg_gain: float = 0.0               # candidate ranker NDCG@k - baseline >= this
    ece_bins: int = 15
    min_slice_n: int = 500


GATES = Gates()
