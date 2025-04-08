import geopandas as gpd
import pandas as pd
import json
import time
import os

TARGET_CRS = "EPSG:25832"

def get_str_val(row, field):
    """Safely gets string value from GeoDataFrame row or Series."""
    # Check if input is a Series (from iloc[0]) or a row (from iterrows)
    if isinstance(row, pd.Series):
        val = row.get(field)
    else: # Assume it's a tuple from iterrows or similar
        val = getattr(row, field, None) # Failsafe for attribute access if needed
    return str(val) if pd.notna(val) else "Ukendt"

# ✅ AGENT WRAPPER / MAIN LOGIC
def analyze_vp3_streams_main(basin_gdf_path, stream_path, kystvand_path, basin_identifier, kommune, distance=100):
    """
    Loads data, analyzes proximity of the *closest* VP3 stream and coastal catchment overlap.
    Returns a compact JSON result.
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
        buffer_geom = basin_geom.buffer(distance)
        bbox = buffer_geom.bounds # Bbox based on buffer for loading

        # --- 4. Load & Process Streams ---
        stream_gdf = gpd.read_file(stream_path, bbox=bbox)
        if not stream_gdf.empty and stream_gdf.crs != TARGET_CRS:
            stream_gdf = stream_gdf.to_crs(epsg=TARGET_CRS)

        # Use spatial index efficiently
        possible_stream_idx = list(stream_gdf.sindex.intersection(buffer_geom.bounds))
        intersecting_streams = stream_gdf.iloc[possible_stream_idx]
        intersecting_streams = intersecting_streams[intersecting_streams.geometry.intersects(buffer_geom)].copy()

        # --- 5. Process Results (Closest Stream Only) ---
        if intersecting_streams.empty:
            result_data = {"vandloeb_i_naerhed": "nej"}
        else:
            intersecting_streams['distance'] = intersecting_streams.geometry.distance(basin_geom)
            intersecting_streams = intersecting_streams.sort_values(by='distance')

            # Get the single closest stream
            closest_stream = intersecting_streams.iloc[0] # This is now a Pandas Series

            # --- 6. Load & Process Kystvandoplande (only if streams found) ---
            kystvand_gdf = gpd.read_file(kystvand_path) # Load fully
            if kystvand_gdf.crs != TARGET_CRS:
                 kystvand_gdf = kystvand_gdf.to_crs(epsg=TARGET_CRS)

            kyst_possible_idx = list(kystvand_gdf.sindex.intersection(basin_geom.bounds))
            intersecting_catchments = kystvand_gdf.iloc[kyst_possible_idx]
            intersecting_catchments = intersecting_catchments[intersecting_catchments.geometry.intersects(basin_geom)]

            kystvandopland_navn = "Ukendt"
            if not intersecting_catchments.empty:
                kyst_name = intersecting_catchments.iloc[0].get("kystom_2na")
                if pd.notna(kyst_name):
                    kystvandopland_navn = str(kyst_name)

            # Populate result_data with details of the closest stream
            result_data = {
                "vandloeb_i_naerhed": "ja",
                "nærmeste_vandløb_afstand": f"{round(closest_stream['distance'])} m",
                "nærmeste_vandløb_navn": get_str_val(closest_stream, "os_navn"),
                "nærmeste_vandløb_kategori": get_str_val(closest_stream, "na_kun_stm"),
                "nærmeste_vandløb_type": get_str_val(closest_stream, "ov_typ"),
                "nærmeste_vandløb_økologisk_tilstand": get_str_val(closest_stream, "til_oko_sm"),
                "nærmeste_vandløb_økologiske_mål": get_str_val(closest_stream, "mal_oko_sm"),
                "nærmeste_vandløb_kemi_tilstand": get_str_val(closest_stream, "ov_til_kem"),
                "nærmeste_vandløb_kemi_mål": get_str_val(closest_stream, "ov_mal_kem"),
                "nærmeste_vandløb_fysisk_tilstand": get_str_val(closest_stream, "til_oko_fk"),
                "nærmeste_vandløb_fysisk_mål": get_str_val(closest_stream, "mål_oko_fk"),
                "kystvandopland_navn": kystvandopland_navn
            }

    except Exception as e:
        # General error handling for brevity
        result_data = {
            "bassin_id_input": str(basin_identifier) if basin_identifier else "Ukendt",
            "kommune_input": kommune,
            "fejl": f"Fejl under analyse: {type(e).__name__} - {e}"
        }

    # Final structured output
    return {"kategori": "VP3 Vandløb & Kystvandopland", "data": result_data}

# ✅ TEST BLOCK
if __name__ == "__main__":
    print("Running test for Check_vp3_streams.py (relative paths)...")
    start = time.perf_counter()
    test_result = analyze_vp3_streams_main(
        basin_gdf_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'BASIN_FINAL.gpkg'),
        stream_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'vp3_vandloeb.gpkg'),
        kystvand_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'Kystvandoplande.gpkg'),
        basin_identifier="20-0 40/0513 Venstre",
        kommune="Køge",
        distance=150
    )
    duration = time.perf_counter() - start
    print(json.dumps(test_result, indent=2, ensure_ascii=False))
    print(f"⏱️ Tid: {duration:.2f}s")