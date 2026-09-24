# Estonian → English deck

One JSON file per frequency band (`01-*.json` is learned first). Each file is a
list of **words**; the word is the unit FSRS schedules. Every word has several
example sentences, and each review picks a different one, so you learn the word
across its forms rather than memorising one sentence.

```jsonc
{
  "id": "olema",                 // unique across the whole deck, ascii-ish, stable forever (progress is keyed on it)
  "lemma": "olema",              // dictionary form
  "pos": "verb",                 // noun | verb | adj | adv | pron | num | conj | post | prep | intj | other
  "en": "to be",                 // short English gloss
  "forms": ["olema", "olla", "on", "oli"],   // principal parts (see below)
  "note": "Irregular: olen, oled, on, oleme, olete, on.",  // optional, shown after answering
  "examples": [
    {
      "et": "Ma {olen} täna kodus.",       // exactly one {…}: the answer, as it appears in the sentence
      "en": "I [am] at home today.",        // exactly one […]: the English words that correspond to it
      "form": "pres 1sg",                   // grammatical tag of the answer (vocabulary in tools/validate_deck.py)
      "accept": []                          // optional: other answers that are also correct here
    }
  ]
}
```

Principal parts (`forms`):

* nouns, adjectives, pronouns, numerals: nominative sg, genitive sg, partitive sg, partitive pl
  (`["sõna", "sõna", "sõna", "sõnu"]`)
* verbs: ma-infinitive, da-infinitive, present 3sg, past 3sg (`["tegema", "teha", "teeb", "tegi"]`)
* everything else: `[]`

Run `python tools/validate_deck.py` after editing.
