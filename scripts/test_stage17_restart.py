import argparse
import os
import secrets
import sys
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from prithi_memory import MemoryStore, stable_user_id


def seed(store: MemoryStore, identity: str) -> None:
    user_id = stable_user_id(identity)
    store.update_profile(user_id, preferred_language="bengali", display_name="Restart Test")
    store.save_relationship(
        user_id,
        {"familiarity": .42, "trust": .31, "affection": .27, "playfulness": .20, "romantic_tension": .08},
        "warm",
        "caring",
    )
    for content in ("Prefers tea over coffee.", "Enjoys Bengali conversation.", "Works nights."):
        store.add_memory(user_id, "preference", content, .8)
    print("Seeded restart test: relationship=yes, memories=3")


def check(store: MemoryStore, identity: str) -> None:
    token = os.environ.get("PRITHI_WEB_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("PRITHI_WEB_ACCESS_TOKEN is missing")
    headers = {"Authorization": f"Bearer {token}", "X-Prithi-User": identity}
    response = httpx.get(
        "http://127.0.0.1:8000/api/memory",
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    body = response.json()
    assert body["saved_memory_count"] == 3
    assert body["relationship_restored"] is True
    assert body["relationship"]["familiarity"] == .42
    assert body["profile"]["preferred_language"] == "bengali"

    other_identity = secrets.token_urlsafe(32)
    isolated = httpx.get(
        "http://127.0.0.1:8000/api/memory",
        headers={**headers, "X-Prithi-User": other_identity},
        timeout=20,
    )
    isolated.raise_for_status()
    other = isolated.json()
    assert other["saved_memory_count"] == 0
    assert other["relationship"] is None
    store.delete_user_memory(stable_user_id(other_identity))
    print("Restart restore: relationship=yes, memories=3, user_isolation=yes")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("seed", "check", "cleanup"))
    parser.add_argument("--identity", required=True)
    args = parser.parse_args()
    store = MemoryStore()
    user_id = stable_user_id(args.identity)
    if args.mode == "seed":
        seed(store, args.identity)
    elif args.mode == "check":
        check(store, args.identity)
    else:
        store.delete_user_memory(user_id)
        print("Restart test data removed")


if __name__ == "__main__":
    main()
