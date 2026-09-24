# Sõnad: spec, roadmap and ideas

Status: v0.1, a working single-user MVP with 200 words. This document says what
we're building, how the spaced repetition is meant to work, where content should
come from, and what to build next.

## 1. Goal

An English speaker can go from zero to understanding everyday Estonian text
(≈ B1, about 3,000 lemmas) in 10–20 minutes a day. That needs two things:

1. **Spaced repetition does the scheduling.** The learner never decides what to
   review. Each session is "today's due words + a few new ones", and FSRS keeps
   each word near the target recall (default 90%) with as few reviews as
   possible.
2. **Words are learned in context, in their real forms.** For Estonian, recalling
   a lemma is not enough. You need *raamatut*, *raamatus*, *raamatuid*. Cloze
   sentences that require the inflected form practise vocabulary and morphology
   together. That's why Estonian suits this format better than English or
   Spanish, and it's the reason to prefer it over plain flashcards.

Non-goals for now: speaking practice, full grammar course, social features.

## 2. Core model

| Concept | Definition |
|---|---|
| **Word** | lemma + sense (`saama` "get/can/become" is one word; a homonym with a different meaning gets its own id). The unit of scheduling. |
| **Example** | a sentence pair: Estonian with one `{answer}`, English with one `[gloss]`, a form tag (`part pl`, `past 3sg`, …), and optional accepted variants. A word has 3–5 today; target is 6–10. |
| **Card state** | one FSRS card per word (stability, difficulty, due, state), stored as JSON in SQLite. |
| **Review** | one attempt: word, example shown, outcome, first answer typed, response time, timestamp. This is the full log FSRS needs to be re-fitted later. |

### Why one card per word and not per sentence

With per-sentence cards, one word learned in five sentences would be reviewed
five times as often, and FSRS would model memory of *sentences*. Per-word
cards with rotating examples model the thing we care about: can you produce
this word in a context you haven't memorised?

The cost is that a form error ("I know *raamat* but wrote *raamatu* instead of
*raamatut*") counts against the word. The fix is planned in §5.3: track
grammar skill per form tag, separately from FSRS.

### Grading (typed answer → FSRS rating)

The learner never presses Again/Hard/Good/Easy. The grade comes from what they
typed:

| What happened | Rating |
|---|---|
| New word, right first try, no hint | Easy (already known) |
| Right first try, no hint | Good |
| Right after hints, or only diacritics wrong | Hard |
| Wrong or empty (then retyped) | Again |
| Wrong, but learner clicks "I made a typo" | Good (Hard if hints were used) |

Still to add: use response time. A correct answer typed in under ~3 s could be
Easy, and one that took 20 s could be Hard. The data is already logged in
`reviews.duration_ms`, so the thresholds can be tuned per user before this ships.

### Queue

1. Learning/relearning cards that are due (short steps: 1 min, 10 min).
2. Review cards that are due, most overdue first.
3. New words, in deck order, up to the daily limit. While reviews are waiting,
   every 4th card is new, so a backlog doesn't block progress entirely.
4. If nothing is due, a learning card due within 20 minutes is pulled forward.
5. Otherwise: "done", with a "learn 10 more" button.

The same word is never shown twice in a row.

## 3. User flows

### 3.1 Daily session (built)
Open the app. The top bar shows done / due / new for today. Cards come one at a
time, with Enter to check and Enter to continue, and the hands never leave the
keyboard. The progress bar fills toward "today's work". The done screen shows
the next due time and a "learn more" button.

### 3.2 First run / placement (planned, high priority)
Someone who already knows some Estonian shouldn't grind through *ma olen*.
Placement:

1. Show 30–40 cards sampled across frequency bands (e.g. 5 each from ranks
   1–100, 100–300, 300–600, …).
2. Stop the ramp when accuracy in a band drops below ~50%.
3. Words in bands the learner passed are seeded as known, with a single *Easy*
   review backdated to today, so FSRS gives them a sensible first interval
   instead of teaching them as new. Later reviews correct any mistakes.

### 3.3 Word lookup (built: Words tab)
Search by Estonian (any form listed) or English. Each row shows status, recall
probability and next review. Expanding a row shows the forms, note and all
examples.

### 3.4 "This sentence is wrong" (planned, high priority)
A flag button on every card: *wrong translation / unnatural / ambiguous blank /
other*. Flagged examples are skipped for that user and collected for editing.
With a generated corpus this is the most important quality loop.

### 3.5 Leeches (planned)
A word that lapses 6+ times is a *leech*. Instead of repeating the same drill,
show it with its full paradigm, all examples, and an optional learner-written
mnemonic. Offer to suspend it for a week.

### 3.6 Coming back after a break (planned)
If 200 words are overdue, don't show "200 due". Cap reviews per day (setting,
default 100), order the backlog by *lowest current retrievability relative to
stability* (the words most at risk of being lost), and pause new words until
the backlog is under control.

