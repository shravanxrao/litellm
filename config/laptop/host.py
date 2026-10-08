from __future__ import annotations

import ctypes
import os
import sys
import threading
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

DIRECTORY: Final = Path(__file__).resolve().parent
RUNTIME: Final = DIRECTORY / ".runtime"
REQUIRED: Final = (
    "DATABASE_URL", "REDIS_URL",
    "LITELLM_MASTER_KEY", "LITELLM_SALT_KEY", "UI_USERNAME", "UI_PASSWORD",
)


def load_environment() -> None:
    from dotenv import load_dotenv

    load_dotenv(RUNTIME / ".env", override=True, interpolate=False)
    missing: Final = tuple(name for name in REQUIRED if not os.getenv(name, "").strip())
    if missing:
        raise ValueError("Missing private settings: " + ", ".join(missing))
    if any(os.environ[name] != os.environ[name].strip() for name in REQUIRED):
        raise ValueError("Remove surrounding whitespace from private settings")
    if not os.environ["LITELLM_MASTER_KEY"].startswith("sk-"):
        raise ValueError("LITELLM_MASTER_KEY must start with sk-")
    if min(len(os.environ[name]) for name in ("LITELLM_MASTER_KEY", "LITELLM_SALT_KEY", "UI_PASSWORD")) < 24:
        raise ValueError("Use strong master, encryption and admin secrets")
    schemes: Final = {
        "DATABASE_URL": ("postgres", "postgresql"),
        "REDIS_URL": ("redis", "rediss"),
    }
    for name, allowed in schemes.items():
        parsed: Final = urlparse(os.environ[name])
        if parsed.scheme not in allowed or not parsed.hostname:
            raise ValueError("Invalid connection format for " + name)
    defaults: Final = {
        "LITELLM_LOCAL_MODEL_COST_MAP": "True", "DISABLE_SCHEMA_UPDATE": "true",
        "LITELLM_LOG": "ERROR", "LITELLM_MODE": "PRODUCTION", "NUM_WORKERS": "1",
        "CONFIG_FILE_PATH": str(DIRECTORY / "config.yaml"), "LITELLM_BATCH_WRITE_AT": "1",
        "STORE_MODEL_IN_DB": "True", "GRACEFUL_SHUTDOWN_TIMEOUT": "20",
    }
    os.environ.update(defaults)
    sys.path.insert(0, str(DIRECTORY.parent / "vercel"))


def check_coordination() -> None:
    from redis import Redis

    with Redis.from_url(os.environ["REDIS_URL"], socket_timeout=5, socket_connect_timeout=5) as client:
        if not client.ping() or client.eval("return 1", 0) != 1:
            raise RuntimeError("Budget coordination unavailable; refusing to serve inference")


def run() -> None:
    load_environment()
    check_coordination()
    import uvicorn

    server: Final = uvicorn.Server(uvicorn.Config(
        "litellm.proxy.proxy_server:app", host="127.0.0.1", port=4000, workers=1,
        loop="asyncio", log_level="warning", access_log=False, timeout_graceful_shutdown=260,
    ))
    stopped: Final = threading.Event()

    def monitor() -> None:
        while not stopped.wait(1):
            if (RUNTIME / "stop.request").exists():
                server.should_exit = True
                return

    if os.name == "nt":
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    (RUNTIME / "host.pid").write_text(str(os.getpid()), encoding="utf-8")
    threading.Thread(target=monitor, daemon=True).start()
    try:
        print("Starting the local gateway with Redis budget coordination", flush=True)
        server.run()
    finally:
        stopped.set()
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
        (RUNTIME / "host.pid").unlink(missing_ok=True)
        (RUNTIME / "stop.request").unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        (RUNTIME / "host.pid").unlink(missing_ok=True)
        print("Local gateway stopped: " + type(error).__name__, file=sys.stderr, flush=True)
        raise SystemExit(1) from None
