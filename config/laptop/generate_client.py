from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

from dotenv import load_dotenv


def main() -> int:
    runtime: Final = Path(__file__).resolve().parent / ".runtime"
    load_dotenv(runtime / ".env", override=True, interpolate=False)
    spec: Final = importlib.util.find_spec("litellm_proxy_extras")
    if spec is None or spec.origin is None:
        raise ValueError("LiteLLM database extras are missing")
    original: Final = (Path(spec.origin).parent / "schema.prisma").read_text(encoding="utf-8")
    schema: Final = runtime / "schema.prisma"
    schema.write_text(re.sub(r"binaryTargets = \[.*?\]", 'binaryTargets = ["native"]', original), encoding="utf-8")
    result: Final = subprocess.run(
        [sys.executable, "-m", "prisma", "generate", "--schema", str(schema)],
        env={**os.environ, "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")},
        capture_output=True, text=True, timeout=240,
    )
    (runtime / "client-generation.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    print("Database client generation: " + ("ready" if result.returncode == 0 else "failed"), flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
