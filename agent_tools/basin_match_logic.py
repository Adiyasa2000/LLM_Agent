import pandas as pd
import os
import time
from typing import Optional, Dict, Any, List # Tilføjet List

# --- Konfiguration ---
CSV_FRAKMT_COL = "Frakmt"  # Collumn Basin ID in CSV
CSV_KOMMUNE_COL = "Kommune" # Collumn with Kommune in CSV
CACHE = {"df": None, "load_time": 0}
CACHE_DURATION = 3600 # Cache DataFrame i 1 time

def _load_data() -> Optional[pd.DataFrame]:
    """Indlæser CSV med korrekt encoding, separator og caching."""
    now = time.time()
    if CACHE["df"] is not None and (now - CACHE["load_time"] < CACHE_DURATION):
        return CACHE["df"].copy() # Returner cachet kopi

    csv_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'ID-Betegnelser.csv')
    if not os.path.exists(csv_path):
        print(f"FEJL: Master list fil ikke fundet: {csv_path}")
        return None
    try:
        # Læs med cp1252 (Windows ANSI) og komma-separator
        df = pd.read_csv(csv_path, encoding='cp1252', dtype=str, sep=',')
        df.columns = [col.strip() for col in df.columns]
        if CSV_KOMMUNE_COL not in df.columns or CSV_FRAKMT_COL not in df.columns:
             raise ValueError(f"CSV mangler påkrævede kolonner: {CSV_KOMMUNE_COL} / {CSV_FRAKMT_COL}")
        df[[CSV_KOMMUNE_COL, CSV_FRAKMT_COL]] = df[[CSV_KOMMUNE_COL, CSV_FRAKMT_COL]].fillna('')
        CACHE["df"] = df
        CACHE["load_time"] = now
        print(f"Master list '{os.path.basename(csv_path)}' loaded/reloaded.")
        return df.copy()
    except Exception as e:
        print(f"FEJL primær indlæsning ({csv_path}): {type(e).__name__} - {e}")
        # Fallback forsøg (f.eks. hvis ANSI ikke er cp1252)
        try:
            print("... forsøger fallback med latin-1 encoding...")
            df = pd.read_csv(csv_path, encoding='latin-1', dtype=str, sep=',')
            df.columns = [col.strip() for col in df.columns]
            if CSV_KOMMUNE_COL not in df.columns or CSV_FRAKMT_COL not in df.columns:
                raise ValueError("Fallback fejlede også: Kolonner mangler.")
            df[[CSV_KOMMUNE_COL, CSV_FRAKMT_COL]] = df[[CSV_KOMMUNE_COL, CSV_FRAKMT_COL]].fillna('')
            CACHE["df"] = df
            CACHE["load_time"] = now
            print(f"Fallback succes med encoding='latin-1'.")
            return df.copy()
        except Exception as e_fallback:
             print(f"FEJL: Fallback fejlede også: {type(e_fallback).__name__} - {e_fallback}")
             CACHE["df"] = None
             return None

def _normalize(text: Optional[str]) -> str:
    """Normaliserer til lowercase og håndterer danske tegn for søgning."""
    if not text:
        return ''
    text = str(text).lower().strip()
    text = text.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    return text

# ✅ AGENT WRAPPER / MAIN LOGIC (Forkortet, med rettet listebygning)
def find_basin_entries_main(kommune_query: Optional[str] = None, basin_id_query: Optional[str] = None) -> Dict[str, Any]:
    """Søger i master basin listen for at finde bassiner."""
    if not kommune_query and not basin_id_query:
        return {"status": "no_query", "message": "Angiv kommune eller bassin ID."}

    df = _load_data()
    if df is None:
        return {"status": "error", "message": "Kunne ikke indlæse master listen."}

    # Anvend filtre sekventielt
    mask = pd.Series(True, index=df.index) # Start med at inkludere alt
    if kommune_query:
        norm_query = _normalize(kommune_query)
        mask &= df[CSV_KOMMUNE_COL].apply(_normalize).str.contains(norm_query, na=False)
    if basin_id_query:
        norm_query = _normalize(basin_id_query)
        mask &= df[CSV_FRAKMT_COL].apply(_normalize).str.contains(norm_query, na=False)

    results_df = df[mask]
    num_results = len(results_df)

    # --- Konstruer output ---
    if num_results == 0:
        return {"status": "not_found", "message": "Ingen bassiner matchede kriterierne."}

    elif num_results == 1:
        match = results_df.iloc[0]
        return {
            "status": "found_exact",
            "basin_identifier": match[CSV_FRAKMT_COL], # Returner den præcise værdi
            "kommune": match[CSV_KOMMUNE_COL]          # Returner den præcise værdi
        }

    else: # Flere resultater
        # *** RETTELSE: Byg listen manuelt for korrekt format ***
        matches_list: List[Dict[str, str]] = [] # Definer type for klarhed
        for index, row in results_df.iterrows():
            matches_list.append({
                'identifier': row[CSV_FRAKMT_COL], # Korrekt nøglenavn
                'kommune': row[CSV_KOMMUNE_COL]    # Korrekt nøglenavn
            })
        # *** Slut på rettelse ***

        # Simpel besked (kan udbygges af agenten hvis nødvendigt)
        message = f"Fandt {num_results} mulige bassiner. Præciser venligst."
        if num_results <= 15: # Vis detaljer hvis få resultater
             details = "\n".join([f"- ID: {m['identifier']} ({m['kommune']})" for m in matches_list])
             message += f"\n{details}"

        return {
            "status": "found_multiple",
            "count": num_results,
            "message_to_user": message,
            "matches_data": matches_list
        }

# ✅ TEST BLOCK
if __name__ == '__main__':
    import json
    print("--- Test Basin Match Logic ---")

    # === TEST ===
    test_kommune = 'Køge'
    test_id = None
    # ======================================

    print(f"Input -> Kommune: '{test_kommune}', ID: '{test_id}'")
    result = find_basin_entries_main(kommune_query=test_kommune, basin_id_query=test_id)
    print("\nOutput:")
    print(json.dumps(result, indent=2, ensure_ascii=False))