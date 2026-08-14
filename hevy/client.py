import os
import logging
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class TokenExpiredError(Exception):
    pass


class HevyClient:
    """Cliente de la API (no oficial) de Hevy con auto-refresh del access_token.

    Auth:
    - `HEVY_REFRESH_TOKEN` en .env (bootstrap, se pega UNA vez).
    - Los tokens vivos se persisten en `data/hevy_token.json`:
      {access_token, refresh_token, expires_at}.
    - El access_token dura ~15 min; se renueva solo vía POST /auth/refresh_token.
    - El refresh_token ROTA en cada refresh → se guarda el nuevo.
    - `HEVY_BEARER_TOKEN` en .env queda como override manual opcional.
    """

    DATA_DIR = Path("data")
    TOKEN_FILE = DATA_DIR / "hevy_token.json"

    def __init__(self):
        self.base_url = os.getenv("HEVY_BASE_URL", "https://api.hevyapp.com").rstrip("/")
        self.api_key = os.getenv("HEVY_API_KEY", "shelobs_hevy_web")
        self.username = os.getenv("HEVY_USERNAME")
        self.session = requests.Session()
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)

        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.expires_at: Optional[datetime] = None

        self._load_tokens()
        # bootstrap del refresh_token desde .env si no había token file
        if not self.refresh_token:
            self.refresh_token = os.getenv("HEVY_REFRESH_TOKEN")
        # override manual de access_token (opcional)
        override = os.getenv("HEVY_BEARER_TOKEN")
        if override:
            self.access_token = override
            self.expires_at = None  # expiry desconocido → válido hasta un 401

        self._build_headers()

    # ---------- persistencia de tokens ----------
    def _load_tokens(self):
        if self.TOKEN_FILE.exists():
            try:
                with open(self.TOKEN_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                self.access_token = d.get("access_token") or d.get("token")
                self.refresh_token = d.get("refresh_token")
                self.expires_at = self._parse_dt(d.get("expires_at"))
            except Exception:
                logger.debug("No pude leer el token file", exc_info=True)

    def _save_tokens(self):
        try:
            with open(self.TOKEN_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "access_token": self.access_token,
                        "refresh_token": self.refresh_token,
                        "expires_at": self.expires_at.isoformat() if self.expires_at else None,
                    },
                    f,
                )
        except Exception:
            logger.exception("No pude guardar los tokens")

    @staticmethod
    def _parse_dt(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

    def _token_expired(self, margin_seconds: int = 60) -> bool:
        if not self.access_token:
            return True
        if self.expires_at is None:
            return False  # expiry desconocido (override manual) → asumir válido hasta 401
        return (self.expires_at - datetime.now(timezone.utc)).total_seconds() <= margin_seconds

    def _build_headers(self):
        headers = {"x-api-key": self.api_key, "hevy-platform": "web", "accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        self.session.headers.update(headers)

    # ---------- refresh ----------
    def refresh(self) -> str:
        """Renueva el access_token vía POST /auth/refresh_token y guarda el refresh_token rotado."""
        if not self.refresh_token:
            raise TokenExpiredError(
                "No hay refresh_token. Pegá HEVY_REFRESH_TOKEN en el .env (una vez, del navegador)."
            )
        url = f"{self.base_url}/auth/refresh_token"
        headers = {
            "x-api-key": self.api_key,
            "hevy-platform": "web",
            "content-type": "application/json",
            "accept": "application/json",
        }
        resp = self.session.post(url, json={"refresh_token": self.refresh_token}, headers=headers)
        if resp.status_code not in (200, 201):
            raise TokenExpiredError(
                f"Refresh falló ({resp.status_code}). El refresh_token pudo expirar/rotar: "
                "pegá uno nuevo del navegador en HEVY_REFRESH_TOKEN del .env."
            )
        d = resp.json()
        self.access_token = d.get("access_token")
        if d.get("refresh_token"):
            self.refresh_token = d["refresh_token"]  # ROTA: guardar el nuevo o el próximo falla
        self.expires_at = self._parse_dt(d.get("expires_at"))
        self._save_tokens()
        self._build_headers()
        return self.access_token

    def _ensure_token(self):
        if self._token_expired():
            self.refresh()

    def _request(self, method: str, path: str, retry_on_unauth: bool = True, **kwargs) -> Any:
        self._ensure_token()
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        resp = self.session.request(method, url, **kwargs)
        if resp.status_code in (401, 403):
            if retry_on_unauth and self.refresh_token:
                try:
                    self.refresh()
                    return self._request(method, path, retry_on_unauth=False, **kwargs)
                except Exception:
                    pass
            raise TokenExpiredError(
                "No pude autenticar. Pegá un HEVY_REFRESH_TOKEN nuevo del navegador en el .env."
            )
        resp.raise_for_status()
        try:
            return resp.json()
        except ValueError:
            return resp.text

    # ---------- endpoints ----------
    def get_user_profile(self, username: Optional[str] = None) -> Dict:
        username = username or self.username
        if not username:
            raise ValueError("username required (HEVY_USERNAME in .env or pass as arg)")
        return self._request("GET", f"/user_profile/{username}")

    def get_workout(self, short_id: str) -> Dict:
        return self._request("GET", f"/workout/{short_id}")

    def get_workouts_page(self, username: Optional[str] = None, limit: int = 5, offset: int = 0) -> List[Dict]:
        """Trae UNA página de workouts (para fetch incremental). La API viene de nuevo→viejo."""
        username = username or self.username
        if not username:
            raise ValueError("username required (HEVY_USERNAME in .env or pass as arg)")
        endpoint = os.getenv("HEVY_WORKOUTS_ENDPOINT") or "/user_workouts_paged"
        r = self._request("GET", endpoint, params={"username": username, "limit": limit, "offset": offset})
        if isinstance(r, list):
            return r
        if isinstance(r, dict):
            for k in ("workouts", "items", "results", "data"):
                if k in r and isinstance(r[k], list):
                    return r[k]
        return []

    def list_user_workouts(self, username: Optional[str] = None, max_pages: int = 40, limit: int = 5) -> Tuple[List[Dict], str]:
        """Lista todos los workouts paginando (limit/offset). Devuelve (lista, endpoint)."""
        username = username or self.username
        if not username:
            raise ValueError("username required (HEVY_USERNAME in .env or pass as arg)")
        endpoint = os.getenv("HEVY_WORKOUTS_ENDPOINT") or "/user_workouts_paged"
        items: List[Dict] = []
        offset = 0
        for _ in range(max_pages):
            page = self.get_workouts_page(username=username, limit=limit, offset=offset)
            if not page:
                break
            items.extend(page)
            if len(page) < limit:
                break
            offset += limit
        if items:
            return items, f"{endpoint}?username={username}&limit={limit}"
        raise RuntimeError("No se obtuvieron workouts. Revisá HEVY_USERNAME (handle) y el token.")
