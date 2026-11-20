# CLAUDE.md — Hevy Tracker

> Manual de operación de esta herramienta. Léelo al empezar. Objetivo del proyecto: **descargar y
> analizar el historial de entrenamiento de Kevin desde la API (no oficial) de Hevy**, para darle
> estadísticas y recomendaciones de progreso. Idioma: **español** (comentarios y mensajes al usuario).

## Qué es
CLI en Python que autentica contra la API privada de Hevy (reverse-engineered desde el navegador),
baja los workouts a **SQLite** (cada uno como JSON simplificado) de forma **incremental**, y ofrece
análisis de progresión por ejercicio. No es un producto: es para uso personal de Kevin (`your_handle`).

## Arquitectura
```
hevy/client.py          Auth con auto-refresh + HTTP + paginación
hevy/models.py          Workout / ExerciseEntry / SetEntry (parsean crudo Y simplificado)
hevy/simplify.py        simplify_workout(): recorta el JSON antes de guardar
hevy/storage.py         SQLite (data/hevy.db), tabla workouts(short_id PK, updated_at, data JSON)
hevy/analysis.py        Epley 1RM, volumen, progresión, top set
hevy/recommendations.py (placeholder, sin desarrollar)
cli.py                  Comandos (click)
tests/test_hevy.py      14 tests
```

## 🔑 API de Hevy — conocimiento ganado (CRÍTICO, no re-descubrir)
- **Base:** `https://api.hevyapp.com`. Headers obligatorios: `x-api-key: <web-client-api-key>` +
  `hevy-platform: web` + `Authorization: Bearer <access_token>`.
- **Auth:** el `/login` (usuario+contraseña) lleva **reCAPTCHA** → NO replicable por script. Se usa
  el **refresh_token**: `POST /auth/refresh_token` con body `{"refresh_token": <token>}` devuelve
  `{access_token, refresh_token (¡ROTA!), expires_at}`. El **access_token dura ~15 min**; el
  **refresh_token ROTA en cada refresh** → hay que guardar el nuevo o el próximo falla.
- **Endpoints usados:**
  - `GET /user_profile/{handle}` → perfil + rutinas + duraciones semanales.
  - `GET /user_workouts_paged?username={handle}&limit={n}&offset={m}` → lista, de **nuevo→viejo**.
    ⚠️ **`limit` máximo = 5** (limit>5 da 400). Respuesta: `{"workouts": [...]}`, workouts COMPLETOS.
  - `GET /workout/{short_id}` → detalle de un workout.
- **Trampas que costaron tiempo (¡ya resueltas!):**
  1. **`username` = el HANDLE (`your_handle`), NO el email** → email da 404. cli.py avisa si ve un "@".
  2. **`limit` máx 5.**
  3. **Fecha real del entrenamiento = `start_time` (epoch), NO `created_at`** (esa es la de registro;
     al cargar workouts viejos, created_at = hoy y rompe la cronología). `simplify.py` usa start_time
     con −5h (Colombia).
  4. Nombres de ejercicio: usar `es_title` (español) y `title` (inglés), NO `name` (no existe a nivel
     ejercicio). El modelo busca en ambos idiomas.

## Estructura simplificada guardada (data/hevy.db)
```
workout : { short_id, name, date (real), volume_kg, exercises: [...] }   # se descartan 10 idiomas,
exercise: { name(es), name_en, muscle_group, other_muscles, equipment, type, sets: [...] }  # thumbnails,
set     : { weight_kg, reps, rpe, pr: [tipos] }                          # uuids, geospatial, likes...
```
El fetch es **incremental**: corta al primer `short_id` ya guardado. `--full` re-escanea (trae ediciones).

## Setup (.env)
```
HEVY_BASE_URL=https://api.hevyapp.com
HEVY_API_KEY=<web-client-api-key>
HEVY_USERNAME=your_handle          # HANDLE, no email
HEVY_REFRESH_TOKEN=<del navegador, una vez>   # Application>Local Storage de hevy.com
```
El refresh_token rota; si la app web sigue abierta compite y lo invalida → mejor sacarlo tras
re-login y no re-abrir hevy.com. Tokens vivos se guardan en `data/hevy_token.json` (gitignored).

## Comandos
`fetch` (incremental) · `fetch --full` (trae ediciones) · `refresh` · `resimplify` (re-slim+VACUUM) ·
`exercise "sentadilla"` · `progress` · `export` (resumen compacto para pegar en chat).
Tests: `python -m pytest tests/ -v`.

## Análisis — cómo se calcula (y sus límites)
- **1RM estimado (Epley):** `peso × (1 + reps/30)` sobre el **top set** (serie más pesada).
- **% de progreso:** `(1RM_último − 1RM_primero) / 1RM_primero`, ordenado por fecha real.
- ⚠️ **Honestidad estadística:** con 2–3 sesiones por ejercicio, un ±5% es **ruido**, no tendencia.
  Un top-set 1RM mezcla peso y reps (un día pesado vs uno de altas reps confunde). Confiar en lo que
  se repite por **meses**, no en 2 semanas.

## Contexto de entrenamiento de Kevin (para las recomendaciones)
Split (v3, sep 2026): **2 días de pesas PESADOS y full body (Mar/Jue)** + **Sáb correr 30'+** +
**Dom natación**. Prioridad: **posterior (isquios "planos", glúteo "blando")** primero y fresco;
cuádriceps ya adelante (+ la corrida los cubre). Cada día cubre todo el cuerpo + abdomen.
Focos de progreso: **sentadilla en 6–10 reps (no 4 al fallo)** y **RDL (subir de 50 kg, meses estancado)**.
Peso corporal ~64,8 kg · grasa ~16% (US Navy, estimado) · meta: mantener **12–15%** (no bajar más).

## Pendiente / roadmap
- `recommendations.py` está sin implementar (genera texto placeholder) → convertir el análisis en
  recomendaciones automáticas (ejercicios estancados, infracargados, rangos de reps).
- Detección de **ediciones** más fina (comparar `updated_at`) para el fetch incremental sin `--full`.
- Más historial acumulado → tendencias confiables (hoy la ventana es corta).

## Convenciones
- Español en comentarios y salida. Tests deben quedar verdes (`pytest`). No romper la compatibilidad
  del modelo con datos crudos ni simplificados. No commitear `.env` ni `data/`.
