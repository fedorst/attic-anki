// Sõnad — Lingvist-style Estonian trainer. No build step, no dependencies.

const TZ = -new Date().getTimezoneOffset(); // minutes east of UTC
const view = document.getElementById("view");

// ---------- tiny helpers ----------

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") for (const [p, val] of Object.entries(v)) p.startsWith("--") ? el.style.setProperty(p, val) : (el.style[p] = val);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
  return el;
}

async function api(path, body) {
  // Static build (dist/sonad.html) has no server: the page embeds an in-browser backend.
  if (window.sonadLocalApi) return window.sonadLocalApi(path, body);
  const res = await fetch(path, body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function relTime(iso) {
  const s = (new Date(iso) - Date.now()) / 1000;
  if (s <= 60) return "now";
  const units = [["minute", 60], ["hour", 3600], ["day", 86400], ["month", 2592000], ["year", 31536000]];
  let [name, size] = units[0];
  for (const u of units) if (s >= u[1]) [name, size] = u;
  const n = Math.round(s / size);
  return `in ${n} ${name}${n === 1 ? "" : "s"}`;
}

// ---------- grammar labels ----------

const CASES = {
  nom: ["nominative", "nimetav", "basic form; subject"],
  gen: ["genitive", "omastav", "of; possession; whole (total) object"],
  part: ["partitive", "osastav", "some / partial object; after numbers; after negation"],
  ill: ["illative", "sisseütlev", "into"],
  in: ["inessive", "seesütlev", "in, inside"],
  el: ["elative", "seestütlev", "out of; about"],
  all: ["allative", "alaleütlev", "onto; to (someone)"],
  ad: ["adessive", "alalütlev", "on, at; possessor (mul on)"],
  abl: ["ablative", "alaltütlev", "off, from (someone)"],
  tr: ["translative", "saav", "becoming; as; by (a time)"],
  ter: ["terminative", "rajav", "until, up to"],
  es: ["essive", "olev", "as, in the role of"],
  ab: ["abessive", "ilmaütlev", "without"],
  kom: ["comitative", "kaasaütlev", "with, together with"],
};
const PERSONS = { "1sg": "I", "2sg": "you", "3sg": "he/she/it", "1pl": "we", "2pl": "you (pl.)", "3pl": "they" };
const TENSES = { pres: "present", past: "past", cond: "conditional", imper: "imperative", quot: "quotative" };
const VERB_FORMS = {
  "ma-inf": ["ma-infinitive", "-ma: after pidama, hakkama, minema, tulema…"],
  "da-inf": ["da-infinitive", "-da: after tahtma, saama, võima, oskama…"],
  mas: ["-mas form", "in the middle of doing"],
  mast: ["-mast form", "from doing; out of doing"],
  maks: ["-maks form", "in order to"],
  des: ["-des gerund", "while / by doing"],
  mata: ["-mata form", "without doing"],
  nud: ["-nud participle", "active past participle (ei teinud, olen teinud)"],
  tud: ["-tud participle", "passive past participle"],
  v: ["-v participle", "present participle"],
  neg: ["negative", "form used after ei"],
  impers: ["impersonal", "someone does / it is done"],
  "impers-past": ["impersonal past", "someone did / it was done"],
  "impers-neg": ["impersonal negative", "after ei"],
};
const DEGREES = { comp: "comparative", sup: "superlative", short: "short" };

function describeForm(tag) {
  if (!tag) return null;
  const t = tag.split(" ");
  if (VERB_FORMS[tag]) return { label: VERB_FORMS[tag][0], hint: VERB_FORMS[tag][1] };
  if (TENSES[t[0]]) {
    if (t[1] === "neg") return { label: `${TENSES[t[0]]} negative`, hint: "form used after ei" };
    return { label: `${TENSES[t[0]]} · ${PERSONS[t[1]] || t[1]}`, hint: `${TENSES[t[0]]} tense, ${PERSONS[t[1]] || t[1]}` };
  }
  let prefix = "";
  if (DEGREES[t[0]]) { prefix = DEGREES[t[0]] + " "; t.shift(); }
  const c = CASES[t[0]];
  if (!c) return { label: tag, hint: "" };
  const num = t[1] === "pl" ? "plural" : "singular";
  return { label: `${prefix}${c[0]} ${t[1] === "pl" ? "pl." : "sg."}`, hint: `${c[1]} (${prefix}${c[0]} ${num}): ${c[2]}` };
}

const FORM_NAMES = {
  verb: ["ma-infinitive", "da-infinitive", "present (3sg)", "past (3sg)"],
  nominal: ["nominative", "genitive", "partitive", "partitive pl."],
};

// ---------- answer checking ----------

const norm = (s) => s.normalize("NFC").trim().replace(/\s+/g, " ").replace(/[‐‑–—]/g, "-").toLowerCase();
const fold = (s) => norm(s).normalize("NFD").replace(/[̀-ͯ]/g, "");

function check(input, ex) {
  const got = norm(input);
  const targets = [ex.answer, ...(ex.accept || [])].map(norm);
  if (targets.includes(got)) return "exact";
  if (targets.map(fold).includes(fold(input))) return "diacritics";
  return got ? "wrong" : "empty";
}

// Mark which letters of the correct answer the learner got wrong (LCS alignment).
function diff(input, answer) {
  const a = norm(input), b = answer;
  const bl = b.toLowerCase();
  const dp = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--)
      dp[i][j] = a[i] === bl[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const hit = new Array(b.length).fill(false);
  for (let i = 0, j = 0; i < a.length && j < b.length;) {
    if (a[i] === bl[j]) { hit[j] = true; i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  return h("span", { class: "diff" }, [...b].map((ch, j) => hit[j] ? ch : h("span", { class: "miss" }, ch)));
}

// ---------- speech ----------

let etVoice = null;
function loadVoices() {
  etVoice = speechSynthesis?.getVoices().find((v) => v.lang?.toLowerCase().startsWith("et")) || null;
}
if ("speechSynthesis" in window) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; }
function speak(text) {
  if (!etVoice) return;
  speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.voice = etVoice; u.lang = etVoice.lang; u.rate = 0.95;
  speechSynthesis.speak(u);
}
const speakBtn = (text) => etVoice && h("button", { class: "btn ghost", title: "Listen", "aria-label": "Listen", onclick: () => speak(text) }, "🔊");

// ---------- shared state ----------

let settings = { show_form: true, auto_speak: false, new_per_day: 15, desired_retention: 0.9 };
let lastWordId = null;

function renderToday(counts) {
  const el = document.getElementById("today");
  el.replaceChildren();
  if (!counts) return;
  el.append(h("span", {}, h("b", {}, counts.reviewed_today), " today · ", h("b", {}, counts.due), " due · ", h("b", {}, counts.new_left), " new"));
}

// ---------- LEARN ----------

async function learnView() {
  let data;
  try {
    data = await api(`/api/next?tz=${TZ}${lastWordId ? `&exclude=${encodeURIComponent(lastWordId)}` : ""}`);
  } catch (e) {
    view.replaceChildren(h("div", { class: "card empty" }, h("h2", {}, "Can't reach the server"), h("p", {}, String(e.message))));
    return;
  }
  renderToday(data.counts);
  const goal = data.counts.reviewed_today + data.counts.due + data.counts.new_left;
  const pct = goal ? (100 * data.counts.reviewed_today) / goal : 100;
  const progress = h("div", { class: "progress", role: "progressbar", "aria-valuenow": Math.round(pct), "aria-valuemin": 0, "aria-valuemax": 100 },
    h("div", { style: { width: `${pct}%` } }));

  if (!data.card) return view.replaceChildren(progress, doneScreen(data));
  view.replaceChildren(progress, cardScreen(data.card));
}

function doneScreen(data) {
  const c = data.counts;
  const more = c.unseen > 0 && h("button", {
    class: "btn primary", onclick: async () => { await api("/api/learn-more", { tz: TZ, amount: 10 }); learnView(); },
  }, "Learn 10 more words");
  return h("div", { class: "card empty" },
    h("h2", {}, c.reviewed_today ? "Tubli! All done for now." : "Nothing to review yet."),
    h("p", {}, data.next_due ? `Next review ${relTime(data.next_due)}. ` : "",
      c.unseen ? `${c.unseen} words still to discover.` : "You've met every word in the deck."),
    h("div", { style: { display: "flex", gap: "10px", justifyContent: "center" } },
      more, h("a", { class: "btn", href: "#/stats" }, "See progress")));
}

function cardScreen(card) {
  const ex = card.example;
  const w = card.word;
  const started = performance.now();
  let hints = 0;
  let outcome = null;     // what we'll report: correct | hard | wrong
  let phase = "ask";      // ask -> (retype) -> done
  let firstAnswer = "";
  let durationMs = null;

  const input = h("input", {
    class: "blank", autocomplete: "off", autocapitalize: "off", spellcheck: "false", "aria-label": "Missing Estonian word",
    style: { width: `${Math.max(3, ex.answer.length + 1)}ch` },
  });
  const formInfo = describeForm(ex.form);
  const formChip = formInfo && h("span", { class: "chip form", title: formInfo.hint }, formInfo.label);
  const stateChip = card.is_new
    ? h("span", { class: "chip new" }, h("span", { class: "dot" }), "new word")
    : h("span", { class: "chip" }, card.state.state === "review" ? "review" : "learning");

  const meta = h("div", { class: "card-meta" }, stateChip, h("span", { class: "chip" }, w.pos),
    settings.show_form && formChip, h("span", { class: "meta-right" }));
  const en = h("p", { class: "en" }, ex.en_before, h("mark", {}, ex.en_gloss), ex.en_after);
  const gloss = h("p", { class: "gloss" }, `${ex.en_gloss.trim()} — ${w.en}`);
  const et = h("p", { class: "et", lang: "et" }, ex.before, input, ex.after);
  const feedback = h("div");
  const details = h("div");

  const insert = (ch) => {
    const { selectionStart: s, selectionEnd: e, value } = input;
    input.value = value.slice(0, s) + ch + value.slice(e);
    input.setSelectionRange(s + 1, s + 1);
    input.focus();
    input.classList.remove("bad");
  };
  const hint = () => {
    if (phase !== "ask") return;
    hints++;
    // Show the form label first (if hidden), then reveal letters one by one.
    if (!settings.show_form && formChip && !meta.contains(formChip)) { meta.insertBefore(formChip, meta.lastChild); hints--; return; }
    input.value = ex.answer.slice(0, hints);
    input.focus();
    if (hints >= ex.answer.length) submit();
  };

  const tools = h("div", { class: "tools" },
    ["õ", "ä", "ö", "ü", "š", "ž"].map((c) => h("button", { class: "key", tabindex: "-1", onmousedown: (e) => e.preventDefault(), onclick: () => insert(c) }, c)),
    h("span", { class: "spacer" }),
    h("button", { class: "btn ghost", tabindex: "-1", onmousedown: (e) => e.preventDefault(), onclick: hint }, "Hint ", h("kbd", {}, "Tab")),
    h("button", { class: "btn primary", tabindex: "-1", onmousedown: (e) => e.preventDefault(), onclick: () => submit() }, "Check ", h("kbd", {}, "↵")));

  function showDetails() {
    const names = w.pos === "verb" ? FORM_NAMES.verb : FORM_NAMES.nominal;
    details.replaceChildren(h("div", { class: "details" },
      h("div", { class: "lemma-line" }, h("span", { class: "lemma", lang: "et" }, w.lemma), h("span", { class: "lemma-en" }, w.en), speakBtn(w.lemma)),
      w.forms.length ? h("div", { class: "forms" }, w.forms.map((f, i) => h("div", { class: "form-cell" }, h("small", {}, names[i]), h("b", { lang: "et" }, f)))) : null,
      w.note && h("div", { class: "note" }, w.note),
      card.others.length ? h("p", { class: "section-label" }, "More examples") : null,
      h("ul", { class: "examples" }, card.others.map((o) => {
        const f = describeForm(o.form);
        return h("li", {},
          h("span", { class: "ex-et", lang: "et" }, o.before, h("b", {}, o.answer), o.after, " ", speakBtn(o.plain)),
          h("span", { class: "ex-form" }, f ? f.label : ""),
          h("span", { class: "ex-en" }, o.plain_en));
      }))));
  }

  async function finish() {
    phase = "done";
    input.readOnly = true;
    input.classList.remove("retype", "bad");
    input.classList.add("ok");
    input.value = ex.answer;
    tools.replaceChildren();
    showDetails();
    if (settings.auto_speak) speak(ex.plain);
    lastWordId = w.id;
    const next = h("div", { class: "next-line" });
    tools.append(next);
    try {
      const res = await api("/api/review", { word_id: w.id, example_idx: card.example_idx, outcome, answer: firstAnswer, duration_ms: durationMs });
      next.append(`Next review ${relTime(res.due)}`);
    } catch (e) {
      next.append(h("span", { style: { color: "var(--bad)" } }, `Couldn't save: ${e.message}`));
    }
    next.append(h("span", { class: "spacer" }), speakBtn(ex.plain) || "",
      h("button", { class: "btn primary", onclick: learnView }, "Continue ", h("kbd", {}, "↵")));
  }

  function submit() {
    if (phase === "done") return learnView();
    const result = check(input.value, ex);
    if (phase === "retype") {
      if (result === "exact" || result === "diacritics") return finish();
      input.classList.remove("bad"); void input.offsetWidth; input.classList.add("bad");
      return;
    }
    // phase === "ask"
    firstAnswer = input.value;
    durationMs = Math.round(performance.now() - started);
    if (result === "exact") {
      outcome = hints ? "hard" : "correct";
      feedback.replaceChildren(h("div", { class: "feedback ok" }, card.is_new && !hints ? "Correct — you already knew this one!" : "Correct!"));
      return finish();
    }
    phase = "retype";
    if (result === "diacritics") {
      outcome = "hard";
      feedback.replaceChildren(h("div", { class: "feedback warn" }, "Almost — check the letters with dots and tildes: ", h("span", { lang: "et" }, diff(input.value, ex.answer)),
        h("span", { class: "sub" }, "Type it again with the right letters.")));
    } else {
      outcome = "wrong";
      const typo = result === "wrong" && h("button", { class: "btn", style: { marginTop: "8px" }, onclick: () => { outcome = hints ? "hard" : "correct"; typo.remove(); finish(); } }, "I made a typo — count it as correct");
      feedback.replaceChildren(h("div", { class: "feedback bad" },
        result === "empty" ? "The answer is " : "Not quite. The answer is ",
        h("span", { lang: "et", class: "answer-inline" }, result === "wrong" ? diff(input.value, ex.answer) : ex.answer),
        h("span", { class: "sub" }, card.is_new ? "New word — type it once to get it into your fingers." : "Type it to continue."),
        typo));
    }
    input.value = "";
    input.placeholder = ex.answer;
    input.classList.add("retype");
    input.focus();
    showDetails();
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); submit(); }
    else if (e.key === "Tab") { e.preventDefault(); hint(); }
  });
  input.addEventListener("input", () => input.classList.remove("bad"));

  const root = h("div", { class: "card" }, meta, en, card.is_new ? gloss : null, et, feedback, tools, details);
  queueMicrotask(() => input.focus());
  return root;
}

