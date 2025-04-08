import geopandas as gpd
from pandas import Timestamp
import json
import time

def analyze_bilag_iv_arter(basin_gdf_path, species_gdf_path, basin_identifier, kommune=None, distance=2000):
    """
    Analyserer om der er registreret Bilag‑IV arter indenfor en given afstand fra et bassin.

    Indlæser data fra stier og matcher bassinet ud fra et fleksibelt identifier-felt.
    Returnerer struktureret output til videre brug i LLM-workflows.

    Args:
        basin_gdf_path (str): Sti til GeoPackage-fil med bassindata.
        species_gdf_path (str): Sti til GeoPackage-fil med Bilag IV-artsdata.
        basin_identifier (str): Identifier for bassinet (f.eks. New_FID, Frakmt, Stedfaestelse).
        kommune (str, optional): Kommunenavn til filtrering af bassiner. Defaults to None.
        distance (int, optional): Søgeafstand omkring bassinet i meter. Defaults to 2000.

    Returns:
        dict: Resultat-dictionary med 'kategori' og 'data' (eller 'fejl').
    """
    # Indlæs data
    try:
        basin_gdf = gpd.read_file(basin_gdf_path)
        species_gdf = gpd.read_file(species_gdf_path)
    except Exception as e:
        return {
            "kategori": "Bilag‑IV arter",
            "data": {
                "fejl": f"Fejl ved indlæsning af datafiler: {e}"
            }
        }

    # Filter på kommune hvis angivet
    if kommune is not None:
        basin_gdf = basin_gdf[basin_gdf["Kommune"].str.lower() == kommune.lower()]
        if basin_gdf.empty:
            return {
                "kategori": "Bilag‑IV arter",
                "data": {
                    "bassin_id": str(basin_identifier) if basin_identifier else None,
                    "fejl": f"Ingen bassin fundet i kommune '{kommune}'"
                }
            }

    if basin_identifier is None:
        return {
            "kategori": "Bilag‑IV arter",
            "data": {
                "bassin_id": None,
                "fejl": "Bassinidentifier mangler"
            }
        }

    ident_str = str(basin_identifier)
    # Robust matching across potential identifier columns
    basin_filter = (basin_gdf["New_FID"].astype(str) == ident_str) | \
                   (basin_gdf["Frakmt"] == ident_str) | \
                   (basin_gdf["Stedfaestelse"] == ident_str)
    selected = basin_gdf[basin_filter]

    if selected.empty:
        fejl_msg = f"Ingen bassin fundet med identifier '{basin_identifier}'"
        if kommune:
            fejl_msg += f" i kommune '{kommune}'"
        return {
            "kategori": "Bilag‑IV arter",
            "data": {
                "bassin_id": ident_str,
                "fejl": fejl_msg
            }
        }

    # Ensure consistent CRS (EPSG:25832 ETRS89 / UTM zone 32N is common in DK)
    try:
        target_crs = "EPSG:25832"
        if species_gdf.crs != target_crs:
            species_gdf = species_gdf.to_crs(epsg=25832)
        if selected.crs != target_crs:
             basin_geom_series = selected.geometry.to_crs(epsg=25832)
        else:
             basin_geom_series = selected.geometry

        basin_geom = basin_geom_series.union_all() # Use union_all for potential multi-part geometries

    except Exception as e:
         return {
            "kategori": "Bilag‑IV arter",
            "data": {
                "bassin_id": ident_str,
                "fejl": f"Fejl ved CRS transformation eller geometry operation: {e}"
            }
        }


    buffer_geom = basin_geom.buffer(distance)
    # Use spatial index if available (geopandas usually creates one on load)
    possible_matches_index = list(species_gdf.sindex.intersection(buffer_geom.bounds))
    species_subset = species_gdf.iloc[possible_matches_index]
    # Precise check
    species_nearby = species_subset[species_subset.geometry.intersects(buffer_geom)].copy() # Use copy to avoid SettingWithCopyWarning

    arter = []
    if not species_nearby.empty:
        species_nearby['distance_to_basin'] = species_nearby.geometry.distance(basin_geom)
        species_nearby = species_nearby.sort_values(by='distance_to_basin') # Sort by distance

        for _, row in species_nearby.iterrows():
            dist = round(row['distance_to_basin'])

            # Handle missing or non-timestamp date data gracefully
            dato_str = "Ukendt dato"
            dato = row.get("ObservationDate")
            if dato and isinstance(dato, Timestamp):
                try:
                    dato_str = dato.strftime("%Y-%m-%d") # Keep it simple date format
                except ValueError:
                    dato_str = str(dato) # Fallback if format fails
            elif dato:
                 dato_str = str(dato) # Use string representation if not timestamp

            arter.append({
                "observation_dato": dato_str,
                "dansk_navn": row.get("VernacularName", "Ukendt"),
                "artsgruppe": row.get("SpeciesGroupName", "Ukendt"),
                "afstand": f"{dist} m"
            })

    result_data = {
        "bassin_id": ident_str,
        "kommune": kommune if kommune else "Ikke specificeret",
        "soegningsafstand": f"{distance} m",
    }

    if arter:
        result_data.update({
            "arter_fundet_indenfor_afstand": "ja",
            "observationer": arter
        })
        return {"kategori": "Bilag‑IV arter", "data": result_data}
    else:
         result_data.update({
            "arter_fundet_indenfor_afstand": "nej",
            "observationer": f"Ingen Bilag-IV arter observeret indenfor {distance}m"
        })
         return {"kategori": "Bilag‑IV arter", "data": result_data}


# ✅ AGENT WRAPPER
def analyze_bilag_iv_arter_main(basin_gdf_path, species_gdf_path, basin_identifier, kommune=None, distance=2000):
    """
    Agent-callable wrapper for analyze_bilag_iv_arter.
    Loads data using paths and returns structured results.
    """
    return analyze_bilag_iv_arter(basin_gdf_path, species_gdf_path, basin_identifier, kommune, distance)


# ✅ TEST BLOCK 
if __name__ == "__main__":
    import os
    import time

    print(f"Running test for check_species_bilag_iv.py (relative paths)...")
    start = time.perf_counter()
    result = analyze_bilag_iv_arter_main(
        basin_gdf_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'BASIN_FINAL.gpkg'),
        species_gdf_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'bilag_iv_arter.gpkg'),
        basin_identifier="20-0 40/0513 Venstre",
        kommune="Køge",
        distance=2000
    )
    duration = time.perf_counter() - start

    # --- Output Results ---
    print("\n--- Resultat ---")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\n⏱️ Tid brugt: {duration:.2f} sekunder")