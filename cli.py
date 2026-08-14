import json
import sys
import os
from typing import List

import click

from hevy.client import HevyClient, TokenExpiredError
from hevy.storage import Storage
from hevy.models import Workout, ExerciseEntry, SetEntry
from hevy.analysis import progression_by_exercise, workout_volume


@click.group()
def cli():
    """Hevy CLI: track and analyze your training history."""
    pass


def _save_item(client, storage, it) -> bool:
    """Guarda un workout (directo si ya trae ejercicios, si no lo pide por short_id). True si guardó."""
    short = it.get("short_id") or it.get("id")
    if not short:
        return False
    if it.get("exercises") or it.get("exercise_list"):
        storage.save_workout(short, it)
    else:
        storage.save_workout(short, client.get_workout(short))
    return True


@cli.command()
@click.option("--username", default=None, help="Usuario Hevy (opcional, usa HEVY_USERNAME)")
@click.option("--max-pages", default=40, help="Máximo número de páginas de workouts a solicitar")
@click.option("--limit", default=5, help="Workouts por página (la API de Hevy limita a 5 máx.)")
@click.option("--short-ids", "short_ids", default=None, help="Comma-separated short_ids o archivo con un id por línea")
@click.option("--full", is_flag=True, default=False, help="Re-escanea todo (no corta en el primer ya-conocido)")
def fetch(username, max_pages, limit, short_ids, full):
    """Descarga incremental a SQLite: solo baja workouts nuevos, sin re-consultar los viejos."""
    client = HevyClient()
    storage = Storage()
    if username:
        client.username = username
    short_ids_arg = short_ids or os.getenv("HEVY_SHORT_IDS")

    new_count = 0
    try:
        # Modo manual: solo los short_ids dados (salta los ya cacheados).
        if short_ids_arg:
            if os.path.exists(short_ids_arg):
                with open(short_ids_arg, "r", encoding="utf-8") as f:
                    ids = [l.strip() for l in f if l.strip()]
            else:
                ids = [s.strip() for s in short_ids_arg.split(",") if s.strip()]
            for sid in ids:
                if storage.has(sid) and not full:
                    continue
                if _save_item(client, storage, {"short_id": sid}):
                    new_count += 1
            click.echo(f"Guardados {new_count} nuevos. Total en DB: {storage.count()}")
            return

        # Modo incremental: paginar de más nuevo a más viejo, cortar en el 1er ya-conocido.
        offset, stopped_early, seen = 0, False, 0
        for _ in range(max_pages):
            page = client.get_workouts_page(username=client.username, limit=limit, offset=offset)
            if not page:
                break
            for it in page:
                seen += 1
                short = it.get("short_id") or it.get("id")
                if short and storage.has(short) and not full:
                    stopped_early = True
                    break
                if _save_item(client, storage, it):
                    new_count += 1
            if stopped_early:
                break
            if len(page) < limit:
                break
            offset += limit
    except TokenExpiredError as e:
        click.echo(str(e))
        sys.exit(1)
    except Exception as e:
        click.echo(f"No pude descargar: {e}")
        sys.exit(1)

    corte = " (cortó al llegar a workouts ya guardados)" if stopped_early else ""
    click.echo(f"Revisados {seen} · Guardados {new_count} nuevos{corte}. Total en DB: {storage.count()}")


@cli.command()
def refresh():
    """Renueva el access_token usando el refresh_token (y guarda el rotado)."""
    client = HevyClient()
    try:
        client.refresh()
        exp = client.expires_at.isoformat() if client.expires_at else "?"
        click.echo(f"Token renovado. Expira: {exp}")
    except TokenExpiredError as e:
        click.echo(str(e))
        sys.exit(1)


@cli.command()
def login():
    """(Obsoleto) El login por usuario/contraseña no funciona por el reCAPTCHA de Hevy."""
    click.echo(
        "El login por usuario/contraseña no funciona (reCAPTCHA). Usá el flujo de refresh_token:\n"
        "1) Pegá HEVY_REFRESH_TOKEN en el .env (del navegador, una vez).\n"
        "2) Corré `fetch` — el access_token se renueva solo."
    )


@cli.command()
@click.option("--weeks", "weeks", default=4, help="Resumen de mejora en N semanas")
def progress(weeks):
    """Resumen básico de progresión en las últimas N semanas."""
    storage = Storage()
    data = storage.load_all()
    # quick summary: total workouts and total volume
    total = 0.0
    for raw in data:
        # best-effort compute volume if possible
        try:
            w = Workout.from_dict(raw)
            total += workout_volume(w)
        except Exception:
            continue
    click.echo(f"Workouts cached: {len(data)} — Volumen total (approx): {total:.1f} kg")


@cli.command()
@click.argument("exercise")
def exercise(exercise):
    """Progresión de un ejercicio por nombre parcial."""
    storage = Storage()
    raws = storage.load_all()
    workouts: List[Workout] = []
    for r in raws:
        try:
            workouts.append(Workout.from_dict(r))
        except Exception:
            continue
    rows = progression_by_exercise(workouts, exercise)
    if not rows:
        click.echo("No encontré datos para ese ejercicio en el cache. Ejecutá `fetch` primero.")
        sys.exit(1)
    for row in rows:
        click.echo(f"{row['date']}: top {row['top_weight']}kg x{row['reps']} — est1RM {row['est_1rm']:.1f} — vol {row['volume']:.1f}")


@cli.command()
def recommend():
    """Simple recomendaciones (placeholder)."""
    storage = Storage()
    click.echo("Recomendaciones (básicas):")
    click.echo("- Implementadas en hevy/recommendations.py (placeholder).")


@cli.command()
def export():
    """Export compacto pensado para pegar en un chat con IA."""
    storage = Storage()
    raws = storage.load_all()
    workouts: List[Workout] = []
    for r in raws:
        try:
            workouts.append(Workout.from_dict(r))
        except Exception:
            continue
    # build compact per-exercise summary: latest top set and weekly volume (very small)
    summary = {}
    for w in workouts:
        for ex in w.exercises:
            key = ex.name.lower()
            top = None
            vol = 0.0
            for s in ex.sets:
                if s.weight_kg:
                    vol += (s.weight_kg or 0) * (s.reps or 0)
                    if top is None or (s.weight_kg or 0) > (top.weight_kg or 0):
                        top = s
            if key not in summary:
                summary[key] = {"top": None, "volume": 0.0}
            if top and (summary[key]["top"] is None or (top.weight_kg or 0) > (summary[key]["top"]["weight"] or 0)):
                summary[key]["top"] = {"weight": top.weight_kg, "reps": top.reps, "rpe": top.rpe}
            summary[key]["volume"] += vol

    # print compact JSON
    click.echo(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