// ---------- WORDS ----------

async function wordsView() {
  const words = await api("/api/words");
  let filter = "all", query = "";
  const list = h("div", { class: "wordlist" });
  const counts = (s) => words.filter((w) => s === "all" || (s === "known" ? w.status === "review" : s === "learning" ? ["learning", "relearning"].includes(w.status) : w.status === s)).length;

  function render() {
    const q = fold(query);
    const shown = words.filter((w) => {
      if (filter === "known" && w.status !== "review") return false;
      if (filter === "learning" && !["learning", "relearning"].includes(w.status)) return false;
      if (filter === "new" && w.status !== "new") return false;
      return !q || fold(w.lemma).includes(q) || w.en.toLowerCase().includes(q) || w.forms.some((f) => fold(f).includes(q));
    });
    const rows = [];
    let band = null;
    for (const w of shown) {
      if (w.band !== band) { band = w.band; rows.push(h("div", { class: "band-label" }, band.replace(/-/g, " "))); }
      const r = w.retrievability;
      rows.push(h("details", { class: "wordrow" },
        h("summary", {},
          h("span", { class: "w-lemma", lang: "et" }, w.lemma),
          h("span", { class: "w-en" }, w.en),
          h("span", {}, h("span", { class: `status ${w.status}` }, w.status === "review" ? "known" : w.status),
            r != null && h("div", { class: "rbar", title: `${Math.round(r * 100)}% chance you remember it now` }, h("div", { style: { width: `${r * 100}%` } }))),
          h("span", { class: "w-due" }, w.due ? relTime(w.due) : "")),
        h("div", { class: "body" },
          w.forms.length ? h("div", { class: "forms" }, w.forms.map((f, i) => h("div", { class: "form-cell" },
            h("small", {}, (w.pos === "verb" ? FORM_NAMES.verb : FORM_NAMES.nominal)[i]), h("b", { lang: "et" }, f)))) : null,
          w.note && h("div", { class: "note" }, w.note),
          h("ul", { class: "examples" }, w.examples.map((o) => h("li", {},
            h("span", { class: "ex-et", lang: "et" }, o.before, h("b", {}, o.answer), o.after, " ", speakBtn(o.plain)),
            h("span", { class: "ex-form" }, describeForm(o.form)?.label || ""),
            h("span", { class: "ex-en" }, o.plain_en)))))));
    }
    list.replaceChildren(...(rows.length ? rows : [h("div", { class: "empty" }, h("p", {}, "No words match."))]));
  }

  const seg = h("div", { class: "seg", role: "tablist" }, [["all", "All"], ["learning", "Learning"], ["known", "Known"], ["new", "New"]].map(([k, label]) =>
    h("button", { class: k === filter ? "on" : "", onclick: (e) => { filter = k; seg.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === e.currentTarget)); render(); } },
      `${label} ${counts(k)}`)));
  const search = h("input", { class: "search", type: "search", placeholder: "Search Estonian or English…", oninput: (e) => { query = e.target.value; render(); } });
  view.replaceChildren(h("div", { class: "toolbar" }, search, seg), list);
  render();
}

