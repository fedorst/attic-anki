"""Build a single self-contained HTML file: python tools/build_static.py [out.html]

No server needed: the deck, ts-fsrs and an in-browser backend (static/local-api.js)
are inlined, and progress is kept in the browser's localStorage. Good for GitHub
Pages, opening from disk, or previews.
"""

import json
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent
STATIC = WEB / "static"


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else WEB / "dist" / "sonad.html"
    deck = [
        {"band": re.sub(r"^\d+-", "", p.stem), "words": json.loads(p.read_text(encoding="utf-8"))}
        for p in sorted((WEB / "decks" / "et-en").glob("*.json"))
    ]
    deck_json = json.dumps(deck, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    local_api = (STATIC / "local-api.js").read_text(encoding="utf-8").replace("export function", "function")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    fsrs = next((STATIC / "vendor").glob("ts-fsrs-*.umd.js")).read_text(encoding="utf-8")

    html = (STATIC / "index.html").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="style.css">',
                        f"<style>\n{(STATIC / 'style.css').read_text(encoding='utf-8')}</style>")
    html = html.replace(
        '<script src="app.js" type="module"></script>',
        f'<script type="application/json" id="deck">{deck_json}</script>\n'
        f"<script>\n{fsrs}\n</script>\n"
        f'<script type="module">\n{local_api}\n'
        'window.sonadLocalApi = createLocalApi(JSON.parse(document.getElementById("deck").textContent), window.FSRS);\n'
        f"{app}\n</script>")
    assert "app.js" not in html and "style.css" not in html, "index.html layout changed; update build_static.py"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB, {sum(len(b['words']) for b in deck)} words)")


if __name__ == "__main__":
    main()
