"""Simplifica el JSON crudo de Hevy antes de guardarlo en SQLite.

Descarta lo que no sirve para el análisis: títulos en 8 idiomas de más, thumbnails, urls de
video, uuids, custom_metric/geospatial, media, likes, etc. Conserva español (+inglés para buscar),
grupo muscular, equipo y los sets con peso/reps/rpe/PR.
"""
from typing import Dict, List
from datetime import datetime, timezone, timedelta

# Colombia = UTC-5 (para que la fecha local del entrenamiento sea correcta)
_TZ = timedelta(hours=-5)


def _workout_date(raw: Dict) -> str:
    """Fecha REAL del entrenamiento (start_time), no la de registro (created_at).

    Clave: al registrar un workout viejo, created_at = hoy; start_time = cuando entrenaste.
    """
    st = raw.get("start_time")
    if isinstance(st, (int, float)):
        return (datetime.fromtimestamp(st, timezone.utc) + _TZ).strftime("%Y-%m-%d")
    c = raw.get("created_at") or raw.get("updated_at") or ""
    return c[:10]


def simplify_set(s: Dict) -> Dict:
    prs = s.get("prs") or s.get("personalRecords") or []
    return {
        "weight_kg": s.get("weight_kg"),
        "reps": s.get("reps"),
        "rpe": s.get("rpe"),
        "pr": [p.get("type") for p in prs if isinstance(p, dict)] if prs else [],
    }


def simplify_exercise(ex: Dict) -> Dict:
    return {
        "name": ex.get("es_title") or ex.get("title"),   # español como principal
        "name_en": ex.get("title"),                        # inglés para búsqueda bilingüe
        "muscle_group": ex.get("muscle_group"),
        "other_muscles": ex.get("other_muscles") or [],
        "equipment": ex.get("equipment_category"),
        "type": ex.get("exercise_type"),
        "sets": [simplify_set(s) for s in ex.get("sets", [])],
    }


def simplify_workout(raw: Dict) -> Dict:
    """Devuelve una versión mínima del workout, lista para guardar y analizar."""
    return {
        "short_id": raw.get("short_id") or raw.get("id"),
        "name": raw.get("name"),                           # nombre de la rutina (ej. "Superior B")
        "date": _workout_date(raw),                        # fecha REAL (start_time), no la de registro
        "volume_kg": raw.get("estimated_volume_kg"),
        "exercises": [simplify_exercise(ex) for ex in raw.get("exercises", [])],
    }


def is_simplified(d: Dict) -> bool:
    """Heurística: un workout ya simplificado tiene 'date' y no trae 'created_at' ni títulos de idiomas."""
    return "date" in d and "created_at" not in d