// ---------- STATS ----------

function barChart(points, { label, valueLabel }) {
  const W = 600, H = 150, pad = { l: 28, r: 4, t: 8, b: 20 };
  const max = Math.max(4, ...points.map((p) => p.value));
  const step = Math.ceil(max / 4);
  const top = step * 4;
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const bw = iw / points.length;
  const ns = "http://www.w3.org/2000/svg";
  const s = (tag, attrs, text) => { const el = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v); if (text != null) el.textContent = text; return el; };
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: "none", role: "img", "aria-label": label });
  for (let i = 0; i <= 4; i++) {
    const y = pad.t + ih - (ih * i) / 4;
    svg.append(s("line", { class: "gridline", x1: pad.l, x2: W - pad.r, y1: y, y2: y }));
    svg.append(s("text", { class: "axis", x: pad.l - 6, y: y + 4, "text-anchor": "end" }, step * i));
  }
  const wrap = h("div", { class: "chart" });
  const tip = h("div", { class: "tip" });
  points.forEach((p, i) => {
    const x = pad.l + i * bw;
    const bh = (ih * p.value) / top;
    const w = Math.max(2, bw - 2); // 2px gap between bars
    const r = Math.min(4, w / 2, bh);
    const y = pad.t + ih - bh;
    // bar with rounded top, square base
    const path = bh > 0 ? `M${x + 1},${pad.t + ih} V${y + r} Q${x + 1},${y} ${x + 1 + r},${y} H${x + 1 + w - r} Q${x + 1 + w},${y} ${x + 1 + w},${y + r} V${pad.t + ih} Z` : "";
    const hit = s("rect", { class: "hit", x, y: pad.t, width: bw, height: ih });
    const bar = s("path", { class: "bar", d: path });
    hit.addEventListener("mouseenter", () => {
      bar.classList.add("hover");
      tip.textContent = `${p.label}: ${p.value} ${valueLabel}`;
      tip.style.left = `${((x + bw / 2) / W) * 100}%`;
      tip.style.top = `${(y / H) * 150 - 6}px`;
      tip.style.opacity = 1;
    });
    hit.addEventListener("mouseleave", () => { bar.classList.remove("hover"); tip.style.opacity = 0; });
    svg.append(hit, bar);
    if (p.tick) svg.append(s("text", { class: "axis", x: x + bw / 2, y: H - 4, "text-anchor": "middle" }, p.tick));
  });
  wrap.append(svg, tip);
  return wrap;
}

