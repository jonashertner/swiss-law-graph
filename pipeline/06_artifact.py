"""Step 4b — derive the claude.ai Artifact page from site/index.html.

The Artifact host wraps the page in its own <!doctype>/<head>/<body> skeleton and
admits scripts only inline or from a few CDNs, so this writes site/artifact.html:
the head content (title, meta, fonts, style) and body content of index.html with
app.js inlined. The data files are published next to it under the same relative
paths (data/core.json, data/titles.*.json, data/p/*.json).
"""
import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"


def main() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
    head = re.sub(r'\s*<meta (charset|name="viewport")[^>]*>', "", head)
    app = (SITE / "app.js").read_text(encoding="utf-8")
    body = body.replace('<script src="app.js"></script>', "<script>\n" + app + "\n</script>")
    (SITE / "artifact.html").write_text(head.strip() + "\n" + body.strip() + "\n", encoding="utf-8")
    print(f"site/artifact.html {len(head) + len(body) + len(app):,} bytes")


if __name__ == "__main__":
    main()
