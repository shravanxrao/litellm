from __future__ import annotations

import argparse
import importlib.util
import importlib.metadata
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Final

DIRECTORY: Final = Path(__file__).resolve().parent
RUNTIME: Final = DIRECTORY / ".runtime"
REPOSITORY: Final = DIRECTORY.parent.parent


def main() -> None:
    parser: Final = argparse.ArgumentParser()
    parser.add_argument("--import-secrets", type=Path)
    parser.add_argument("--hostname", default="")
    args: Final = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if importlib.metadata.version("litellm") != "1.104.0":
        raise ValueError("Use the prepared LiteLLM 1.104.0 runtime")
    if importlib.metadata.version("litellm-proxy-extras") != "0.4.102.post1":
        raise ValueError("Use the matching database extras")
    (RUNTIME / "python.path").write_text(sys.executable, encoding="utf-8")
    shutil.copyfile(REPOSITORY / "model_prices_and_context_window.json", DIRECTORY / "pricing.json")
    spec: Final = importlib.util.find_spec("litellm")
    if spec is None or spec.origin is None:
        raise ValueError("Install the matching LiteLLM Windows package first")
    shutil.copyfile(DIRECTORY / "pricing.json", Path(spec.origin).parent / "model_prices_and_context_window_backup.json")
    if args.import_secrets:
        private: Final = json.loads(args.import_secrets.resolve().read_text(encoding="utf-8-sig"))
        if not isinstance(private, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in private.items()):
            raise ValueError("Private settings must be a JSON object containing strings")
        values: Final = {**private, "PUBLIC_PROXY_HOST": args.hostname}
        lines: Final = tuple(key + "=" + json.dumps(value) for key, value in values.items())
        if any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in values):
            raise ValueError("Invalid environment setting name")
        (RUNTIME / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif not (RUNTIME / ".env").exists():
        shutil.copyfile(DIRECTORY / ".env.example", RUNTIME / ".env")
    print("Laptop configuration prepared; private settings were not displayed")


if __name__ == "__main__":
    main()
