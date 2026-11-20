# Hevy Tracker

Herramienta CLI en Python para descargar y analizar tu historial de entrenamiento desde la API
(no oficial) de Hevy. Cachea tus workouts localmente y te da progresión por ejercicio, volumen y
un export compacto para pegar en un chat con IA.

## Setup

1. Instalá dependencias:
   ```bash
   pip install -r requirements.txt
   ```
2. Creá tu `.env` a partir de `.env.example`:
   ```
   HEVY_BASE_URL=https://api.hevyapp.com
   HEVY_API_KEY=<web-client-api-key>
   HEVY_USERNAME=tu_handle        # ⚠️ el handle (ej. your_handle), NO el email
   HEVY_BEARER_TOKEN=...          # el access_token (~40 chars) del header Authorization
   ```
   > `HEVY_API_KEY` es la clave **pública del cliente web de Hevy** (la misma para todos): se ve en DevTools → Network → header `x-api-key` de cualquier petición a `api.hevyapp.com`. Si no la defines, el cliente usa ese valor por defecto. API no oficial: revisa los términos de uso de Hevy.

### Cómo sacar el token

En hevy.com: **DevTools (F12) → Network → clic en una request a `api.hevyapp.com` → Headers →
Request Headers → `authorization: Bearer XXXX`** → copiá **solo el `XXXX`** (después de "Bearer ").

⚠️ **El access_token dura ~15 min** → pegalo y corré `fetch` enseguida. (El `refresh_token`, el
largo de ~64 chars, es para el flujo automático que se implementará después — NO va acá.)

## Comandos

| Comando | Qué hace |
|---|---|
| `python cli.py fetch` | Descarga **incremental** a SQLite (`data/hevy.db`): solo baja workouts **nuevos** y **corta** al llegar al primero ya guardado. |
| `python cli.py fetch --full` | Re-escanea todo (no corta en el primero ya-conocido). |
| `python cli.py fetch --username your_handle` | Igual, forzando el handle. |
| `python cli.py fetch --limit 5 --max-pages 40` | Ajusta paginación (⚠️ la API limita `limit` a **5 máx.**). |
| `python cli.py fetch --short-ids abc,def` | Baja solo esos workouts (plan B sin listar). |
| `python cli.py resimplify` | Re-slim + compacta (VACUUM) los workouts ya cacheados, sin re-descargar. |
| `python cli.py export` | Resumen compacto por ejercicio (top set + volumen) para pegar en el chat. |
| `python cli.py exercise "sentadilla"` | Progresión de un ejercicio en el tiempo (peso, reps, 1RM est, volumen). |
| `python cli.py progress` | Resumen: workouts cacheados + volumen total. |
| `python cli.py recommend` | Recomendaciones (básicas, placeholder). |
| `python cli.py login` | (Opcional) login por usuario/contraseña — **no funciona por el reCAPTCHA de Hevy.** |

## Tests

```bash
python -m pytest tests/ -v
```

## Estructura

```
hevy/client.py          Auth (Bearer) + HTTP + páginas /user_workouts_paged
hevy/models.py          Workout / ExerciseEntry / SetEntry (nombres es/en)
hevy/storage.py         Cache SQLite (data/hevy.db): cada workout como JSON, indexado por short_id
hevy/analysis.py        1RM (Epley), volumen, progresión, top set
hevy/recommendations.py Recomendaciones (en desarrollo)
cli.py                  Comandos
tests/                  11 tests
```

## Almacenamiento (SQLite)

Los workouts se guardan en `data/hevy.db`, tabla `workouts(short_id PK, updated_at, data JSON)`.
El JSON se **simplifica** antes de guardar (se descartan títulos en 8 idiomas de más, thumbnails,
urls de video, uuids, geospatial, likes…) → queda ~73% más chico. Estructura guardada:

```
workout : { short_id, name, date, volume_kg, exercises: [...] }
exercise: { name (español), name_en, muscle_group, other_muscles, equipment, type, sets: [...] }
set     : { weight_kg, reps, rpe, pr: [tipos de récord] }
```

El `fetch` es **incremental**: usa `short_id` para no descargar dos veces lo mismo y **corta**
apenas encuentra un workout ya guardado (la API viene de nuevo→viejo). Para traer **ediciones** de
workouts viejos, usá `fetch --full` (re-escanea y sobrescribe). `resimplify` re-slim el cache viejo.
La primera vez migra automáticamente el viejo `data/workouts.json` si existe.

## Notas

- API **no oficial** → para uso personal de tus propios datos; puede romperse sin aviso.
- El `username` en la API es el **handle** (ej. `your_handle`), no el email.
- La API rechaza `limit > 5` (400 Bad Request).
- Pendiente: flujo `refresh_token` para no re-pegar el token cada 15 min.
