"""PII detection benchmark.

    ezpiizi-bench                                  # MAPA (French), Presidio vs Presidio + PII-Tracer
    ezpiizi-bench --dataset gretel --systems C,H6  # Gretel synthetic finance (French)
    ezpiizi-bench --dataset path/to/file.jsonl --details --limit 100

Scoring is span-based, per type:
    full      a prediction of the right type covers the whole value (found)
    partial   overlaps but leaves part visible (not found)
    false +   prediction overlapping no value of its type and no ignored span
    leak      value covered by no prediction of any type (what matters for privacy)
    chars     label-agnostic character P/R/F1 (as in the PII-TRACE paper); characters in ignored
              spans count neither way
"""
import argparse
import sys
import time
from collections import defaultdict

from ezpiizi.bench import systems as systems_mod
from ezpiizi.bench.datasets import DATASETS, TYPES, load_jsonl, load_mapa

ACCOUNT_TYPES = {"IBAN", "RIB", "CARD", "ID"}   # gold types a generic ACCOUNT prediction can stand for


def merge_overlaps(preds):
    merged = []
    for t, s, e in sorted(preds):
        if merged and merged[-1][0] == t and s < merged[-1][2]:
            merged[-1] = (t, merged[-1][1], max(e, merged[-1][2]))
        else:
            merged.append((t, s, e))
    return merged


def progress(name: str, done: int, total: int, elapsed: float) -> None:
    eta = elapsed / done * (total - done) if done else 0
    end = "\n" if done == total else ""
    print(f"\r  {name}: {done}/{total}  ({elapsed:.0f} s, reste ~{eta:.0f} s)   ", end=end, file=sys.stderr, flush=True)


def snippet(text: str, start: int, end: int, width: int = 45) -> str:
    """One-line excerpt around a span, the span in [brackets]."""
    left = text[max(0, start - width):start]
    right = text[end:end + width]
    return " ".join(f"{left}[{text[start:end]}]{right}".split())


