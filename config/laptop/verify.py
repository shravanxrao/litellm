from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv


def check(name: str, passed: bool, status: int) -> None:
    print(json.dumps({"check": name, "passed": passed, "status": status}), flush=True)
    if not passed:
        raise RuntimeError("Verification failed: " + name)


def main() -> None:
    parser: Final = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:4000")
    args: Final = parser.parse_args()
    base: Final = args.base_url.rstrip("/")
    url: Final = urlparse(base)
    load_dotenv(Path(__file__).resolve().parent / ".runtime" / ".env", override=True, interpolate=False)
    local: Final = url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"} and url.port == 4000
    public: Final = url.scheme == "https" and url.hostname == os.getenv("PUBLIC_PROXY_HOST") and url.port in {None, 443}
    if not (local or public) or url.username or url.password or url.path or url.query or url.fragment:
        raise ValueError("Use the local gateway or the configured public proxy hostname")
    headers: Final = {"Authorization": "Bearer " + os.environ["LITELLM_MASTER_KEY"]}
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        ready: Final = client.get(base + "/health/readiness", headers=headers)
        check("authenticated_readiness", ready.status_code == 200, ready.status_code)
        unauthenticated: Final = client.get(base + "/key/list")
        check("admin_authentication", unauthenticated.status_code in {401, 403}, unauthenticated.status_code)
        login: Final = client.post(base + "/login", data={
            "username": os.environ["UI_USERNAME"], "password": os.environ["UI_PASSWORD"],
        })
        check("admin_login", login.status_code in {302, 303, 307}, login.status_code)
        models: Final = client.get(base + "/v1/models", headers=headers)
        check("configured_models", models.status_code == 200 and bool(models.json().get("data")), models.status_code)
        model: Final = models.json()["data"][0]["id"]
        created: Final = client.post(base + "/key/generate", headers=headers, json={
            "key_alias": "Temporary laptop readiness verification", "max_budget": 0, "models": [model],
        })
        check("virtual_key_creation", created.status_code == 200, created.status_code)
        key: Final = created.json()["key"]

        def denied_request(_: int) -> bool:
            response: Final = client.post(base + "/v1/chat/completions", headers={
                "Authorization": "Bearer " + key,
            }, json={"model": model, "messages": [{"role": "user", "content": "Never forward this request"}],
                     "max_completion_tokens": 128})
            return (response.status_code in {400, 402, 403, 422, 429}
                    and response.json().get("error", {}).get("type") == "budget_exceeded")

        try:
            with ThreadPoolExecutor(max_workers=6) as pool:
                results: Final = tuple(pool.map(denied_request, range(6)))
            check("concurrent_zero_budget_rejection", all(results), 200 if all(results) else 500)
            info: Final = client.get(base + "/key/info", headers=headers, params={"key": key})
            check("budget_and_spend", info.status_code == 200 and info.json()["info"]["max_budget"] == 0
                  and info.json()["info"]["spend"] == 0, info.status_code)
        finally:
            deleted: Final = client.post(base + "/key/delete", headers=headers, json={"keys": [key]})
            check("temporary_key_deleted", deleted.status_code == 200, deleted.status_code)
        revoked: Final = client.get(base + "/v1/models", headers={"Authorization": "Bearer " + key})
        check("deleted_key_rejection", revoked.status_code in {401, 403}, revoked.status_code)
    print("Verification completed without forwarding Azure inference", flush=True)


if __name__ == "__main__":
    main()
