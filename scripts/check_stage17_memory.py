import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from prithi_memory import MemoryStore, extract_memory_candidates


def main() -> None:
    store = MemoryStore()
    with sqlite3.connect(store.db_path) as connection:
        print(f"Profiles: {connection.execute('SELECT COUNT(1) FROM profiles').fetchone()[0]}")
        print(f"Relationships: {connection.execute('SELECT COUNT(1) FROM relationships').fetchone()[0]}")
        print(f"Saved memories: {connection.execute('SELECT COUNT(1) FROM memory_items').fetchone()[0]}")
    sample = "আমি কফির চেয়ে বেশি চা পছন্দ করি"
    result = extract_memory_candidates(sample)
    print(f"Bengali STT preference rule: {'matched' if result else 'not matched'}")


if __name__ == "__main__":
    main()
