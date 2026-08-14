from typing import List

from .storage import Storage
from .analysis import progression_by_exercise


def recommend_from_storage(storage: Storage, min_progress_pct: float = 0.01) -> List[str]:
    """Very small starter recommendations based on per-exercise progression."""
    out = []
    workouts = storage.load_all()
    # convert raw dicts to lightweight objects for analysis is left to the caller
    # TODO: wire models conversion
    out.append("Placeholder: implement recommendation rules (infracargado, estancado)")
    return out