def score(system, rows, name: str = ""):
    stats = defaultdict(lambda: defaultdict(int))
    errors, elapsed = [], 0.0
    every = max(1, len(rows) // 50)
    for i, row in enumerate(rows, 1):
        text, gold, ignore = row["text"], row["gold"], row["ignore"]
        t0 = time.perf_counter()
        raw = system(text)
        elapsed += time.perf_counter() - t0

        def resolve(t, s, e, gold=gold):
            if t == "ACCOUNT":
                for gt, gs, ge in gold:
                    if gt in ACCOUNT_TYPES and s < ge and e > gs:
                        return gt
            return t
        preds = merge_overlaps([(resolve(t, s, e), s, e) for t, s, e in raw])
        if name and (i % every == 0 or i == len(rows)):
            progress(name, i, len(rows), elapsed)

        gold_chars = {i for _, s, e in gold for i in range(s, e)}
        ignored = {i for s, e in ignore for i in range(s, e)} - gold_chars
        pred_chars = {i for _, s, e in preds for i in range(s, e)} - ignored
        stats["_chars"]["gold"] += len(gold_chars)
        stats["_chars"]["pred"] += len(pred_chars)
        stats["_chars"]["hit"] += len(gold_chars & pred_chars)

        for gtype, gs, ge in gold:
            stats[gtype]["labelled"] += 1
            if not any(s <= gs and e >= ge for _, s, e in preds):
                stats["_all"]["leaks"] += 1
            same = [(s, e) for t, s, e in preds if t == gtype and s < ge and e > gs]
            if any(s <= gs and e >= ge for s, e in same):
                stats[gtype]["full"] += 1
            elif same:
                stats[gtype]["partial"] += 1
                errors.append(("partial", gtype, text[gs:ge], snippet(text, gs, ge)))
            else:
                stats[gtype]["missed"] += 1
                errors.append(("missed", gtype, text[gs:ge], snippet(text, gs, ge)))

        for ptype, ps, pe in preds:
            if any(t == ptype and ps < ge and pe > gs for t, gs, ge in gold):
                stats[ptype]["predicted"] += 1
            elif not any(ps < ie and pe > is_ for is_, ie in ignore):
                stats[ptype]["predicted"] += 1
                stats[ptype]["false_pos"] += 1
                errors.append(("false +", ptype, text[ps:pe], snippet(text, ps, pe)))
    return stats, errors, elapsed * 1000 / max(len(rows), 1)


def cell(s) -> str:
    n, full, pred = s["labelled"], s["full"], s["predicted"]
    recall = f"{full}/{n}" if n else "-"
    precision = f"{full / pred:.0%}" if pred and n else ("0%" if pred else "-")
    extra = ", ".join(f"{s[k]} {label}" for k, label in (("partial", "partiel"), ("false_pos", "FP")) if s[k])
    return f"{recall:>7} {precision:>5} {extra:<14}"


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="ezpiizi PII detection benchmark")
    parser.add_argument("--dataset", default="mapa", help="mapa | gretel | path to a .jsonl file")
    parser.add_argument("--systems", default="C,H6",
                        help="C (presidio) and/or H1-H6 (presidio+tracer steps, H6 = tracer mode)")
    parser.add_argument("--mapa-level", default="fine", choices=["fine", "coarse"],
                        help="fine: names only (default); coarse: MAPA PERSON spans (titles, roles...)")
    parser.add_argument("--limit", type=int, default=None, help="first N sentences only")
    parser.add_argument("--details", action="store_true", help="list every error")
    args = parser.parse_args(argv)

    if args.dataset == "mapa":
        rows = load_mapa(level=args.mapa_level)
    else:
        rows = DATASETS[args.dataset]() if args.dataset in DATASETS else load_jsonl(args.dataset)
    rows = rows[: args.limit] if args.limit else rows
    systems = systems_mod.build([s.strip().upper() for s in args.systems.split(",")])
    results = {name: score(fn, rows, name) for name, fn in systems.items()}

    n_values = sum(len(r["gold"]) for r in rows)
    label = f"mapa ({args.mapa_level})" if args.dataset == "mapa" else args.dataset
    print(f"\n{label}: {len(rows)} phrases, {n_values} valeurs à masquer, "
          f"{sum(1 for r in rows if not r['gold'])} phrases sans PII\n")
    width = 30
    print(f"{'type':9}| " + " | ".join(f"{name:{width}}" for name in systems))
    print(f"{'':9}| " + " | ".join(f"{'rappel':>7} {'préc.':>5} {'erreurs':<14}" for _ in systems))
    print("-" * (11 + (width + 3) * len(systems)))
    shown = [t for t in TYPES + ["ACCOUNT"]
             if any(results[n][0][t]["labelled"] or results[n][0][t]["predicted"] for n in systems)]
    for t in shown:
        print(f"{t:9}| " + " | ".join(cell(results[n][0][t]) for n in systems))
    print("-" * (11 + (width + 3) * len(systems)))
    totals = {}
    for n in systems:
        total = defaultdict(int)
        for t in shown:
            for k, v in results[n][0][t].items():
                total[k] += v
        totals[n] = total
    print(f"{'TOTAL':9}| " + " | ".join(cell(totals[n]) for n in systems))
    print(f"{'fuites':9}| " + " | ".join(f"{results[n][0]['_all']['leaks']:>7} non masquées{'':10}" for n in systems))
    def chars(c):
        p = c["hit"] / c["pred"] if c["pred"] else 0
        r = c["hit"] / c["gold"] if c["gold"] else 0
        f = 2 * p * r / (p + r) if p + r else 0
        return f"P {p:.2f} R {r:.2f} F1 {f:.2f}"
    print(f"{'caractères':9}| " + " | ".join(f"{chars(results[n][0]['_chars']):<30}" for n in systems))
    print(f"{'ms/phrase':9}| " + " | ".join(f"{results[n][2]:>7.1f}{'':23}" for n in systems))

    if args.details:
        for name in systems:
            print(f"\n=== {name}")
            for kind, t, span, context in sorted(results[name][1], key=lambda e: (e[0], e[1])):
                print(f"  {kind:8} {t:8} {span!r:35} | {context}")


if __name__ == "__main__":
    main()
