from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SetEntry:
    weight_kg: Optional[float]
    reps: Optional[int]
    rpe: Optional[float] = None
    is_pr: Optional[bool] = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        # PR desde varias formas: 'pr' (simplificado), 'prs'/'personalRecords' (crudo), 'is_pr'
        is_pr = bool(d.get("pr")) or bool(d.get("prs")) or bool(d.get("personalRecords")) or bool(d.get("is_pr"))
        return cls(
            weight_kg=d.get("weight_kg") or d.get("weight"),
            reps=d.get("reps"),
            rpe=d.get("rpe"),
            is_pr=is_pr,
        )


@dataclass
class ExerciseEntry:
    title: str  # inglés
    es_title: Optional[str] = None  # español
    muscle_group: Optional[str] = None
    equipment: Optional[str] = None
    sets: List[SetEntry] = field(default_factory=list)

    @property
    def name(self) -> str:
        # nombre combinado (es + en) para buscar en cualquiera de los dos idiomas
        parts = [p for p in [self.es_title, self.title] if p]
        return " ".join(parts).strip()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        sets = [SetEntry.from_dict(s) for s in d.get("sets", [])]
        # crudo: title (en) + es_title · simplificado: name (es) + name_en (en)
        es = d.get("es_title") or d.get("name")
        en = d.get("title") or d.get("name_en")
        return cls(
            title=en or "",
            es_title=es,
            muscle_group=d.get("muscle_group"),
            equipment=d.get("equipment") or d.get("equipment_category"),
            sets=sets,
        )


@dataclass
class Workout:
    short_id: str
    date: str
    exercises: List[ExerciseEntry] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        exercises = [ExerciseEntry.from_dict(ex) for ex in (d.get("exercises") or [])]
        return cls(
            short_id=d.get("short_id") or d.get("id") or "",
            date=d.get("date") or d.get("created_at") or "",
            exercises=exercises,
            raw=d,
        )