## 4. Content: more words, better sentences

The 200 hand-written words (≈ 670 sentences) show the quality target. Getting
to 3,000+ words with 6–10 sentences each needs a pipeline. Quality beats
quantity: one unnatural sentence costs more trust than ten missing ones.

### 4.1 Sources

Licences below are unverified. Check each one before using it.

| Need | Source | Notes |
|---|---|---|
| **Which words, in what order** | *Eesti keele sagedussõnastik* (Kaalep & Muischnek), frequency lists from the Estonian National Corpus (EKI / Sketch Engine), CEFR level vocabulary lists (A1–B2 *tasemesõnavara*, used for the state language exams) | Order by CEFR level first, then frequency within a level. Pure corpus frequency puts *aasta*, *kroon* and *valitsus* too early and *leib* too late. |
| **Real sentences** | Tatoeba (est–eng pairs, CC BY), Leipzig Corpora Collection Estonian news/web sentences, OpenSubtitles (spoken register, but check licence and quality), EKI dictionary examples (Sõnaveeb, the basic vocabulary dictionary *Eesti keele põhisõnavara sõnastik*) | Dictionary examples are short, clean and graded, the best source if licensing allows. |
| **Morphology** | [EstNLTK](https://github.com/estnltk/estnltk) / Vabamorf: analysis (lemma + form of every token) and **synthesis** (generate any form of a lemma) | Makes tagging automatic and checkable, see 4.3. |
| **Translations** | Human pairs where they exist (Tatoeba); otherwise LLM translation with review | |
| **Audio** | TartuNLP's neural Estonian TTS (Neurokõne), pre-generated per sentence | Browser TTS rarely has an Estonian voice. |

### 4.2 Pipeline (to build in `web/tools/`)

```
lemma list (CEFR + frequency)
   │
   ├─► candidate sentences: corpus search for any form of the lemma
   │      filter: 4–12 tokens; every *other* token is in the top-N lemmas
   │      (N ≈ learner level); no names/numbers-heavy; not a fragment
   │
   ├─► or LLM-generate candidates for gaps ("5 everyday sentences using
   │      `raamat` in partitive pl, genitive sg, inessive…")
   │
   ├─► analyse with Vabamorf → form tag of the answer, and ambiguity check
   │      (if the blank could be two different forms that both fit, drop it
   │      or add to `accept`)
   │
   ├─► translate (human pair or LLM), mark [gloss]
   │
   ├─► automatic checks: validate_deck.py + Vabamorf re-synthesis of the tag
   │      + an LLM "strict native editor" pass that scores naturalness
   │
   └─► human review queue: accept / edit / reject  →  decks/et-en/*.json
```

Two properties matter most for spaced repetition:

* **Comprehensible input (i+1).** A sentence should contain only one word the
  learner doesn't know: the blank. When choosing an example at review time,
  prefer sentences whose other words are all already known *by this learner*
  (FSRS state is available). This is how SRS data improves the examples, and
  it's cheap to do in `store._card_payload`.
* **Form coverage.** Each word's examples should span its most frequent forms
  (corpus-weighted), so rotating through them trains the paradigm.

### 4.3 Automatic quality checks (cheap wins)
- Re-synthesise each tagged answer with Vabamorf: `synth(lemma, tag)` must
  contain the answer. This catches wrong tags and misspellings.
- Check principal parts (`forms`) against the synthesiser.
- Flag any sentence where the answer also appears elsewhere in the sentence.
- Flag English glosses with more than 4 words (probably a bad bracket).

### 4.4 Literary / parallel texts
Classic translations are good for a later *reading mode* (§5.4), not as cloze
sources. Their language is often dated or idiosyncratic (e.g. Aavik's coinages),
their sentences are long, and many are still under copyright (in Estonia, life
+ 70 years). Short modern sentences make better drill material.

## 5. Feature ideas, by value for the effort

### 5.1 Next up
1. **Placement test** (§3.2).
2. **Report sentence** (§3.4).
3. **Audio**: pre-generated neural TTS for every sentence. Play it after
   answering, and add a listening card type: hear the sentence, type the
   missing word.
4. **Personal FSRS parameters**: after ~1,000 reviews, fit the 21 parameters to
   the user's own log (`pip install "fsrs[optimizer]"`, `Optimizer(review_logs)`),
   typically a noticeable efficiency gain. `/api/export` already has the data.
5. **Accounts + deploy**: magic-link login, one SQLite file per user (or
   Postgres), served behind Caddy. Make it an installable **PWA** with an
   offline queue: download today's cards and sync reviews when back online.

### 5.2 Better drills
- **i+1 example selection** (§4.2).
- **Varied cloze direction**: sometimes blank the English and show all the
  Estonian (comprehension), sometimes Estonian → type the lemma.
- **"Why this form?"** When an answer has the right lemma but the wrong form,
  say so explicitly: "right word, wrong case: you wrote genitive, this needs
  partitive because of negation". Vabamorf can analyse the typo.
- **Paradigm table** for each word from the synthesiser (all 28 noun forms,
  main verb forms) in the word detail view.

### 5.3 Grammar skill model
Track accuracy per form tag (e.g. `part pl` 62%, `ill sg` 91%) separately from
FSRS. Use it to:
- choose which example of a due word to show (a weak form, when the word itself
  is well known),
- show a "grammar" panel in Progress: your weakest cases, with a short
  explanation and a "drill partitive plural" mini-session built from words the
  learner already knows.

### 5.4 Later
- **Graded reading**: short texts (news-style, dialogues) where every unknown
  word is tappable and "add to my deck" creates a card with the sentence as its
  example. This connects SRS to real input.
- **Fresh sentences for mature words**: once a word is stable (e.g. >60 days),
  generate a new sentence at review time with an LLM, validated with Vabamorf,
  so the learner can't be recognising the sentence instead of recalling the word.
- **Other language pairs**: the engine is language-agnostic. `decks/<pair>/`
  plus a form-tag vocabulary is all that's needed (Finnish, or the original
  Attic Greek ↔ Estonian data in this repo).
- **Load balancing / easy days**: spread reviews so no day spikes; option to
  make weekends lighter.

## 6. Roadmap

| Milestone | Scope | Done when |
|---|---|---|
| **M0 MVP** ✅ | cloze UI, FSRS, 200 words, stats, word list, settings, export | this commit |
| **M1 Content ×5** | pipeline §4.2 (Vabamorf checks, candidate mining, LLM draft + review tool), 1,000 words (A1–A2), 6+ examples each | 1,000 words pass all automatic checks; 10% sample reviewed by a native speaker |
| **M2 Everyday usable** | report sentence, placement test, audio, backlog cap | a real learner uses it for 30 days without touching the code |
| **M3 Online** | accounts, deploy, PWA/offline, per-user FSRS optimisation | usable on a phone, progress synced |
| **M4 Depth** | grammar skill model, i+1 selection, "why this form?", 3,000 words (B1) | |
| **M5 Input** | graded reading, fresh generated sentences | |

## 7. Open questions
- Should the English gloss of the lemma (*"am — to be"*) be shown on review
  cards too, or only when a word is new? It is currently new-only, to keep
  reviews about recall.
- Is showing the form tag by default too much help? It's a setting now. Data
  from `reviews` (accuracy with vs. without) could decide the default.
- Short vs long illative, *ma*/*mina*, and similar pairs: accept both
  everywhere, or teach one? Currently the common one is the answer and the
  other is accepted.
