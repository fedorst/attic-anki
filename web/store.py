"""Deck loading, progress storage (SQLite) and FSRS scheduling.

The unit FSRS schedules is a *word*. Each word has several example sentences;
every review shows the next one in rotation, so the word gets practised in
different inflected forms instead of one memorised sentence.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fsrs import Card, Rating, Scheduler, State

DEFAULT_SETTINGS = {
    "new_per_day": 15,
    "desired_retention": 0.9,
    "show_form": True,
    "auto_speak": False,
}

# How far ahead we'll pull a learning card forward when nothing else is due.
LEARN_AHEAD = timedelta(minutes=20)
# While reviews are waiting, every Nth card is a new word (so new words don't stall behind a backlog).
NEW_EVERY = 4

OUTCOME_TO_RATING = {"wrong": Rating.Again, "hard": Rating.Hard, "correct": Rating.Good}


@dataclass
class Example:
    et: str
    en: str
    form: str
    accept: list[str]

    def parts(self) -> dict:
        et_before, answer, et_after = re.match(r"(.*)\{([^{}]+)\}(.*)", self.et, re.S).groups()
        en_before, gloss, en_after = re.match(r"(.*)\[([^\[\]]+)\](.*)", self.en, re.S).groups()
        return {
            "before": et_before, "answer": answer, "after": et_after,
            "en_before": en_before, "en_gloss": gloss, "en_after": en_after,
            "form": self.form, "accept": self.accept,
            "plain": self.et.replace("{", "").replace("}", ""),
            "plain_en": self.en.replace("[", "").replace("]", ""),
        }


@dataclass
class Word:
    id: str
    lemma: str
    pos: str
    en: str
    forms: list[str]
    note: str
    examples: list[Example]
    band: str
    order: int

    def summary(self) -> dict:
        return {"id": self.id, "lemma": self.lemma, "pos": self.pos, "en": self.en,
                "forms": self.forms, "note": self.note, "band": self.band}


def load_deck(deck_dir: Path) -> list[Word]:
    words = []
    for path in sorted(deck_dir.glob("*.json")):
        band = re.sub(r"^\d+-", "", path.stem)
        for raw in json.loads(path.read_text(encoding="utf-8")):
            words.append(Word(
                id=raw["id"], lemma=raw["lemma"], pos=raw["pos"], en=raw["en"],
                forms=raw.get("forms", []), note=raw.get("note", ""),
                examples=[Example(e["et"], e["en"], e.get("form", ""), e.get("accept", []))
                          for e in raw["examples"]],
                band=band, order=len(words),
            ))
    return words


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def day_start(at: datetime, tz_minutes: int) -> datetime:
    """UTC instant of local midnight for the day containing `at`, given a UTC offset in minutes."""
    local = at + timedelta(minutes=tz_minutes)
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(minutes=tz_minutes)


SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    word_id      TEXT PRIMARY KEY,
    fsrs         TEXT NOT NULL,           -- fsrs.Card.to_dict() as JSON
    due          TEXT NOT NULL,           -- copy of fsrs due, for querying
    state        INTEGER NOT NULL,        -- copy of fsrs state (1 learning, 2 review, 3 relearning)
    next_example INTEGER NOT NULL DEFAULT 0,
    introduced   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    word_id      TEXT NOT NULL,
    example_idx  INTEGER NOT NULL,
    rating       INTEGER NOT NULL,
    outcome      TEXT NOT NULL,
    answer       TEXT NOT NULL DEFAULT '',
    duration_ms  INTEGER,
    was_new      INTEGER NOT NULL,
    reviewed_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS reviews_at ON reviews(reviewed_at);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class Store:
    def __init__(self, db_path: str | Path, deck_dir: str | Path):
        self.words = load_deck(Path(deck_dir))
        self.by_id = {w.id: w for w in self.words}
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    # ---- settings -------------------------------------------------------

    def settings(self) -> dict:
        rows = self.db.execute("SELECT key, value FROM settings").fetchall()
        stored = {r["key"]: json.loads(r["value"]) for r in rows}
        return {k: stored.get(k, v) for k, v in DEFAULT_SETTINGS.items()} | {
            k: v for k, v in stored.items() if k.startswith("extra_new_")}

    def update_settings(self, changes: dict) -> dict:
        clean = {}
        if "new_per_day" in changes:
            clean["new_per_day"] = max(0, min(200, int(changes["new_per_day"])))
        if "desired_retention" in changes:
            clean["desired_retention"] = max(0.7, min(0.97, float(changes["desired_retention"])))
        for key in ("show_form", "auto_speak"):
            if key in changes:
                clean[key] = bool(changes[key])
        with self.lock:
            for k, v in clean.items():
                self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (k, json.dumps(v)))
            self.db.commit()
        return self.settings()

    def scheduler(self) -> Scheduler:
        return Scheduler(desired_retention=self.settings()["desired_retention"])

    # ---- queue ----------------------------------------------------------

    def _new_today(self, since: datetime) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM cards WHERE introduced >= ?", (since.isoformat(),)).fetchone()[0]

    def _reviews_today(self, since: datetime) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM reviews WHERE reviewed_at >= ?", (since.isoformat(),)).fetchone()[0]

    def _new_limit(self, today: datetime) -> int:
        s = self.settings()
        return s["new_per_day"] + int(s.get(f"extra_new_{today.date().isoformat()}", 0))

    def learn_more(self, tz_minutes: int, amount: int = 10) -> None:
        """Raise today's new-word limit (the 'keep going' button)."""
        key = f"extra_new_{day_start(now_utc(), tz_minutes).date().isoformat()}"
        with self.lock:
            current = self.settings().get(key, 0)
            self.db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(current + amount)))
            self.db.commit()

    def _next_new_word(self) -> Word | None:
        seen = {r[0] for r in self.db.execute("SELECT word_id FROM cards")}
        return next((w for w in self.words if w.id not in seen), None)

    def counts(self, tz_minutes: int, at: datetime | None = None) -> dict:
        at = at or now_utc()
        today = day_start(at, tz_minutes)
        known = {wid for (wid,) in self.db.execute("SELECT word_id FROM cards")}
        due = self.db.execute(
            "SELECT COUNT(*) FROM cards WHERE due <= ?", (at.isoformat(),)).fetchone()[0]
        unseen = sum(1 for w in self.words if w.id not in known)
        new_left = max(0, min(unseen, self._new_limit(today) - self._new_today(today)))
        return {"due": due, "new_left": new_left, "reviewed_today": self._reviews_today(today),
                "unseen": unseen, "total": len(self.words)}

    def next_card(self, tz_minutes: int, exclude: str | None = None, at: datetime | None = None) -> dict:
        at = at or now_utc()
        counts = self.counts(tz_minutes, at)
        due_rows = self.db.execute(
            "SELECT word_id, state, due FROM cards WHERE due <= ? AND word_id != ? ORDER BY due",
            (at.isoformat(), exclude or "")).fetchall()
        # Short-term (learning) steps first: they're the ones that decay within minutes.
        due_rows = sorted(due_rows, key=lambda r: (r["state"] == State.Review, r["due"]))
        want_new = counts["new_left"] > 0 and (
            not due_rows or counts["reviewed_today"] % NEW_EVERY == NEW_EVERY - 1)

        word = None
        if want_new:
            word = self._next_new_word()
        if word is None and due_rows:
            word = self.by_id.get(due_rows[0]["word_id"])
        if word is None:
            # Nothing due: pull a learning card forward if it's close, rather than idling.
            row = self.db.execute(
                "SELECT word_id, due FROM cards WHERE state != ? AND due <= ? AND word_id != ? ORDER BY due LIMIT 1",
                (State.Review, (at + LEARN_AHEAD).isoformat(), exclude or "")).fetchone()
            if row:
                word = self.by_id.get(row["word_id"])
        if word is None:
            nxt = self.db.execute("SELECT MIN(due) FROM cards").fetchone()[0]
            return {"card": None, "counts": counts, "next_due": nxt}
        return {"card": self._card_payload(word), "counts": counts}

    def _card_payload(self, word: Word) -> dict:
        row = self.db.execute("SELECT * FROM cards WHERE word_id = ?", (word.id,)).fetchone()
        idx = (row["next_example"] if row else 0) % len(word.examples)
        payload = {
            "word": word.summary(),
            "example_idx": idx,
            "example": word.examples[idx].parts(),
            "others": [e.parts() for i, e in enumerate(word.examples) if i != idx],
            "is_new": row is None,
            "state": None,
        }
        if row:
            card = Card.from_dict(json.loads(row["fsrs"]))
            payload["state"] = {
                "state": card.state.name.lower(),
                "stability": card.stability,
                "difficulty": card.difficulty,
                "retrievability": self.scheduler().get_card_retrievability(card),
            }
        return payload

    # ---- reviewing ------------------------------------------------------

    def review(self, word_id: str, example_idx: int, outcome: str, answer: str = "",
               duration_ms: int | None = None, at: datetime | None = None) -> dict:
        if word_id not in self.by_id:
            raise KeyError(word_id)
        if outcome not in OUTCOME_TO_RATING:
            raise ValueError(f"bad outcome {outcome!r}")
        at = at or now_utc()
        word = self.by_id[word_id]
        with self.lock:
            row = self.db.execute("SELECT * FROM cards WHERE word_id = ?", (word_id,)).fetchone()
            was_new = row is None
            card = Card() if was_new else Card.from_dict(json.loads(row["fsrs"]))
            rating = OUTCOME_TO_RATING[outcome]
            if was_new and outcome == "correct":
                rating = Rating.Easy  # knew it before we ever taught it
            card, _log = self.scheduler().review_card(card, rating, review_datetime=at)
            next_example = (example_idx + 1) % len(word.examples)
            self.db.execute(
                """INSERT INTO cards (word_id, fsrs, due, state, next_example, introduced)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(word_id) DO UPDATE SET fsrs=excluded.fsrs, due=excluded.due,
                       state=excluded.state, next_example=excluded.next_example""",
                (word_id, json.dumps(card.to_dict()), card.due.isoformat(), int(card.state),
                 next_example, at.isoformat()))
            self.db.execute(
                """INSERT INTO reviews (word_id, example_idx, rating, outcome, answer, duration_ms, was_new, reviewed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (word_id, example_idx, int(rating), outcome, answer[:100], duration_ms, int(was_new), at.isoformat()))
            self.db.commit()
        return {"due": card.due.isoformat(), "state": card.state.name.lower(),
                "stability": card.stability, "rating": rating.name.lower()}

    # ---- overview -------------------------------------------------------

    def word_list(self) -> list[dict]:
        rows = {r["word_id"]: r for r in self.db.execute("SELECT * FROM cards")}
        sched = self.scheduler()
        out = []
        for w in self.words:
            item = w.summary() | {"examples": [e.parts() for e in w.examples], "status": "new"}
            if w.id in rows:
                card = Card.from_dict(json.loads(rows[w.id]["fsrs"]))
                item |= {
                    "status": card.state.name.lower(),
                    "due": card.due.isoformat(),
                    "stability": card.stability,
                    "retrievability": sched.get_card_retrievability(card),
                }
            out.append(item)
        return out

    def stats(self, tz_minutes: int, at: datetime | None = None) -> dict:
        at = at or now_utc()
        today = day_start(at, tz_minutes)
        offset = timedelta(minutes=tz_minutes)

        def local_day(iso: str) -> str:
            return (datetime.fromisoformat(iso) + offset).date().isoformat()

        by_day: dict[str, dict] = {}
        for r in self.db.execute(
                "SELECT reviewed_at, outcome, was_new FROM reviews WHERE reviewed_at >= ?",
                ((today - timedelta(days=365)).isoformat(),)):
            d = by_day.setdefault(local_day(r["reviewed_at"]), {"reviews": 0, "correct": 0, "new": 0})
            d["reviews"] += 1
            d["correct"] += r["outcome"] == "correct"
            d["new"] += r["was_new"]

        days = [(today - timedelta(days=i) + offset).date().isoformat() for i in range(29, -1, -1)]
        history = [{"day": d, **by_day.get(d, {"reviews": 0, "correct": 0, "new": 0})} for d in days]

        streak, i = 0, 0
        today_key = (today + offset).date().isoformat()
        if today_key not in by_day:
            i = 1  # today not done yet doesn't break the streak
        while (today - timedelta(days=i) + offset).date().isoformat() in by_day:
            streak += 1
            i += 1

        forecast = [0] * 14
        states = {"learning": 0, "review": 0, "relearning": 0}
        mature = 0
        for r in self.db.execute("SELECT fsrs, due, state FROM cards"):
            states[State(r["state"]).name.lower()] += 1
            card = json.loads(r["fsrs"])
            if (card.get("stability") or 0) >= 21:
                mature += 1
            days_out = (datetime.fromisoformat(r["due"]) - today).days
            if days_out < len(forecast):
                forecast[max(0, days_out)] += 1  # overdue counts as due today
        total = sum(h["reviews"] for h in history)
        return {
            "streak": streak,
            "today": by_day.get(today_key, {"reviews": 0, "correct": 0, "new": 0}),
            "accuracy_30d": (sum(h["correct"] for h in history) / total) if total else None,
            "reviews_30d": total,
            "history": history,
            "forecast": [{"day": (today + timedelta(days=i) + offset).date().isoformat(), "due": n}
                         for i, n in enumerate(forecast)],
            "states": states,
            "mature": mature,
            "seen": sum(states.values()),
            "total": len(self.words),
            "counts": self.counts(tz_minutes, at),
        }

    def export(self) -> dict:
        """Everything needed to back up progress or fit personal FSRS parameters later."""
        return {
            "cards": [dict(r) for r in self.db.execute("SELECT * FROM cards")],
            "reviews": [dict(r) for r in self.db.execute("SELECT * FROM reviews ORDER BY id")],
            "settings": self.settings(),
        }
