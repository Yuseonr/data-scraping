import asyncio
import os
import sys
import json
from pathlib import Path

project_root = Path(__file__).parent
gmaps_folder = project_root / "gmaps-extractor"
sys.path.append(str(gmaps_folder))

from src.area import bbox_to_polygon, build_hex_grid, save_area_manifest
from src.runner import run_scrape
from src.state import StateDB
from src.export import deduplicate, filter_places, get_stats

async def main():
    print("=== GMAPS-EXTRACTOR END-TO-END TEST ===")
    
    base_dir = Path("gmaps-extractor/data/result_test")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    area_path = base_dir / "test_area.json"
    db_path = base_dir / "test_state.sqlite"
    output_path = base_dir / "test_places.csv"
    clean_path = base_dir / "test_places_clean.csv"
    filtered_path = base_dir / "test_places_filtered.csv"
    
    for p in [area_path, db_path, output_path, clean_path, filtered_path]:
        if p.exists():
            p.unlink()

    print("\n--- 1. Building Area ---")
    poly = bbox_to_polygon(-7.03313, -7.025, 110.40888, 110.41833)
    cells = build_hex_grid(poly, resolution=9)
    cells = cells[:3]
    
    print(f"Generated {len(cells)} cells.")
    save_area_manifest(cells, resolution=9, path=area_path, source="test_script")
    print(f"Area manifest saved to {area_path}")
    
    keywords = ["warung", "kafe"]
    print(f"\n--- 2. Starting Scrape Run ---")
    print(f"Keywords: {keywords}")
    print(f"Workers: 2")
    
    await run_scrape(
        area_path=str(area_path),
        keywords=keywords,
        db_path=str(db_path),
        output_path=str(output_path),
        n_workers=2,
        headless=False, 
        filter_address="semarang" 
    )
    
    print("\n--- 3. Checking State DB directly ---")
    db = StateDB(db_path)
    progress = db.get_progress()
    print("Final State DB Progress:")
    print(json.dumps(progress, indent=2))
    db.close()
    
    if output_path.exists():
        print("\n--- 4. Testing Export Features ---")
        
        print("\n[Stats before cleaning]")
        stats_raw = get_stats(str(output_path))
        print(json.dumps(stats_raw, indent=2))
        
        print("\n[Deduplicating]")
        deduplicate(str(output_path), str(clean_path))
        
        print("\n[Filtering (min 5 reviews, exclude closed)]")
        filter_places(str(clean_path), str(filtered_path), min_reviews=5, exclude_closed=True)
        
        print("\n[Stats after filtering]")
        stats_final = get_stats(str(filtered_path))
        print(json.dumps(stats_final, indent=2))
    else:
        print("\nNo output file was created, scrape might have failed or found no places.")

    print("\n=== TEST COMPLETED ===")

if __name__ == "__main__":
    asyncio.run(main())