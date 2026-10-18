"""Fill __NAME__ placeholders in a deploy template, escaping values for the output format.

Usage: python deploy/render_template.py <template> <output> NAME=value [NAME=value ...]
"""
import json
import re
import sys
from xml.sax.saxutils import escape


def main() -> int:
    template, output, *pairs = sys.argv[1:]
    values = dict(pair.split("=", 1) for pair in pairs)
    as_json = template.endswith(".json.template")
    quote = (lambda v: json.dumps(v)[1:-1]) if as_json else escape

    text = open(template, encoding="utf-8").read()
    missing = set(re.findall(r"__([A-Z_]+)__", text)) - set(values)
    if missing:
        print(f"missing values for: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    for name, value in values.items():
        text = text.replace(f"__{name}__", quote(value))
    with open(output, "w", encoding="utf-8") as f:
        f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
