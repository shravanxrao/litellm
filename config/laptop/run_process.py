from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Final


def main() -> int:
    parser: Final = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("Gateway", "Tunnel"), required=True)
    args: Final = parser.parse_args()
    directory: Final = Path(__file__).resolve().parent
    runtime: Final = directory / ".runtime"
    prefix: Final = "server" if args.kind == "Gateway" else "tunnel"
    with (runtime / (prefix + ".out.log")).open("w", encoding="utf-8", buffering=1) as output:
        with (runtime / (prefix + ".err.log")).open("w", encoding="utf-8", buffering=1) as error:
            if args.kind == "Gateway":
                sys.stdout = output
                sys.stderr = error
                (runtime / "stop.request").unlink(missing_ok=True)
                from host import run

                try:
                    run()
                    return 0
                except Exception as failure:
                    print("Gateway stopped: " + type(failure).__name__, file=error, flush=True)
                    return 1
            child: Final = subprocess.Popen(
                [str(runtime / "cloudflared.exe"), "tunnel", "--config", str(runtime / "tunnel.yaml"),
                 "--loglevel", "warn", "run", "--dns-resolver-addrs", "1.1.1.1:53",
                 "--dns-resolver-addrs", "8.8.8.8:53"], stdout=output, stderr=error,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            try:
                while child.poll() is None:
                    if (runtime / "tunnel-stop.request").exists():
                        child.terminate()
                        child.wait(timeout=10)
                        (runtime / "tunnel-stop.request").unlink(missing_ok=True)
                        return 0
                    time.sleep(1)
                return child.wait()
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
