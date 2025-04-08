import geopandas as gpd

def load_nature_data_near_basin(basin_gdf_path, nature_path, kommune, buffer_m=5000):
    """
    Loads basin geometries for a specific kommune and filters nature GPKG using a bounding box around the basin.
    Speeds up loading large datasets.
    """
    basin_gdf = gpd.read_file(basin_gdf_path)
    basin_gdf = basin_gdf[basin_gdf["Kommune"].str.lower() == kommune.lower()]
    if basin_gdf.empty:
        raise ValueError(f"Ingen bassiner fundet i kommune '{kommune}'")

    basin_geom = basin_gdf.geometry.union_all()
    bbox = basin_geom.buffer(buffer_m).bounds  # (minx, miny, maxx, maxy)
    nature_gdf = gpd.read_file(nature_path, bbox=bbox)

    return basin_gdf, nature_gdf


def analyze_protected_nature_compact(basin_gdf, nature_gdf, basin_identifier, kommune=None, buffer=100):
    """
    Analyzes protected nature based on basin-ID and distance
    """
    if kommune is not None:
        basin_gdf = basin_gdf[basin_gdf["Kommune"].str.lower() == kommune.lower()]
        if basin_gdf.empty:
            return {
                "kategori": "Beskyttet natur",
                "data": {
                    "bassin_id": str(basin_identifier),
                    "fejl": f"Ingen bassin fundet i kommune '{kommune}'"
                }
            }

    if basin_identifier is None:
        return {
            "kategori": "Beskyttet natur",
            "data": {
                "bassin_id": None,
                "fejl": "Bassinidentifier mangler"
            }
        }

    ident_str = str(basin_identifier)
    basin_filter = (basin_gdf["New_FID"].astype(str) == ident_str) | \
                   (basin_gdf["Frakmt"] == ident_str) | \
                   (basin_gdf["Stedfaestelse"] == ident_str)
    selected = basin_gdf[basin_filter]

    if selected.empty:
        fejl_msg = f"Ingen bassin fundet med identifier '{basin_identifier}'"
        if kommune:
            fejl_msg += f" i kommune '{kommune}'"
        return {
            "kategori": "Beskyttet natur",
            "data": {
                "bassin_id": ident_str,
                "fejl": fejl_msg
            }
        }

    basin_geom = selected.geometry.union_all()
    clip_buffer = basin_geom.buffer(3000)

    nature_clipped = nature_gdf[nature_gdf.geometry.intersects(clip_buffer)].copy()

    initial = nature_clipped[nature_clipped.geometry.intersects(basin_geom)]
    initial_ids = set(initial.index)

    buffer_geom = basin_geom.buffer(buffer)
    nearby = nature_clipped[nature_clipped.geometry.intersects(buffer_geom)]
    nearby_ids = set(nearby.index)

    connected_ids = initial_ids | nearby_ids

    if connected_ids:
        while True:
            current_geom_union = nature_clipped.loc[list(connected_ids)].geometry.union_all()
            expanded_filter = nature_clipped.geometry.touches(current_geom_union) | \
                              nature_clipped.geometry.intersects(current_geom_union)
            new_ids = set(nature_clipped[expanded_filter].index) - connected_ids
            if not new_ids:
                break
            connected_ids.update(new_ids)

    is_protected_in_basin = "ja" if not initial.empty else "nej"
    is_connected_nearby = "ja" if connected_ids and (connected_ids - initial_ids) else "nej"

    total_area_str = "0 m²"
    nature_types = []

    if connected_ids:
        connected_nature = nature_clipped.loc[list(connected_ids)]
        try:
            connected_nature_proj = connected_nature.to_crs(epsg=25832)
            total_area = round(connected_nature_proj.geometry.area.sum())
            total_area_str = f"{total_area} m²"
        except Exception:
            total_area_str = "Ukendt (arealfejl)"

        if "Natyp_navn" in connected_nature.columns:
            nature_types = connected_nature["Natyp_navn"].dropna().unique().tolist()
        else:
            nature_types = ["Ukendt (felt mangler)"]

    return {
        "kategori": "Beskyttet natur",
        "data": {
            "bassin_id": ident_str,
            "registreret_som_beskyttet": is_protected_in_basin,
            "i_sammenhæng_med_beskyttet_natur": is_connected_nearby,
            "naturtype": nature_types,
            "areal": total_area_str
        }
    }


# ✅ AGENT WRAPPER
def analyze_protected_nature_main(basin_gdf_path, nature_path, basin_identifier, kommune, buffer=100):
    basin_gdf, nature_gdf = load_nature_data_near_basin(
        basin_gdf_path, nature_path, kommune, buffer_m=5000
    )
    return analyze_protected_nature_compact(basin_gdf, nature_gdf, basin_identifier, kommune, buffer)


# ✅ TEST BLOCK 
if __name__ == "__main__":
    import os
    import json
    import time

    print(f"Running test for check_protected_nature.py (relative paths)...")
    start = time.perf_counter()
    result = analyze_protected_nature_main(
        basin_gdf_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'BASIN_FINAL.gpkg'),
        nature_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'beskyttede_naturtyper.gpkg'),
        basin_identifier="20-0 43/0563 Højre",
        kommune="Køge",
        buffer=100
    )
    duration = time.perf_counter() - start

    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n⏱️  Tid brugt: {duration:.2f} sekunder")