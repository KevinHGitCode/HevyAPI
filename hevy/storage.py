import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path("data")
DB_FILE = DATA_DIR / "hevy.db"
LEGACY_JSON = DATA_DIR / "workouts.json"


class Storage:
    """SQLite storage: cada entrenamiento se guarda como JSON, indexado por short_id.

    Objetivo: no re-consultar workouts ya descargados. `has()` permite al fetch saltar/parar
    en los que ya están. Migra automáticamente el viejo cache `data/workouts.json` la 1ª vez.
    """

    def __init__(self, path: Optional[Path] = None):
        DATA_DIR.mkdir(exist_ok=True)
        self.path = Path(path) if path else DB_FILE
        self.conn = sqlite3.connect(self.path)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workouts (
                short_id   TEXT PRIMARY KEY,
                updated_at TEXT,
                data       TEXT NOT NULL
            )
            """
        )
        self.conn.commit()
        self._migrate_legacy_json()

    def _migrate_legacy_json(self):
        """Importa una sola vez el viejo data/workouts.json (si existe y la DB está vacía)."""
        if self.path != DB_FILE:
            return  # no migrar en DBs de test/custom
        if self.count() > 0 or not LEGACY_JSON.exists():
            return
        try:
            with open(LEGACY_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            for short_id, payload in data.items():
                self.save_workout(short_id, payload)
        except Exception:
            pass

    def has(self, short_id: str) -> bool:
        cur = self.conn.execute("SELECT 1 FROM workouts WHERE short_id = ?", (short_id,))
        return cur.fetchone() is not None

    def get_updated_at(self, short_id: str) -> Optional[str]:
        cur = self.conn.execute("SELECT updated_at FROM workouts WHERE short_id = ?", (short_id,))
        row = cur.fetchone()
        return row[0] if row else None

    def save_workout(self, short_id: str, payload: Dict):
        updated = payload.get("updated_at") or payload.get("created_at") or ""
        self.conn.execute(
            "INSERT OR REPLACE INTO workouts (short_id, updated_at, data) VALUES (?, ?, ?)",
            (short_id, updated, json.dumps(payload, ensure_ascii=False)),
        )
        self.conn.commit()

    def load_all(self) -> List[Dict]:
        cur = self.conn.execute("SELECT data FROM workouts")
        return [json.loads(r[0]) for r in cur.fetchall()]

    def count(self) -> int:
        cur = self.conn.execute("SELECT COUNT(*) FROM workouts")
        return cur.fetchone()[0]
