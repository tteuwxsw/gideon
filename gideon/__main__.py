"""Ponto de entrada para execução via `python -m gideon` ou `pythonw -m gideon`."""

import sys
from pathlib import Path

# Quando executado via pythonw.exe (sem console), redireciona stdout/stderr antes de qualquer import
if sys.stdout is None or sys.stderr is None:
    _log_path = Path(__file__).resolve().parent.parent / "dados" / "gideon_background.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = open(_log_path, "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _log_file
    if sys.stderr is None:
        sys.stderr = _log_file

from gideon.servidor import main

if __name__ == "__main__":
    main()
