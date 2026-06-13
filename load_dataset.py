"""POST data/publications.ttl into the Fuseki `publications` dataset.

This loader is complete — you do not modify it for the integration task.
Bring up Fuseki via `docker compose up -d`, run this once, then run pytest.

Auth: docker-compose.yml starts Fuseki with `ADMIN_PASSWORD: admin`, which
locks write endpoints (including POST `/publications/data`) behind HTTP
Basic Auth. The defaults below match the docker-compose credentials;
override via FUSEKI_USER / FUSEKI_PASSWORD env vars if you change the
compose file. The same defaults work in CI (the workflow's services.fuseki
block sets ADMIN_PASSWORD=admin), so no env-var configuration is needed
for local or CI runs.
"""

import os
import sys
import time

import requests

FUSEKI_DATA_URL = "http://localhost:3030/publications/data"
FUSEKI_PING = "http://localhost:3030/$/ping"
TTL_FILE = "data/publications.ttl"
FUSEKI_USER = os.getenv("FUSEKI_USER", "admin")
FUSEKI_PASSWORD = os.getenv("FUSEKI_PASSWORD", "admin")


def wait_for_fuseki(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if requests.get(FUSEKI_PING, timeout=2).status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(1)
    return False


def main():
    if not wait_for_fuseki():
        raise RuntimeError("Fuseki did not respond on http://localhost:3030 within 60s.")
    with open(TTL_FILE, "rb") as f:
        payload = f.read()
    r = requests.post(
        FUSEKI_DATA_URL,
        data=payload,
        headers={"Content-Type": "text/turtle"},
        auth=(FUSEKI_USER, FUSEKI_PASSWORD),
        timeout=30,
    )
    r.raise_for_status()
    print(f"Loaded {TTL_FILE} into {FUSEKI_DATA_URL} (status {r.status_code}).")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"load_dataset failed: {exc}", file=sys.stderr)
        sys.exit(1)
