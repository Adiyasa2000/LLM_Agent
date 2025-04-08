import geopandas as gpd
import pandas as pd
from pandas import Timestamp
import time
import json
import os # For path checking in test block

# Define columns to retrieve from the basin GPKG
BASIN_ATTRIBUTE_COLUMNS = [
    "Dato for seneste oprensning", "Dato for seneste oprensning af ind/udloeb",
    "Dato for seneste aarlige vedligehold", "Dato for seneste screening",
    "Bassintype", "Generel bedoemmelse", "Adgang til bassin via", "Bemaerkning"
]

# Define potential identifier columns in the GPKG
IDENTIFIER_COLS = ["New_FID", "Frakmt", "Stedfaestelse"]


def _format_value(value):
    """Helper to format dates or convert others to string, handles NA."""
    if pd.isna(value):
        return None # Explicitly return None for missing values
    if isinstance(value, Timestamp):
        try:
            return value.strftime("%Y-%m-%d") # Consistent date format
        except ValueError:
            return str(value) # Fallback
    # Ensure empty strings are also treated as 'None' for clarity
    str_value = str(value).strip()
    return str_value if str_value else None


# ✅ AGENT WRAPPER / MAIN LOGIC
def get_basin_attributes_main(basin_gpkg_path: str, basin_identifier: str, kommune: str) -> dict:
    """
    Retrieves specific attributes for a SINGLE, precisely identified basin
    from the main basin GeoPackage file. Uses exact identifier and kommune.
    Explicitly marks attributes with no registered data.

    Args:
        basin_gpkg_path: Path to the main basin GeoPackage (e.g., BASIN_FINAL.gpkg).
        basin_identifier: The EXACT basin identifier (must match a value in IDENTIFIER_COLS).
        kommune: The EXACT kommune name associated with the basin.

    Returns:
        dict: Structured result with 'kategori', 'data' (containing attributes or 'fejl').
              Attributes dictionary includes all requested columns found for the basin;
              those without data are marked with 'Ingen data registreret'.
    """
    start_time = time.time()
    result_data = {"basin_id_input": basin_identifier, "kommune_input": kommune} # Store inputs
    NO_DATA_STRING = "Ingen data registreret" # Standard text for missing values

    try:
        # --- 1. Load Basin Data & Filter by Kommune ---
        basin_gdf_full = gpd.read_file(basin_gpkg_path)
        # Add .copy() to potentially avoid SettingWithCopyWarning later
        basin_gdf_kommune = basin_gdf_full[basin_gdf_full["Kommune"].str.lower() == kommune.lower()].copy()

        if basin_gdf_kommune.empty:
            raise ValueError(f"Ingen bassiner fundet for kommune '{kommune}' i filen.")

        # --- 2. Find Specific Basin using the EXACT identifier ---
        ident_str = str(basin_identifier)
        # Initialize filter with the correct index
        basin_filter = pd.Series([False] * len(basin_gdf_kommune), index=basin_gdf_kommune.index)
        for col in IDENTIFIER_COLS:
            if col in basin_gdf_kommune.columns: # Check if column exists
                 basin_filter |= (basin_gdf_kommune[col].astype(str) == ident_str)
        selected_basin = basin_gdf_kommune[basin_filter]

        # --- 3. Process Result ---
        if selected_basin.empty:
            result_data["fejl"] = f"Bassin ID '{ident_str}' ikke fundet i '{kommune}'."
        elif len(selected_basin) > 1:
            result_data["fejl"] = f"Dataintegritetsfejl: Flere ({len(selected_basin)}) bassiner fundet for unikt ID '{ident_str}' i '{kommune}'. Kontakt dataansvarlig."
        else:
            # Extract attributes for the single found basin
            attributes_raw = selected_basin.iloc[0].to_dict()
            formatted_attributes = {} # Initialize dict to store final attributes

            # Iterate through the DEFINED columns we care about
            for col_name in BASIN_ATTRIBUTE_COLUMNS:
                 # Clean the key name regardless of whether data exists
                 clean_key = col_name.replace("Dato for seneste ", "Senest ").replace("aarlige ", "")

                 if col_name in attributes_raw:
                     # Column exists for this basin, check its value
                     formatted_val = _format_value(attributes_raw[col_name])
                     if formatted_val is not None:
                         # Value exists and is formatted
                         formatted_attributes[clean_key] = formatted_val
                     else:
                         # Value is NA/None/Empty, explicitly mark it
                         formatted_attributes[clean_key] = NO_DATA_STRING
                 # Optional: Handle case where the column *doesn't exist at all* for this basin
                 # else:
                 #    formatted_attributes[clean_key] = "Attribut ikke fundet i data" # Might make output too verbose

            # Assign the dictionary, which now contains entries for all found columns
            result_data["attributes"] = formatted_attributes

    except FileNotFoundError:
        result_data["fejl"] = f"Filfejl: Basin GeoPackage ikke fundet: {basin_gpkg_path}"
    except ValueError as ve: # Catch specific expected errors
         result_data["fejl"] = str(ve)
    except Exception as e:
        result_data["fejl"] = f"Uventet fejl: {type(e).__name__} - {e}"

    duration = time.time() - start_time
    return {
        "kategori": "Bassin Attributter",
        "data": result_data,
        "time_used_seconds": round(duration, 2)
    }

# ✅ Minimal TEST BLOCK (No changes needed here)
if __name__ == "__main__":
    # --- Test Parameters ---
    gpkg_file = r"C:\Users\adiya\OneDrive\Dokumenter\AAU\10. Semester\Scripts\Geodata\VD\BASIN_FINAL.gpkg"
    target_id = "20-0 40/0513 Venstre"      # Known valid ID from GPKG
    target_kommune = "Køge"                 # Corresponding Kommune for the ID

    print(f"\n--- Testing: get_basin_attributes_main ---")
    print(f"Target -> ID: '{target_id}', Kommune: '{target_kommune}'")
    # Note: Assumes gpkg_file exists. Add os.path.exists(gpkg_file) check if needed.
    result = get_basin_attributes_main(gpkg_file, target_id, target_kommune)
    print(json.dumps(result, indent=2, ensure_ascii=False))