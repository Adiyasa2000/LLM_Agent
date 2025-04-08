import geopandas as gpd
import pandas as pd
import json
import time
import os

TARGET_CRS = "EPSG:25832"

# ✅ AGENT WRAPPER / MAIN LOGIC
def analyze_natura2000_main(basin_gdf_path, habitat_path, bird_path, basin_identifier, kommune):
    """
    Loads data and checks if a basin overlaps Natura 2000 habitat/bird areas.
    Returns a compact JSON result. Max ~120 lines target.
    """
    result_data = {}
    try:
        # --- 1. Load Basin Data & Filter ---
        basin_gdf_full = gpd.read_file(basin_gdf_path)
        basin_gdf = basin_gdf_full[basin_gdf_full["Kommune"].str.lower() == kommune.lower()].copy()
        if basin_gdf.empty:
            raise ValueError(f"Ingen bassiner fundet i kommune '{kommune}'")

        # --- 2. Find Specific Basin ---
        ident_str = str(basin_identifier)
        basin_filter = (basin_gdf["New_FID"].astype(str) == ident_str) | \
                       (basin_gdf["Frakmt"] == ident_str) | \
                       (basin_gdf["Stedfaestelse"] == ident_str)
        selected_basin = basin_gdf[basin_filter]
        if selected_basin.empty:
            raise ValueError(f"Bassin ID '{ident_str}' ikke fundet i '{kommune}'")

        # --- 3. CRS Conversion & Geometry Prep ---
        if selected_basin.crs != TARGET_CRS:
            selected_basin = selected_basin.to_crs(epsg=TARGET_CRS)
        basin_geom = selected_basin.geometry.iloc[0]
        bbox = basin_geom.buffer(10).bounds # Small buffer for loading N2K

        # --- 4. Load & Process N2K Data ---
        habitat_gdf = gpd.read_file(habitat_path, bbox=bbox)
        bird_gdf = gpd.read_file(bird_path, bbox=bbox)

        if not habitat_gdf.empty and habitat_gdf.crs != TARGET_CRS:
             habitat_gdf = habitat_gdf.to_crs(epsg=TARGET_CRS)
        if not bird_gdf.empty and bird_gdf.crs != TARGET_CRS:
             bird_gdf = bird_gdf.to_crs(epsg=TARGET_CRS)

        # --- 5. Intersection Checks (using spatial index) ---
        h_idx = list(habitat_gdf.sindex.intersection(basin_geom.bounds))
        intersecting_habitat = habitat_gdf.iloc[h_idx][habitat_gdf.iloc[h_idx].geometry.intersects(basin_geom)]

        b_idx = list(bird_gdf.sindex.intersection(basin_geom.bounds))
        intersecting_bird = bird_gdf.iloc[b_idx][bird_gdf.iloc[b_idx].geometry.intersects(basin_geom)]

        # --- 6. Construct Result ---
        habitat_overlap = "ja" if not intersecting_habitat.empty else "nej"
        bird_overlap = "ja" if not intersecting_bird.empty else "nej"

        if habitat_overlap == "ja" or bird_overlap == "ja":
            result_data = {"natura2000_i_nærheden": "ja"}
            result_data["habitatomraade"] = habitat_overlap
            if habitat_overlap == "ja":
                h_name = intersecting_habitat.iloc[0].get("Objektnavn")
                result_data["habitat_navn"] = str(h_name) if pd.notna(h_name) else "Ukendt navn"

            result_data["fugleomraade"] = bird_overlap
            if bird_overlap == "ja":
                b_name = intersecting_bird.iloc[0].get("Objektnavn")
                result_data["fugle_navn"] = str(b_name) if pd.notna(b_name) else "Ukendt navn"
        else:
            result_data = {"natura2000_i_nærheden": "nej"}

    except Exception as e:
        # General error handling for brevity
        result_data = {
            "bassin_id_input": str(basin_identifier) if basin_identifier else "Ukendt",
            "kommune_input": kommune,
            "fejl": f"Fejl under analyse: {type(e).__name__} - {e}"
        }

    # Final structured output
    return {"kategori": "Natura 2000", "data": result_data}

# ✅ TEST BLOCK
if __name__ == "__main__":
    print("Running test for check_natura2000.py (relative paths)...")
    start = time.perf_counter()
    test_result = analyze_natura2000_main(
        basin_gdf_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'BASIN_FINAL.gpkg'),
        habitat_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'natura_2000_habitatomraader.gpkg'),
        bird_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'natura_2000_fugleomraader.gpkg'),
        basin_identifier="50-0 19/0292 Højre", 
        kommune="Aabenrå"                     
    )
    duration = time.perf_counter() - start
    print(json.dumps(test_result, indent=2, ensure_ascii=False))
    print(f"⏱️ Tid: {duration:.2f}s")