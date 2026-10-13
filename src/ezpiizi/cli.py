"""Interactive PII tester.

    ezpiizi              Presidio only
    ezpiizi --tracer         Presidio + PII-Tracer (trim, typing, cross-confirmation, filters): recommended
    ezpiizi --tracer-alone   PII-Tracer alone: raw output, every label, no Presidio, no filters

Commands: /vault  /restore <text>  /context <previous message>  /mode presidio|tracer|tracer-alone  /reset  /quit
"""
import json
import sys
import time

from ezpiizi import config, detection
from ezpiizi.pseudonymise import context_words, pseudonymise_content, pseudonymise_text
from ezpiizi.vault import PiiVault

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def explain_presidio(text: str, context: list[str] | None) -> None:
    engine = detection.analyzer()
    artifacts = engine.nlp_engine.process_text(text, config.LANGUAGE)
    raw = engine.analyze(text=text, language=config.LANGUAGE, entities=config.ENTITIES, nlp_artifacts=artifacts,
                         score_threshold=0, return_decision_process=True, context=context)
    if detection.USE_TRACER:
        print(f"  {DIM}Presidio :{RESET}")
    if not raw:
        print(f"  {DIM}aucune détection{RESET}")
    for r in sorted(raw, key=lambda r: r.start):
        found = text[r.start:r.end]
        if detection.USE_TRACER and r.entity_type == "PERSON":
            verdict = f"{RED}ignoré{RESET}  noms pris au modèle"
        elif r.score < config.SCORE_THRESHOLD:
            verdict = f"{RED}écarté{RESET}  score < {config.SCORE_THRESHOLD}"
        elif found in config.ALLOW_LIST:
            verdict = f"{RED}écarté{RESET}  allow list"
        elif not detection.is_plausible(r, text, artifacts.tokens):
            verdict = f"{RED}écarté{RESET}  filtre NER"
        else:
            verdict = f"{GREEN}gardé{RESET}"
        why = r.analysis_explanation
        boost = f", contexte +{why.score_context_improvement:.2f}" if why and why.score_context_improvement else ""
        source = why.recognizer if why else "?"
        print(f"  {r.entity_type:14} {found!r:40} score={r.score:.2f}  {DIM}({source}{boost}){RESET}  -> {verdict}")


def explain_tracer(text: str, context: list[str] | None) -> None:
    from ezpiizi.hybrid import detect_hybrid
    trace: list = []
    t0 = time.perf_counter()
    detect_hybrid(text, context, trace=trace)
    ms = (time.perf_counter() - t0) * 1000
    print(f"  {DIM}combinaison Presidio + PII-Tracer :{RESET}")
    if not trace:
        print(f"  {DIM}aucune détection{RESET}")
    for source, entity, found, score, verdict in trace:
        colour = GREEN if verdict.startswith("gardé") else RED
        head, _, reason = verdict.partition("  ")
        print(f"  {entity:14} {found!r:40} score={score:.2f}  {DIM}({source}){RESET}  -> "
              f"{colour}{head}{RESET}  {reason}")
    print(f"  {DIM}{ms:.0f} ms{RESET}")


def explain_tracer_alone(text: str) -> None:
    from ezpiizi.tracer import _predict
    t0 = time.perf_counter()
    raw = _predict(text)
    ms = (time.perf_counter() - t0) * 1000
    print(f"  {DIM}PII-Tracer seul (seuil {config.TRACER_THRESHOLD}) :{RESET}")
    if not raw:
        print(f"  {DIM}aucune détection{RESET}")
    for label, start, end, score in sorted(raw, key=lambda r: r[1]):
        kept = score >= config.TRACER_THRESHOLD and label in config.TRACER_ALL_LABELS
        verdict = (f"{GREEN}gardé{RESET}  -> {config.TRACER_ALL_LABELS[label]}" if kept
                   else f"{RED}écarté{RESET}  score < {config.TRACER_THRESHOLD}")
        print(f"  {label:16} {text[start:end]!r:40} score={score:.2f}  -> {verdict}")
    print(f"  {DIM}{ms:.0f} ms{RESET}")


def show(text: str, vault: PiiVault, context: list[str] | None) -> None:
    try:
        is_json = isinstance(json.loads(text), (dict, list))
    except json.JSONDecodeError:
        is_json = False
    if is_json:
        print(f"  {DIM}JSON : les clés connues décident sans analyse{RESET}")
        out = pseudonymise_content(text, vault)
    else:
        if detection.USE_TRACER and detection.TRACER_ALONE:
            explain_tracer_alone(text)
        elif detection.USE_TRACER:
            explain_tracer(text, context)
        else:
            explain_presidio(text, context)
        out = pseudonymise_text(text, vault, context)
    print(f"\n  {BOLD}le modèle voit :{RESET} {out}")


def set_mode(mode: str) -> None:
    if mode in ("tracer", "tracer-alone"):
        print(f"  {DIM}chargement de PII-Tracer...{RESET}", flush=True)
        t0 = time.perf_counter()
        detection.enable_tracer(True, alone=mode == "tracer-alone")
        label = "PII-Tracer seul" if mode == "tracer-alone" else "Presidio + PII-Tracer"
        print(f"  mode {label} ({time.perf_counter() - t0:.0f} s)")
    elif mode == "presidio":
        detection.enable_tracer(False)
        print("  mode Presidio seul")
    else:
        print("  /mode presidio | tracer | tracer-alone")


def main() -> None:
    print(f"{DIM}{__doc__.strip().splitlines()[-1]}{RESET}")
    if "--tracer-alone" in sys.argv:
        set_mode("tracer-alone")
    elif "--tracer" in sys.argv:
        set_mode("tracer")
    vault, context = PiiVault(), None
    while True:
        tag = ("[tracer seul]" if detection.TRACER_ALONE else "[+tracer]") if detection.USE_TRACER else ""
        prompt = f"{BOLD}texte{tag}>{RESET} "
        try:
            line = input(f"\n{DIM}(contexte: {' '.join(context)}){RESET}\n{prompt}" if context
                         else f"\n{prompt}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line == "/quit":
            break
        if line == "/reset":
            vault = PiiVault()
            print("  nouveau coffre")
        elif line == "/vault":
            for placeholder, value in vault.by_placeholder.items():
                print(f"  {placeholder:18} -> {value}")
            if not vault.by_placeholder:
                print(f"  {DIM}coffre vide{RESET}")
        elif line.startswith("/context"):
            msg = line.removeprefix("/context").strip()
            context = context_words(msg) if msg else None
            print(f"  contexte {'défini' if context else 'effacé'}")
        elif line.startswith("/mode"):
            set_mode(line.removeprefix("/mode").strip())
        elif line.startswith("/restore "):
            print(f"  le client voit : {vault.restore(line.removeprefix('/restore '))}")
        else:
            show(line, vault, context)


if __name__ == "__main__":
    main()
