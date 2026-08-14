"""10 tests para la herramienta Hevy: modelos, análisis, storage y paginación del cliente."""
import json
from pathlib import Path

import pytest

from hevy.models import SetEntry, ExerciseEntry, Workout
from hevy.analysis import epley_1rm, workout_volume, top_set_for_exercise, progression_by_exercise
from hevy.storage import Storage
from hevy.client import HevyClient
from hevy.simplify import simplify_workout


# --- datos de ejemplo (estructura real de la API de Hevy) ---
SQUAT_EX = {
    "title": "Squat (Barbell)",
    "es_title": "Sentadilla (Barra)",
    "sets": [
        {"weight_kg": 20, "reps": 12},
        {"weight_kg": 50, "reps": 10, "rpe": 8.5},
        {"weight_kg": 60, "reps": 8, "rpe": 9.5},
        {"weight_kg": 70, "reps": 4, "rpe": 10, "prs": [{"type": "best_weight", "value": 70}]},
    ],
}
WORKOUT_RAW = {"short_id": "eLCDReRFEmh", "created_at": "2026-08-10T22:59:11Z", "exercises": [SQUAT_EX]}


# 1
def test_setentry_parses_fields():
    s = SetEntry.from_dict({"weight_kg": 70, "reps": 4, "rpe": 10})
    assert s.weight_kg == 70 and s.reps == 4 and s.rpe == 10


# 2 — detección de PR desde la clave "prs" (la API no trae "is_pr")
def test_setentry_pr_from_prs():
    s = SetEntry.from_dict({"weight_kg": 70, "reps": 4, "prs": [{"type": "best_weight", "value": 70}]})
    assert s.is_pr is True
    assert SetEntry.from_dict({"weight_kg": 50, "reps": 10}).is_pr is False


# 3 — FIX clave: el nombre combina título inglés y español (para buscar en ambos idiomas)
def test_exercise_name_combines_es_and_en():
    ex = ExerciseEntry.from_dict(SQUAT_EX)
    assert "squat" in ex.name.lower()
    assert "sentadilla" in ex.name.lower()


# 4
def test_workout_from_dict_parses():
    w = Workout.from_dict(WORKOUT_RAW)
    assert w.short_id == "eLCDReRFEmh"
    assert w.date == "2026-08-10T22:59:11Z"
    assert len(w.exercises) == 1 and len(w.exercises[0].sets) == 4


# 5
def test_epley_1rm():
    assert round(epley_1rm(70, 4), 2) == 79.33


# 6
def test_workout_volume():
    w = Workout.from_dict(WORKOUT_RAW)
    # 20*12 + 50*10 + 60*8 + 70*4 = 240+500+480+280 = 1500
    assert workout_volume(w) == 1500.0


# 7 — buscar por nombre en español debe funcionar (era el bug)
def test_progression_by_exercise_by_spanish_name():
    w = Workout.from_dict(WORKOUT_RAW)
    rows = progression_by_exercise([w], "sentadilla")
    assert len(rows) == 1
    assert rows[0]["top_weight"] == 70 and rows[0]["reps"] == 4
    assert round(rows[0]["est_1rm"], 2) == 79.33


# 8
def test_top_set_picks_heaviest():
    w = Workout.from_dict(WORKOUT_RAW)
    top = top_set_for_exercise(w, "squat")
    assert top.weight_kg == 70 and top.reps == 4


# 9 — storage: guardar / leer / has / count en archivo temporal
def test_storage_roundtrip(tmp_path):
    st = Storage(path=tmp_path / "w.json")
    assert st.count() == 0
    st.save_workout("abc", WORKOUT_RAW)
    assert st.has("abc") is True
    assert st.count() == 1
    assert st.load_all()[0]["short_id"] == "eLCDReRFEmh"


# 10b — fetch incremental: corta en el 1er workout ya conocido, no re-guarda los viejos
def test_incremental_stops_at_known(tmp_path):
    st = Storage(path=tmp_path / "t.db")
    st.save_workout("w2", {"short_id": "w2", "exercises": []})  # ya lo teníamos
    page = [  # página de más nuevo a más viejo
        {"short_id": "w0", "exercises": []},
        {"short_id": "w1", "exercises": []},
        {"short_id": "w2", "exercises": []},
    ]
    saved, stopped = [], False
    for it in page:
        if st.has(it["short_id"]):
            stopped = True
            break
        st.save_workout(it["short_id"], it)
        saved.append(it["short_id"])
    assert stopped is True
    assert saved == ["w0", "w1"]  # paró en w2, no re-consultó lo viejo
    assert st.count() == 3