async function statsView() {
  const st = await api(`/api/stats?tz=${TZ}`);
  renderToday(st.counts);
  const fmtDay = (d, opts) => new Date(d + "T12:00:00").toLocaleDateString(undefined, opts);
  const tile = (v, l) => h("div", { class: "tile" }, h("div", { class: "v" }, v), h("div", { class: "l" }, l));
  const known = st.states.review;
  const learning = st.states.learning + st.states.relearning;
  const pct = (n) => `${(100 * n) / st.total}%`;

  view.replaceChildren(
    h("div", { class: "tiles" },
      tile(`${st.streak}`, st.streak === 1 ? "day streak" : "day streak"),
      tile(st.today.reviews, "cards today"),
      tile(`${st.seen}/${st.total}`, "words met"),
      tile(st.accuracy_30d == null ? "—" : `${Math.round(st.accuracy_30d * 100)}%`, "right first try (30 days)")),
    h("div", { class: "panel" },
      h("h3", {}, "Vocabulary"),
      h("p", { class: "desc" }, `${known} known (${st.mature} solid for 3+ weeks), ${learning} in learning, ${st.total - st.seen} not seen yet.`),
      h("div", { class: "stack", role: "img", "aria-label": `${known} known, ${learning} learning, ${st.total - st.seen} new` },
        h("div", { style: { width: pct(known), background: "var(--good)" } }),
        h("div", { style: { width: pct(learning), background: "var(--warn)" } })),
      h("div", { class: "legend" },
        h("span", { style: { "--c": "var(--good)" } }, `Known ${known}`),
        h("span", { style: { "--c": "var(--warn)" } }, `Learning ${learning}`),
        h("span", { style: { "--c": "var(--surface-2)" } }, `New ${st.total - st.seen}`))),
    h("div", { class: "panel" },
      h("h3", {}, "Last 30 days"),
      h("p", { class: "desc" }, `${st.reviews_30d} cards reviewed`),
      barChart(st.history.map((d, i) => ({
        value: d.reviews, label: fmtDay(d.day, { month: "short", day: "numeric" }),
        tick: i % 7 === 2 || i === 29 ? fmtDay(d.day, { month: "short", day: "numeric" }) : null,
      })), { label: "Reviews per day, last 30 days", valueLabel: "cards" })),
    h("div", { class: "panel" },
      h("h3", {}, "Coming up"),
      h("p", { class: "desc" }, "Reviews FSRS has scheduled for the next two weeks"),
      barChart(st.forecast.map((d, i) => ({
        value: d.due, label: i === 0 ? "Today" : fmtDay(d.day, { weekday: "short", month: "short", day: "numeric" }),
        tick: i === 0 ? "Today" : i % 2 === 0 ? fmtDay(d.day, { weekday: "short" }) : null,
      })), { label: "Reviews due per day, next 14 days", valueLabel: "due" })),
  );
}

