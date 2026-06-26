import subprocess
import sys


def test_eval_ai_passes_on_golden():
    r = subprocess.run(
        [sys.executable, "scripts/eval_ai.py", "--min-accuracy", "0.8"],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, f"eval falló: {r.stdout}\n{r.stderr}"
    assert "triage golden:" in r.stdout