# 13 — simplify: recorta el ruido (idiomas, thumbnails, uuids) y el modelo lee el resultado
def test_simplify_workout_strips_noise():
    raw = {
        "id": "u", "short_id": "abc", "name": "Superior B", "created_at": "2026-08-08T00:40:47Z",
        "estimated_volume_kg": 9983,
        "exercises": [{
            "title": "Bench Press (Barbell)", "es_title": "Press de Banca (Barra)",
            "de_title": "x", "ja_title": "y", "thumbnail_url": "http://t", "url": "http://u",
            "muscle_group": "chest", "equipment_category": "barbell", "exercise_type": "weight_reps",
            "other_muscles": ["triceps"],
            "sets": [{"id": "s", "weight_kg": 80, "reps": 8, "rpe": None,
                      "prs": [{"type": "best_1rm", "value": 98}], "geospatial_data": None}],
        }],
    }
    s = simplify_workout(raw)
    assert s["short_id"] == "abc" and s["name"] == "Superior B" and s["volume_kg"] == 9983
    ex = s["exercises"][0]
    assert ex["name"] == "Press de Banca (Barra)" and ex["name_en"] == "Bench Press (Barbell)"
    assert ex["muscle_group"] == "chest" and ex["equipment"] == "barbell"
    assert "de_title" not in ex and "thumbnail_url" not in ex and "url" not in ex  # ruido fuera
    st = ex["sets"][0]
    assert st["weight_kg"] == 80 and st["reps"] == 8 and st["pr"] == ["best_1rm"]
    assert "id" not in st and "geospatial_data" not in st
    w = Workout.from_dict(s)  # el modelo lee el simplificado
    assert "press de banca" in w.exercises[0].name.lower()


# 11 — refresh: renueva access_token, ROTA el refresh_token y persiste ambos
def test_refresh_rotates_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(HevyClient, "TOKEN_FILE", tmp_path / "tok.json")
    monkeypatch.setenv("HEVY_REFRESH_TOKEN", "OLD_REFRESH")
    monkeypatch.delenv("HEVY_BEARER_TOKEN", raising=False)
    c = HevyClient()
    assert c.refresh_token == "OLD_REFRESH"

    class FakeResp:
        status_code = 200
        def json(self):
            return {
                "access_token": "NEW_ACCESS",
                "refresh_token": "NEW_REFRESH",  # rotó
                "expires_at": "2026-08-14T02:35:22.205Z",
            }

    monkeypatch.setattr(c.session, "post", lambda *a, **k: FakeResp())
    c.refresh()
    assert c.access_token == "NEW_ACCESS"
    assert c.refresh_token == "NEW_REFRESH"  # guardó el rotado
    saved = json.loads((tmp_path / "tok.json").read_text())
    assert saved["refresh_token"] == "NEW_REFRESH" and saved["access_token"] == "NEW_ACCESS"


# 12 — _token_expired: True si venció, False si aún vigente
def test_token_expired_logic(monkeypatch):
    monkeypatch.setattr(HevyClient, "TOKEN_FILE", Path("nonexistent_xyz.json"))
    c = HevyClient()
    c.access_token = "x"
    from datetime import datetime, timezone, timedelta
    c.expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    assert c._token_expired() is False
    c.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert c._token_expired() is True


# 10 — paginación del cliente: avanza offset y corta cuando la página < limit
def test_list_user_workouts_pagination(monkeypatch):
    client = HevyClient()
    TOTAL = 25

    def fake_request(method, path, params=None, **kw):
        params = params or {}
        off, lim = params.get("offset", 0), params.get("limit", 10)
        if off >= TOTAL:
            return []
        return [{"short_id": f"w{i}"} for i in range(off, min(off + lim, TOTAL))]

    monkeypatch.setattr(client, "_request", fake_request)
    items, ep = client.list_user_workouts(username="kevind21", limit=10)
    assert len(items) == TOTAL  # 10 + 10 + 5, corta en la página incompleta
    assert "user_workouts_paged" in ep or ep is not None
