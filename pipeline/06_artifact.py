"""Step 4b — derive the claude.ai Artifact page from site/index.html.

The Artifact host wraps the page in its own <!doctype>/<head>/<body> skeleton and
admits scripts only inline or from a few CDNs (three.js comes from jsDelivr through
the import map), so this writes site/artifact.html: the head content of index.html
(title, meta, fonts, import map, style) and its body with the page's own modules
inlined as one module script. gl.js, i18n.js and method.js keep their own scope
(each becomes a function returning its exports); main.js runs at the top level.
The data files are published next to it under the same relative paths
(data/core.json, data/ey.json, data/titles.*.json, data/topics.*.json, data/p/*.json).
"""
import re
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"
THREE_IMPORT = re.compile(r'^import .* from "three(/[^"]*)?";\n', re.M)


def as_scope(src: str, name: str) -> str:
    """A module without imports of its own pages as `const {exports} = (() => {...})();`."""
    src = THREE_IMPORT.sub("", src)
    names = re.findall(r"^export (?:async )?(?:function|const|let) (\w+)", src, re.M)
    body = re.sub(r"^export ", "", src, flags=re.M)
    assert "import " not in re.sub(r"//.*", "", body), f"{name}: unexpected import"
    return f"// ---- {name} ----\nconst {{ {', '.join(names)} }} = (() => {{\n{body}\nreturn {{ {', '.join(names)} }};\n}})();\n"


def main() -> None:
    html = (SITE / "index.html").read_text(encoding="utf-8")
    head = re.search(r"<head>(.*?)</head>", html, re.S).group(1)
    body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
    head = re.sub(r'\s*<meta (charset|name="viewport")[^>]*>', "", head)

    main_js = (SITE / "main.js").read_text(encoding="utf-8")
    imports = [m.group(0) for m in THREE_IMPORT.finditer(main_js)]
    main_js = THREE_IMPORT.sub("", main_js)
    main_js = re.sub(r'^import \{[^}]*\} from "\./(gl|i18n)\.js";\n', "", main_js, flags=re.M)
    dyn = 'const { methodHTML } = await import("./method.js");'
    assert dyn in main_js, "method.js import changed"
    main_js = main_js.replace(dyn, "")
    assert 'from "./' not in main_js and 'import("./' not in main_js, "unbundled local import left"
    bundle = "".join(imports) + "".join(as_scope((SITE / f).read_text(encoding="utf-8"), f)
                                        for f in ("gl.js", "i18n.js", "method.js")) + "// ---- main.js ----\n" + main_js
    tag = '<script type="module" src="main.js"></script>'
    assert tag in body
    body = body.replace(tag, '<script type="module">\n' + bundle + "\n</script>")
    out = head.strip() + "\n" + body.strip() + "\n"
    (SITE / "artifact.html").write_text(out, encoding="utf-8")
    print(f"site/artifact.html {len(out.encode()):,} bytes")


if __name__ == "__main__":
    main()
