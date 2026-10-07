#!/bin/sh
set -eu

python - <<'PY'
import os
import re
import subprocess
import sys
from urllib.parse import urlparse

required = (
    "AZURE_API_BASE", "AZURE_API_KEY", "DATABASE_URL",
    "LITELLM_MASTER_KEY", "LITELLM_SALT_KEY",
)
missing = [name for name in required if not os.environ.get(name, "").strip()]
if missing:
    sys.exit("Startup blocked: missing " + ", ".join(missing))
for name in required:
    if os.environ[name] != os.environ[name].strip():
        sys.exit("Startup blocked: whitespace around " + name)
if not os.environ["LITELLM_MASTER_KEY"].startswith("sk-"):
    sys.exit("Startup blocked: LITELLM_MASTER_KEY must begin with sk-")
if len(os.environ["LITELLM_MASTER_KEY"]) < 32:
    sys.exit("Startup blocked: LITELLM_MASTER_KEY is too short")
if len(os.environ["LITELLM_SALT_KEY"]) < 32:
    sys.exit("Startup blocked: LITELLM_SALT_KEY is too short")
endpoint = urlparse(os.environ["AZURE_API_BASE"])
if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
    sys.exit("Startup blocked: AZURE_API_BASE must be an HTTPS endpoint")
database = urlparse(os.environ["DATABASE_URL"])
if database.scheme not in {"postgres", "postgresql"} or not database.hostname:
    sys.exit("Startup blocked: DATABASE_URL must be a PostgreSQL connection URL")
redis_value = os.environ.get("REDIS_URL", "")
if redis_value:
    redis_url = urlparse(redis_value)
    if redis_url.scheme not in {"redis", "rediss"} or not redis_url.hostname:
        sys.exit("Startup blocked: REDIS_URL must use the Redis TCP protocol")
port = os.environ.get("PORT", "4000")
if not port.isdigit() or not 1 <= int(port) <= 65535:
    sys.exit("Startup blocked: PORT must be between 1 and 65535")
import yaml
from pathlib import Path
config = yaml.safe_load(Path("/app/deploy/config.yaml").read_text())
if redis_value:
    try:
        from redis import Redis
        client = Redis.from_url(redis_value, socket_timeout=5, socket_connect_timeout=5)
        if not client.ping() or client.eval("return 1", 0) != 1:
            sys.exit("Startup blocked: Redis budget coordination is unavailable")
        client.close()
    except Exception:
        sys.exit("Startup blocked: Redis budget coordination could not be verified")
    print("Deployment prerequisites verified; starting the budget gateway.", flush=True)
else:
    config["general_settings"].pop("coordination_redis", None)
    config["general_settings"]["use_redis_transaction_buffer"] = False
    config["litellm_settings"]["enable_redis_auth_cache"] = False
    config["model_list"] = []
    print("Admin portal available; paid inference blocked until Redis is configured and redeployed.", flush=True)
Path("/tmp/litellm-runtime-config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
if os.environ.get("LITELLM_RUN_MIGRATIONS", "false").lower() == "true":
    migration_environment = dict(os.environ)
    migration_environment["DISABLE_SCHEMA_UPDATE"] = "false"
    migration_environment["ENFORCE_PRISMA_MIGRATION_CHECK"] = "true"
    try:
        migration = subprocess.run(
            [sys.executable, "-m", "litellm.proxy.prisma_migration"],
            env=migration_environment,
            capture_output=True,
            text=True,
            timeout=240,
        )
    except Exception:
        sys.exit("Startup blocked: database migration could not finish")
    if migration.returncode:
        diagnostic = migration.stdout + "\n" + migration.stderr
        prisma_codes = sorted(set(re.findall(r"\bP\d{4}\b", diagnostic)))
        missing_modules = re.findall(
            r"ModuleNotFoundError: No module named ['\"]([A-Za-z0-9_.]{1,80})['\"]", diagnostic
        )
        safe_details = ["exit " + str(migration.returncode)]
        if prisma_codes:
            safe_details.append("Prisma " + ", ".join(prisma_codes))
        if missing_modules:
            safe_details.append("missing module " + ", ".join(sorted(set(missing_modules))))
        sys.exit("Startup blocked: database migration failed (" + "; ".join(safe_details) + ")")
    print("Matching LiteLLM database migrations completed.", flush=True)
PY

export CONFIG_FILE_PATH=/tmp/litellm-runtime-config.yaml
export NUM_WORKERS=1
exec python -m uvicorn litellm.proxy.proxy_server:app --fd "${LITELLM_SERVER_FD}" --workers 1 --timeout-graceful-shutdown 5
