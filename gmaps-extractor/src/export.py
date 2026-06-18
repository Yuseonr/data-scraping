import csv
from collections import defaultdict

from .schema import FIELDNAMES


def _read_places(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_places(path: str, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def deduplicate(input_path: str, output_path: str):
    """Deduplicate by place_id, keeping the row with latest scraped_at."""
    rows = _read_places(input_path)
    best = {}
    for row in rows:
        pid = row.get("place_id", "")
        if not pid:
            continue
        existing = best.get(pid)
        if not existing or row.get("scraped_at", "") > existing.get("scraped_at", ""):
            best[pid] = row

    deduped = list(best.values())
    _write_places(output_path, deduped)
    print(f"Input: {len(rows)} rows → Output: {len(deduped)} unique places")
    print(f"Removed {len(rows) - len(deduped)} duplicates")
    print(f"Written to: {output_path}")


def filter_places(
    input_path: str,
    output_path: str,
    min_reviews: int | None = None,
    exclude_closed: bool = False,
):
    rows = _read_places(input_path)
    filtered = []
    for row in rows:
        if exclude_closed and row.get("permanently_closed", "").lower() == "true":
            continue
        if min_reviews is not None:
            try:
                reviews = int(row.get("total_reviews", 0) or 0)
            except (ValueError, TypeError):
                reviews = 0
            if reviews < min_reviews:
                continue
        filtered.append(row)

    _write_places(output_path, filtered)
    print(f"Input: {len(rows)} → Filtered: {len(filtered)}")
    print(f"Written to: {output_path}")


def get_stats(input_path: str) -> dict:
    rows = _read_places(input_path)
    unique_ids = set(r.get("place_id", "") for r in rows if r.get("place_id"))
    keywords = defaultdict(int)
    for r in rows:
        kw = r.get("search_keyword", "")
        if kw:
            keywords[kw] += 1

    stats = {
        "total_rows": len(rows),
        "unique_places": len(unique_ids),
        "duplicates": len(rows) - len(unique_ids),
        "by_keyword": dict(keywords),
    }
    return stats
