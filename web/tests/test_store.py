import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from store import Store, day_start  # noqa: E402
from validate_deck import valid_form, validate  # noqa: E402

T0 = datetime(2026, 9, 24, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db", ROOT / "decks" / "et-en")
    s.update_settings({"new_per_day": 5})
    return s


def test_shipped_deck_is_valid():
    assert validate(ROOT / "decks" / "et-en") == []


def test_form_tags():
    for ok in ["", "part sg", "comp nom sg", "short ill sg", "pres 1sg", "past neg", "ma-inf", "impers"]:
        assert valid_form(ok), ok
    for bad in ["partitive", "pres", "nom", "ill sg pl", "pres 4sg"]:
        assert not valid_form(bad), bad


def test_example_parts(store):
    ex = store.words[0].examples[0].parts()
    assert ex["before"] + "{" + ex["answer"] + "}" + ex["after"] == store.words[0].examples[0].et
    assert "{" not in ex["plain"] and "[" not in ex["plain_en"]


def test_new_words_come_in_deck_order_and_respect_daily_limit(store):
    seen = []
    at = T0
    for _ in range(5):
        card = store.next_card(0, at=at)["card"]
        assert card["is_new"]
        seen.append(card["word"]["id"])
        store.review(card["word"]["id"], card["example_idx"], "correct", at=at)
        at += timedelta(seconds=5)
    assert seen == [w.id for w in store.words[:5]]
    # All five were "correct" on first sight -> Easy -> days away; limit reached -> nothing left.
    res = store.next_card(0, at=at)
    assert res["card"] is None
    assert res["counts"]["new_left"] == 0

    store.learn_more(0, amount=2)
    assert store.next_card(0, at=at)["counts"]["new_left"] == 2


def test_wrong_answer_comes_back_soon_with_next_example(store):
    card = store.next_card(0, at=T0)["card"]
    wid = card["word"]["id"]
    res = store.review(wid, card["example_idx"], "wrong", at=T0)
    assert res["rating"] == "again" and res["state"] == "learning"
    assert datetime.fromisoformat(res["due"]) - T0 < timedelta(minutes=15)

    # Right after, it's excluded (to avoid immediate repeats) and a new word is shown instead.
    nxt = store.next_card(0, exclude=wid, at=T0 + timedelta(seconds=10))["card"]
    assert nxt["word"]["id"] != wid

    # Once due, it comes back - with a different sentence.
    later = store.next_card(0, at=T0 + timedelta(minutes=2))["card"]
    assert later["word"]["id"] == wid
    assert later["example_idx"] == (card["example_idx"] + 1) % len(store.by_id[wid].examples)
    assert not later["is_new"]


def test_learning_card_pulled_forward_when_nothing_else(store):
    store.update_settings({"new_per_day": 1})
    card = store.next_card(0, at=T0)["card"]
    store.review(card["word"]["id"], card["example_idx"], "wrong", at=T0)
    # Not due yet (1 min step), no new words left -> pulled forward via learn-ahead.
    res = store.next_card(0, at=T0 + timedelta(seconds=20))
    assert res["card"]["word"]["id"] == card["word"]["id"]


def test_intervals_grow_with_successful_reviews(store):
    wid = store.words[0].id
    at = T0
    store.review(wid, 0, "wrong", at=at)
    intervals = []
    for _ in range(5):
        at = datetime.fromisoformat(store.review(wid, 0, "correct", at=at)["due"])
        intervals.append(at)
    gaps = [(b - a).total_seconds() for a, b in zip(intervals, intervals[1:])]
    assert all(g2 > g1 for g1, g2 in zip(gaps, gaps[1:]))


def test_stats_and_streak(store):
    for d in range(3):
        at = T0 - timedelta(days=d)
        card = store.next_card(0, at=at)["card"]
        store.review(card["word"]["id"], card["example_idx"], "correct", at=at)
    st = store.stats(0, at=T0)
    assert st["streak"] == 3
    assert st["today"]["reviews"] == 1
    assert st["seen"] == 3
    assert len(st["history"]) == 30 and len(st["forecast"]) == 14


def test_day_start_respects_timezone():
    at = datetime(2026, 9, 24, 22, 30, tzinfo=timezone.utc)  # 01:30 next day in Tallinn (UTC+3)
    assert day_start(at, 180) == datetime(2026, 9, 24, 21, 0, tzinfo=timezone.utc)
    assert day_start(at, 0) == datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)


def test_bad_review_input(store):
    with pytest.raises(KeyError):
        store.review("no-such-word", 0, "correct")
    with pytest.raises(ValueError):
        store.review(store.words[0].id, 0, "meh")
