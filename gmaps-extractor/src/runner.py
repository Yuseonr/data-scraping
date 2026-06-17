import asyncio
import csv
import json
from pathlib import Path

from .area import load_area_manifest
from .browser import BrowserPool, random_delay
from .schema import Place, FIELDNAMES
from .scraper import search_cell, extract_place, parse_place_id
from .state import StateDB


_csv_lock = asyncio.Lock()


def _init_csv(path: str):
    p = Path(path)
    if not p.exists():
        with open(p, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writeheader()


async def _append_place(path: str, place: Place):
    async with _csv_lock:
        with open(path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(place.to_row())


async def _worker(
    worker_id: int,
    db: StateDB,
    cell_map: dict[str, tuple[float, float]],
    page,
    output_path: str,
    filter_address: str | None,
    headed: bool,
) -> int:
    """Process tasks from the DB until none remain. Returns count of new places found."""
    found = 0

    while True:
        task = db.claim_next(worker_id)
        if not task:
            break

        cell_id, keyword = task
        lat, lng = cell_map[cell_id]

        try:
            hrefs = await search_cell(
                page, lat, lng, keyword,
                seen_fn=db.is_seen,
                headed=headed,
                worker_id=worker_id,
            )

            for href in hrefs:
                pid = parse_place_id(href)
                if pid and db.is_seen(pid):
                    continue

                place = await extract_place(page, href, filter_address, headed, worker_id)
                if place and not db.is_seen(place.place_id):
                    place.source_cell_id = cell_id
                    place.search_keyword = keyword
                    db.mark_seen(place.place_id)
                    await _append_place(output_path, place)
                    found += 1

            db.mark_done(cell_id, keyword)

        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"[Worker {worker_id}] Error on ({cell_id}, {keyword}): {e}")
            db.mark_failed(cell_id, keyword, str(e))

        await random_delay(1.0, 2.0)

    return found


async def run_scrape(
    area_path: str,
    keywords: list[str],
    db_path: str,
    output_path: str,
    n_workers: int = 3,
    headless: bool = True,
    limit_cells: int | None = None,
    filter_address: str | None = None,
    locale: str = "id-ID",
    retry_failed: bool = False,
):
    cells, meta = load_area_manifest(area_path)
    if limit_cells:
        cells = cells[:limit_cells]

    cell_map = {c.id: (c.lat, c.lng) for c in cells}
    cell_ids = [c.id for c in cells]

    db = StateDB(db_path)
    db.init_tasks(cell_ids, keywords)
    db.release_stale()

    if retry_failed:
        db.reset_failed()

    # store run config
    db.set_meta("area_path", area_path)
    db.set_meta("keywords", json.dumps(keywords))
    db.set_meta("n_workers", str(n_workers))

    _init_csv(output_path)
    progress = db.get_progress()
    total = progress["total"]
    done = progress["done"]

    print(f"Cells: {len(cells)} | Keywords: {len(keywords)} | Total tasks: {total}")
    print(f"Already done: {done} | Pending: {progress['pending']} | Failed: {progress['failed']}")
    print(f"Unique places found so far: {progress['unique_places']}")
    print(f"Workers: {n_workers} | Headless: {headless}\n")

    async with BrowserPool(n_workers, headless=headless, locale=locale) as pool:
        tasks = []
        for wid in range(n_workers):
            page = pool.get_page(wid)
            t = asyncio.create_task(
                _worker(wid, db, cell_map, page, output_path, filter_address, not headless)
            )
            tasks.append(t)

        try:
            results = await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            print("\n[Stopped] Progress saved in DB.")
            for t in tasks:
                t.cancel()
            results = [0]

    new_total = sum(results)
    final = db.get_progress()
    print(f"\nDone. New places scraped: {new_total}")
    print(f"Total unique places: {final['unique_places']}")
    print(f"Tasks done: {final['done']}/{final['total']} | Failed: {final['failed']}")
    print(f"Output: {output_path}")

    db.close()
