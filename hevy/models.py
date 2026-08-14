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
        return cls(
            weight_kg=d.get("weight_kg") or d.get("weight"),
            reps=d.get("reps"),
            rpe=d.get("rpe"),
            # API may report personal records using several keys: `is_pr`, `prs`, `personalRecords`
            is_pr=(bool(d.get("is_pr")) or bool(d.get("prs")) or bool(d.get("personalRecords")))
        )


@dataclass
class ExerciseEntry:
    # store both english and spanish titles when present
    title: str
    es_title: Optional[str] = None
    sets: List[SetEntry] = field(default_factory=list)

    @property
    def name(self) -> str:
        # combined name used for search/matching: contains both english and spanish
        parts = []
        if self.title:
            parts.append(self.title)
        if self.es_title:
            parts.append(self.es_title)
        return " ".join(parts).strip()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        sets = [SetEntry.from_dict(s) for s in d.get("sets", [])]
        # prefer explicit title fields; fall back to legacy `name` or `exercise` keys
        title = d.get("title") or d.get("name") or d.get("exercise") or ""
        es_title = d.get("es_title") or d.get("esTitle") or None
        return cls(title=title, es_title=es_title, sets=sets)


@dataclass
class Workout:
    short_id: str
    date: str
    exercises: List[ExerciseEntry] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]):
        exercises = []
        for ex in d.get("exercises", []) or d.get("exercise_list", []) or []:
            exercises.append(ExerciseEntry.from_dict(ex))
        return cls(short_id=d.get("short_id") or d.get("id") or "", date=d.get("date") or d.get("created_at") or "", exercises=exercises, raw=d)
