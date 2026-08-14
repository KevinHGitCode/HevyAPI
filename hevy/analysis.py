from typing import Dict, List, Tuple
import os

from .models import Workout, ExerciseEntry, SetEntry


def epley_1rm(weight: float, reps: int) -> float:
    return weight * (1 + reps / 30.0)


def set_volume(s: SetEntry) -> float:
    if s.weight_kg is None or s.reps is None:
        return 0.0
    weight = float(s.weight_kg)
    # optional: include bar weight when sets were recorded "without the bar"
    include_bar = os.getenv("HEVY_INCLUDE_BAR_WEIGHT", "0").lower() in ("1", "true", "yes")
    if include_bar:
        try:
            bar = float(os.getenv("HEVY_BAR_WEIGHT_KG", "20"))
            weight += bar
        except Exception:
            pass
    return weight * float(s.reps)


def workout_volume(w: Workout) -> float:
    total = 0.0
    for ex in w.exercises:
        for s in ex.sets:
            total += set_volume(s)
    return total


def top_set_for_exercise(w: Workout, exercise_name: str):
    candidates = []
    for ex in w.exercises:
        if exercise_name.lower() in ex.name.lower():
            for s in ex.sets:
                if s.weight_kg:
                    candidates.append(s)
    if not candidates:
        return None
    # top by weight, then reps
    top = max(candidates, key=lambda x: (x.weight_kg or 0, x.reps or 0))
    return top


def progression_by_exercise(workouts: List[Workout], exercise_name: str) -> List[Dict]:
    """Return list of {date, top_weight, reps, est_1rm, volume} ordered by date asc"""
    rows = []
    for w in sorted(workouts, key=lambda x: x.date):
        top = top_set_for_exercise(w, exercise_name)
        vol = 0.0
        for ex in w.exercises:
            if exercise_name.lower() in ex.name.lower():
                for s in ex.sets:
                    vol += set_volume(s)
        if top and top.weight_kg and top.reps:
            rows.append({
                "date": w.date,
                "top_weight": top.weight_kg,
                "reps": top.reps,
                "est_1rm": epley_1rm(top.weight_kg, top.reps),
                "volume": vol,
            })
    return rows
