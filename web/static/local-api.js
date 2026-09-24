// In-browser backend for the static build (dist/sonad.html): same API as server.py,
// but the deck is embedded in the page, FSRS is ts-fsrs, and progress lives in localStorage.
// Mirrors store.py — keep the queue/grading rules in sync with it.

export function createLocalApi(rawDeck, FSRS) {
  const KEY = "sonad-progress-v1";
  const DEFAULTS = { new_per_day: 15, desired_retention: 0.9, show_form: true, auto_speak: false };
  const LEARN_AHEAD_MS = 20 * 60 * 1000;
  const NEW_EVERY = 4;
  const OUTCOME = { wrong: FSRS.Rating.Again, hard: FSRS.Rating.Hard, correct: FSRS.Rating.Good };
  const RATING_NAME = { 1: "again", 2: "hard", 3: "good", 4: "easy" };
  const STATE_NAME = { 0: "new", 1: "learning", 2: "review", 3: "relearning" };

  // ---- deck ----
  const parts = (e) => {
    const [, before, answer, after] = e.et.match(/^(.*)\{([^{}]+)\}(.*)$/s);
    const [, en_before, en_gloss, en_after] = e.en.match(/^(.*)\[([^\[\]]+)\](.*)$/s);
    return { before, answer, after, en_before, en_gloss, en_after, form: e.form || "", accept: e.accept || [],
      plain: e.et.replace(/[{}]/g, ""), plain_en: e.en.replace(/[\[\]]/g, "") };
  };
  const words = rawDeck.flatMap(({ band, words }) => words.map((w) => ({ ...w, band, forms: w.forms || [], note: w.note || "" })));
  const byId = new Map(words.map((w) => [w.id, w]));
  const summary = (w) => ({ id: w.id, lemma: w.lemma, pos: w.pos, en: w.en, forms: w.forms, note: w.note, band: w.band });

  // ---- persistence (falls back to memory where storage is blocked) ----
  let db;
  try { db = JSON.parse(localStorage.getItem(KEY)); } catch { db = null; }
  db = db || { cards: {}, reviews: [], settings: {} };
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(db)); } catch { /* memory only */ } };

  const settings = () => ({ ...DEFAULTS, ...db.settings });
  const scheduler = () => FSRS.fsrs(FSRS.generatorParameters({ request_retention: settings().desired_retention, enable_fuzz: true }));
  const loadCard = (c) => ({ ...c.fsrs, due: new Date(c.fsrs.due), last_review: c.fsrs.last_review ? new Date(c.fsrs.last_review) : undefined });

  const dayStart = (at, tz) => {
    const local = new Date(at.getTime() + tz * 60000);
    local.setUTCHours(0, 0, 0, 0);
    return new Date(local.getTime() - tz * 60000);
  };
  const localDay = (d, tz) => new Date(new Date(d).getTime() + tz * 60000).toISOString().slice(0, 10);
  const extraKey = (tz, at = new Date()) => `extra_new_${localDay(dayStart(at, tz), tz)}`;

  function counts(tz, at = new Date()) {
    const today = dayStart(at, tz);
    const cards = Object.values(db.cards);
    const unseen = words.length - cards.length;
    const newToday = cards.filter((c) => new Date(c.introduced) >= today).length;
    const limit = settings().new_per_day + (db.settings[extraKey(tz, at)] || 0);
    return {
      due: cards.filter((c) => new Date(c.fsrs.due) <= at).length,
      new_left: Math.max(0, Math.min(unseen, limit - newToday)),
      reviewed_today: db.reviews.filter((r) => new Date(r.reviewed_at) >= today).length,
      unseen, total: words.length,
    };
  }

  function cardPayload(w) {
    const row = db.cards[w.id];
    const idx = (row ? row.next_example : 0) % w.examples.length;
    const out = {
      word: summary(w), example_idx: idx, example: parts(w.examples[idx]),
      others: w.examples.filter((_, i) => i !== idx).map(parts), is_new: !row, state: null,
    };
    if (row) {
      const card = loadCard(row);
      out.state = { state: STATE_NAME[card.state], stability: card.stability, difficulty: card.difficulty,
        retrievability: scheduler().get_retrievability(card, new Date(), false) };
    }
    return out;
  }

  function next(tz, exclude) {
    const at = new Date();
    const c = counts(tz, at);
    const due = Object.entries(db.cards)
      .filter(([id, r]) => id !== exclude && new Date(r.fsrs.due) <= at)
      .sort(([, a], [, b]) => (a.fsrs.state === 2) - (b.fsrs.state === 2) || new Date(a.fsrs.due) - new Date(b.fsrs.due));
    const wantNew = c.new_left > 0 && (!due.length || c.reviewed_today % NEW_EVERY === NEW_EVERY - 1);
    let w = wantNew ? words.find((x) => !db.cards[x.id]) : null;
    if (!w && due.length) w = byId.get(due[0][0]);
    if (!w) {
      const soon = Object.entries(db.cards)
        .filter(([id, r]) => id !== exclude && r.fsrs.state !== 2 && new Date(r.fsrs.due) - at <= LEARN_AHEAD_MS)
        .sort(([, a], [, b]) => new Date(a.fsrs.due) - new Date(b.fsrs.due));
      if (soon.length) w = byId.get(soon[0][0]);
    }
    if (!w) {
      const dues = Object.values(db.cards).map((r) => r.fsrs.due).sort();
      return { card: null, counts: c, next_due: dues[0] || null };
    }
    return { card: cardPayload(w), counts: c };
  }

  function review({ word_id, example_idx, outcome, answer = "", duration_ms = null }) {
    const w = byId.get(word_id);
    if (!w || !(outcome in OUTCOME)) throw new Error("bad request");
    const at = new Date();
    const row = db.cards[word_id];
    let rating = OUTCOME[outcome];
    if (!row && outcome === "correct") rating = FSRS.Rating.Easy; // knew it before we taught it
    const { card } = scheduler().next(row ? loadCard(row) : FSRS.createEmptyCard(at), at, rating);
    db.cards[word_id] = {
      fsrs: JSON.parse(JSON.stringify(card)),
      next_example: (example_idx + 1) % w.examples.length,
      introduced: row ? row.introduced : at.toISOString(),
    };
    db.reviews.push({ word_id, example_idx, rating, outcome, answer: String(answer).slice(0, 100), duration_ms,
      was_new: !row, reviewed_at: at.toISOString() });
    save();
    return { due: card.due.toISOString(), state: STATE_NAME[card.state], stability: card.stability, rating: RATING_NAME[rating] };
  }

  function wordList() {
    const sched = scheduler();
    return words.map((w) => {
      const item = { ...summary(w), examples: w.examples.map(parts), status: "new" };
      const row = db.cards[w.id];
      if (row) {
        const card = loadCard(row);
        Object.assign(item, { status: STATE_NAME[card.state], due: card.due.toISOString(), stability: card.stability,
          retrievability: sched.get_retrievability(card, new Date(), false) });
      }
      return item;
    });
  }

  function stats(tz) {
    const at = new Date();
    const today = dayStart(at, tz);
    const byDay = {};
    for (const r of db.reviews) {
      const d = (byDay[localDay(r.reviewed_at, tz)] ||= { reviews: 0, correct: 0, new: 0 });
      d.reviews++; d.correct += r.outcome === "correct"; d.new += r.was_new;
    }
    const dayKey = (offsetDays) => localDay(new Date(today.getTime() + offsetDays * 86400000), tz);
    const history = [];
    for (let i = 29; i >= 0; i--) history.push({ day: dayKey(-i), ...(byDay[dayKey(-i)] || { reviews: 0, correct: 0, new: 0 }) });
    let streak = 0, i = byDay[dayKey(0)] ? 0 : 1;
    while (byDay[dayKey(-i)]) { streak++; i++; }
    const forecast = new Array(14).fill(0);
    const states = { learning: 0, review: 0, relearning: 0 };
    let mature = 0;
    for (const r of Object.values(db.cards)) {
      states[STATE_NAME[r.fsrs.state]]++;
      if ((r.fsrs.stability || 0) >= 21) mature++;
      const daysOut = Math.floor((new Date(r.fsrs.due) - today) / 86400000);
      if (daysOut < 14) forecast[Math.max(0, daysOut)]++;
    }
    const total = history.reduce((s, h) => s + h.reviews, 0);
    const seen = Object.keys(db.cards).length;
    return {
      streak, today: byDay[dayKey(0)] || { reviews: 0, correct: 0, new: 0 },
      accuracy_30d: total ? history.reduce((s, h) => s + h.correct, 0) / total : null,
      reviews_30d: total, history,
      forecast: forecast.map((due, k) => ({ day: dayKey(k), due })),
      states, mature, seen, total: words.length, counts: counts(tz, at),
    };
  }

  function updateSettings(ch) {
    const s = db.settings;
    if ("new_per_day" in ch) s.new_per_day = Math.max(0, Math.min(200, Math.trunc(+ch.new_per_day)));
    if ("desired_retention" in ch) s.desired_retention = Math.max(0.7, Math.min(0.97, +ch.desired_retention));
    for (const k of ["show_form", "auto_speak"]) if (k in ch) s[k] = !!ch[k];
    save();
    return settings();
  }

  // Router with the same paths as server.py.
  return async function localApi(path, body) {
    const url = new URL(path, "http://local");
    const tz = +(url.searchParams.get("tz") || (body && body.tz) || 0);
    switch (url.pathname) {
      case "/api/next": return next(tz, url.searchParams.get("exclude"));
      case "/api/review": return review(body);
      case "/api/words": return wordList();
      case "/api/stats": return stats(tz);
      case "/api/settings": return body === undefined ? settings() : updateSettings(body);
      case "/api/learn-more": {
        const k = extraKey(tz);
        db.settings[k] = (db.settings[k] || 0) + (+body.amount || 10);
        save();
        return { ok: true };
      }
      case "/api/export": return JSON.parse(JSON.stringify(db));
      default: throw new Error(`${path}: 404`);
    }
  };
}
