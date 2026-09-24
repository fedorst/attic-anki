"""Validate deck files: python tools/validate_deck.py [deck_dir]

Checks structure, the {answer}/[gloss] markers, form tags and id uniqueness.
It can't check that the Estonian is right; that part still needs a human.
"""

import json
import re
import sys
from pathlib import Path

POS = {"noun", "verb", "adj", "adv", "pron", "num", "conj", "post", "prep", "intj", "other"}

CASES = {"nom", "gen", "part", "ill", "in", "el", "all", "ad", "abl", "tr", "ter", "es", "ab", "kom"}
NUMBERS = {"sg", "pl"}
PERSONS = {"1sg", "2sg", "3sg", "1pl", "2pl", "3pl"}
TENSES = {"pres", "past", "cond", "imper", "quot"}
# Standalone verb forms: infinitives, participles, negation, impersonal, etc.
VERB_FORMS = {
    "ma-inf", "da-inf", "mas", "mast", "maks", "des", "mata",
    "nud", "tud", "v", "neg", "impers", "impers-past", "impers-neg",
}
DEGREES = {"comp", "sup"}
SHORT = {"short"}  # short illative (majja, kooli)

EXAMPLE_KEYS = {"et", "en", "form", "accept"}
WORD_KEYS = {"id", "lemma", "pos", "en", "forms", "note", "examples"}


def valid_form(tag: str) -> bool:
    """Accept '', 'part sg', 'comp nom sg', 'short ill sg', 'pres 1sg', 'neg', 'ma-inf', ..."""
    if tag == "":
        return True
    tokens = tag.split()
    if len(tokens) == 1 and tokens[0] in VERB_FORMS:
        return True
    if len(tokens) == 2 and tokens[0] in TENSES and tokens[1] in PERSONS:
        return True
    if len(tokens) == 2 and tokens[0] in ("pres", "past", "cond") and tokens[1] == "neg":
        return True
    # nominal: [comp|sup|short] case number
    if tokens and tokens[0] in DEGREES | SHORT:
        tokens = tokens[1:]
    return len(tokens) == 2 and tokens[0] in CASES and tokens[1] in NUMBERS


def validate_word(w, where, errors):
    extra = set(w) - WORD_KEYS
    if extra:
        errors.append(f"{where}: unknown keys {sorted(extra)}")
    for key in ("id", "lemma", "pos", "en"):
        if not isinstance(w.get(key), str) or not w[key].strip():
            errors.append(f"{where}: missing '{key}'")
    if w.get("pos") not in POS:
        errors.append(f"{where}: bad pos {w.get('pos')!r}")
    forms = w.get("forms")
    if not isinstance(forms, list) or not all(isinstance(f, str) for f in forms):
        errors.append(f"{where}: 'forms' must be a list of strings")
    elif w.get("pos") in ("noun", "adj", "pron", "num", "verb") and len(forms) != 4:
        errors.append(f"{where}: {w.get('pos')} needs 4 principal parts, got {len(forms)}")
    examples = w.get("examples")
    if not isinstance(examples, list) or len(examples) < 2:
        errors.append(f"{where}: needs at least 2 examples")
        return
    seen = set()
    for i, ex in enumerate(examples):
        at = f"{where} ex{i}"
        extra = set(ex) - EXAMPLE_KEYS
        if extra:
            errors.append(f"{at}: unknown keys {sorted(extra)}")
        et, en = ex.get("et", ""), ex.get("en", "")
        if len(re.findall(r"\{[^{}]+\}", et)) != 1 or et.count("{") != 1:
            errors.append(f"{at}: 'et' needs exactly one {{answer}}: {et!r}")
        if len(re.findall(r"\[[^\[\]]+\]", en)) != 1 or en.count("[") != 1:
            errors.append(f"{at}: 'en' needs exactly one [gloss]: {en!r}")
        if not valid_form(ex.get("form", "")):
            errors.append(f"{at}: bad form tag {ex.get('form')!r}")
        accept = ex.get("accept", [])
        if not isinstance(accept, list) or not all(isinstance(a, str) and a for a in accept):
            errors.append(f"{at}: 'accept' must be a list of non-empty strings")
        if et in seen:
            errors.append(f"{at}: duplicate sentence")
        seen.add(et)


def validate(deck_dir: Path) -> list[str]:
    errors, ids = [], {}
    files = sorted(deck_dir.glob("*.json"))
    if not files:
        errors.append(f"no deck files in {deck_dir}")
    for path in files:
        try:
            words = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"{path.name}: invalid JSON: {e}")
            continue
        if not isinstance(words, list):
            errors.append(f"{path.name}: top level must be a list")
            continue
        for n, w in enumerate(words):
            where = f"{path.name}[{n}] {w.get('id', '?')}"
            validate_word(w, where, errors)
            if w.get("id") in ids:
                errors.append(f"{where}: duplicate id (also in {ids[w['id']]})")
            ids[w.get("id")] = path.name
    return errors


def main():
    deck_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "decks" / "et-en"
    errors = validate(deck_dir)
    for e in errors:
        print(e)
    n_words = sum(len(json.loads(p.read_text(encoding="utf-8"))) for p in deck_dir.glob("*.json")) if not errors else 0
    print(f"{len(errors)} error(s)" if errors else f"OK: {n_words} words")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
