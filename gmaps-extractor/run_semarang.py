import asyncio
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.area import load_polygon, build_hex_grid, save_area_manifest
from src.runner import run_scrape
from src.export import deduplicate

async def main():
    script_dir = Path(__file__).parent
    base_dir = script_dir / "data/semarang_full"
    base_dir.mkdir(parents=True, exist_ok=True)
    
    area_path = base_dir / "area_semarang_res9.json"
    db_path = base_dir / "state_semarang.sqlite"
    output_path = base_dir / "places_semarang.csv"
    clean_path = base_dir / "places_semarang_clean.csv"
    
    if not area_path.exists():
        print("\n--- 1. Building Area from Shapefile ---")
        shp_path = script_dir / "data/batas-wilayah-semarang/semarang.shp"
        poly = load_polygon(shp_path)
        cells = build_hex_grid(poly, resolution=9)
        save_area_manifest(cells, resolution=9, path=area_path, source="semarang.shp")
        print(f"Area manifest saved with {len(cells)} cells.")
    else:
        print("\n--- 1. Area manifest already exists, skipping build ---")

    keywords = ["warung", "kafe", "kedai", "rumah makan", "angkringan"]
    print(f"\n--- 2. Starting/Resuming Scrape Run ---")
    print(f"Keywords: {keywords}")
    print(f"Workers: 5")
    
    await run_scrape(
        area_path=str(area_path),
        keywords=keywords,
        db_path=str(db_path),
        output_path=str(output_path),
        n_workers=3,
        headless=False,  
        filter_address="semarang",
        retry_failed=True  
    )
    
    if output_path.exists():
        print("\n--- 3. Running Final Deduplication ---")
        deduplicate(str(output_path), str(clean_path))
        print("Done! Check places_semarang_clean.csv for the final data.")

if __name__ == "__main__":
    asyncio.run(main())
