"""End-to-end evaluation through the HTTP API (run the server first, with requirements-ocr.txt).

    .venv\\Scripts\\python -m tests.ocr.eval_e2e [--base http://127.0.0.1:8000] [--user admin --password ...]

Builds a template from the blank 2-page form, then extracts every degraded filled scan in
zone mode (template positions) and label mode (positions removed), and prints a field matrix.
"""
import argparse
import copy
import json
import re
import sys
import time

import httpx

from app.ocr.values import plain
from tests.ocr import corpus


def norm(v):
    if isinstance(v, str):
        return re.sub(r"\s+", " ", v.strip().lower()).rstrip(".,")
    if isinstance(v, list):
        return [norm(x) for x in v]
    return v


def post(client, path, files, data=None):
    t = time.time()
    r = client.post(path, files=files, data=data, timeout=600)
    r.raise_for_status()
    return r.json(), time.time() - t


def labels(task_data):
    return {plain(e.get("label", "")): e for e in task_data if e.get("field_name") and plain(e.get("label", ""))}


def check_template(task_data):
    found = labels(task_data)
    problems = []
    for label, kind in corpus.EXPECTED_TYPES.items():
        e = found.get(label)
        if e is None:
            problems.append(f"missing field '{label}'")
        elif e["element"] != kind:
            problems.append(f"'{label}' is {e['element']}, expected {kind}")
    extra = [f"{e['element']}:'{plain(e.get('label', ''))}'" for lab, e in found.items()
             if lab not in corpus.EXPECTED_TYPES and e["element"] not in ("TwoColumnRow", "ThreeColumnRow", "MultiColumnRow")]
    opts = {lab: [o["text"] for o in found[lab].get("options", [])] for lab in ("Account Type", "Services Required") if lab in found}
    table = found.get("Nominee Details")
    return problems, extra, opts, table


def score(task_data, result):
    found = labels(task_data)
    answers = result["answers"]
    row = {}
    for label, want in corpus.EXPECTED.items():
        e = found.get(label)
        if e is None:
            row[label] = ("no field", None)
            continue
        got = answers.get(e["field_name"])
        if e["element"] in ("Checkboxes", "RadioButtons") and got is not None:
            names = {o["key"]: o["text"] for o in e.get("options", [])}
            got = [names.get(k, k) for k in got]
        if want == "<image>":
            ok = isinstance(got, str) and len(got) > 100
            shown = "image" if ok else got
        else:
            ok = norm(got) == norm(want)
            shown = got
        row[label] = ("ok" if ok else "WRONG", shown)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin", help="an account allowed to author templates")
    ap.add_argument("--password", default="Harman@2026")
    ap.add_argument("--kinds", default=",".join(corpus.KINDS))
    ap.add_argument("--json", default=None, help="write raw results here")
    args = ap.parse_args()
    client = httpx.Client(base_url=args.base)
    login = client.post("/api/auth/login", json={"username": args.user, "password": args.password})
    login.raise_for_status()
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    blank = corpus.to_pdf(corpus.draw(filled=False))
    tpl, secs = post(client, "/api/ocr/template", {"file": ("blank.pdf", blank, "application/pdf")})
    task_data = tpl["task_data"]
    problems, extra, opts, table = check_template(task_data)
    print(f"TEMPLATE ({secs:.1f}s, {len(task_data)} elements, stats {tpl['stats']})")
    print("  problems:", problems or "none")
    print("  extra fields:", extra or "none")
    print("  options:", opts)
    if table:
        print("  table columns:", [c["text"] for c in table["columns"]], "rows:", len(table["rows"]))
    statics = [(e["element"], plain(e.get("content", ""))[:60]) for e in task_data if e.get("static")]
    print("  static text:", statics)

    no_ocr = copy.deepcopy(task_data)
    for e in no_ocr:
        e.pop("ocr", None)
        for o in e.get("options") or []:
            o.pop("ocr", None)

    filled = corpus.draw(filled=True)
    results = {}
    for kind in args.kinds.split(","):
        pages = [corpus.degrade(p, kind, seed=i) for i, p in enumerate(filled)]
        pdf = corpus.to_pdf(pages)
        for mode, form in (("zone", task_data), ("label", no_ocr)):
            res, secs = post(client, "/api/ocr/extract", {"file": (f"{kind}.pdf", pdf, "application/pdf")}, {"form": json.dumps(form)})
            results[(kind, mode)] = (score(form, res), res.get("alignment"), secs)

    fields = list(corpus.EXPECTED)
    cols = list(results)
    print()
    print(f"{'field':24}" + "".join(f"{k[0][:11] + '/' + k[1][0]:>14}" for k in cols))
    for f in fields:
        print(f"{f[:24]:24}" + "".join(f"{('ok' if results[c][0][f][0] == 'ok' else 'X'):>14}" for c in cols))
    print(f"{'ACCURACY':24}" + "".join(f"{sum(1 for f in fields if results[c][0][f][0] == 'ok')}/{len(fields):<11}".rjust(14) for c in cols))
    print(f"{'seconds':24}" + "".join(f"{results[c][2]:>14.1f}" for c in cols))
    print()
    for c in cols:
        wrong = {f: v[1] for f, v in results[c][0].items() if v[0] != "ok"}
        if wrong:
            print(f"{c[0]}/{c[1]} alignment={results[c][1]}")
            for f, got in wrong.items():
                print(f"    {f}: got {got!r}  expected {corpus.EXPECTED[f]!r}")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"template": task_data, "results": {f"{k[0]}/{k[1]}": v[0] for k, v in results.items()}}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
