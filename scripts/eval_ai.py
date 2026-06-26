"""Evalúa la precisión del motor DETERMINISTA de triaje contra el golden set.
Sin LLM (corre en CI). Sale con código !=0 si la precisión < umbral."""
import argparse
import json
import sys
from pathlib import Path

# Ensure the project root is on sys.path so `src.*` is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.triage.engine import triage  # noqa: E402
from src.triage.signals import Signals  # noqa: E402

GOLDEN = Path(__file__).resolve().parent.parent / "tests" / "golden" / "golden_triage.jsonl"


def run(min_accuracy: float) -> int:
    cases = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    hits = 0
    for c in cases:
        signals = Signals(**c["signals"])
        verdict = triage(signals)
        got = verdict.category
        if got == c["expected_category"]:
            hits += 1
    acc = hits / len(cases) if cases else 0.0
    print(f"triage golden: {hits}/{len(cases)} = {acc:.3f} (min {min_accuracy})")
    return 0 if acc >= min_accuracy else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-accuracy", type=float, default=0.8)
    sys.exit(run(ap.parse_args().min_accuracy))