// ---------- SETTINGS ----------

async function settingsView() {
  settings = await api("/api/settings");
  const save = async (patch) => { settings = await api("/api/settings", patch); };
  const retentionOut = h("span", {}, `${Math.round(settings.desired_retention * 100)}%`);
  const row = (label, desc, control) => h("div", { class: "setting" }, h("label", {}, label), h("div", { class: "control" }, control), h("div", { class: "desc" }, desc));
  const toggle = (key) => h("input", { type: "checkbox", class: "switch", checked: settings[key], onchange: (e) => save({ [key]: e.target.checked }) });

  view.replaceChildren(h("div", { class: "panel" },
    row("New words per day", "How many unseen words to introduce each day.",
      h("input", { type: "number", min: 0, max: 200, value: settings.new_per_day, onchange: (e) => save({ new_per_day: +e.target.value }) })),
    row("Target recall", "FSRS schedules each review for when your chance of remembering drops to this. Higher = more reviews, fewer lapses. 90% is a good default.",
      [h("input", { type: "range", min: 0.8, max: 0.95, step: 0.01, value: settings.desired_retention,
        oninput: (e) => { retentionOut.textContent = `${Math.round(e.target.value * 100)}%`; },
        onchange: (e) => save({ desired_retention: +e.target.value }) }), retentionOut]),
    row("Show grammatical form", "Show the case / tense the blank needs (e.g. partitive sg.). Turn off for a harder challenge — the first hint reveals it.", toggle("show_form")),
    row("Read sentences aloud", etVoice ? `Speak the sentence after each answer (voice: ${etVoice.name}).` : "No Estonian voice found on this device; install one in your OS speech settings to enable audio.", toggle("auto_speak")),
    row("Back up progress", "Download all reviews as JSON (also useful for fitting personal FSRS parameters).",
      h("button", { class: "btn", onclick: async () => {
        const blob = new Blob([JSON.stringify(await api("/api/export"), null, 1)], { type: "application/json" });
        const a = h("a", { href: URL.createObjectURL(blob), download: "sonad-progress.json" });
        document.body.append(a); a.click(); a.remove();
      } }, "Export")),
  ));
}

// ---------- router ----------

const routes = { learn: learnView, words: wordsView, stats: statsView, settings: settingsView };

async function route() {
  const name = location.hash.replace(/^#\//, "") || "learn";
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
  try {
    await (routes[name] || learnView)();
  } catch (e) {
    view.replaceChildren(h("div", { class: "card empty" }, h("h2", {}, "Something went wrong"), h("p", {}, e.message)));
  }
}

window.addEventListener("hashchange", route);
document.addEventListener("keydown", (e) => {
  // Enter continues after a finished card even if focus wandered off the input.
  if (e.key === "Enter" && document.activeElement === document.body && view.querySelector(".next-line .btn.primary")) learnView();
});
api("/api/settings").then((s) => { settings = s; }).catch(() => {}).finally(route);
