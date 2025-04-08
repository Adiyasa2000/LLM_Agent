import os
import json
from typing import Type, Dict, Any, Optional, List
from pydantic import BaseModel, Field
from pathlib import Path 

# --- Importer _main funktionerne fra agent_tools ---
try:
    from agent_tools.basin_match_logic import find_basin_entries_main as basin_match_logic_main
    from agent_tools.get_basin_attributes import get_basin_attributes_main
    from agent_tools.check_natura2000 import analyze_natura2000_main
    from agent_tools.check_protected_nature import analyze_protected_nature_main
    from agent_tools.check_species_bilag_iv import analyze_bilag_iv_arter_main
    from agent_tools.check_vp3_streams import analyze_vp3_streams_main
    # Brug alias for generate_map da navnet er generisk
    from agent_tools.generate_map import generate_map as generate_map_logic_main
    # Importer sanitize funktionen specifikt, da den bruges i GenerateMapTool's _run
    from agent_tools.generate_map import sanitize
    from agent_tools.generate_pdf import create_simple_report_main

except ImportError as e:
    print(f"Import FEJL: Kunne ikke importere fra 'agent_tools'. Sikr dig at tools.py køres fra 'basin_agent' mappen, eller at PYTHONPATH er sat.")
    print(f"Fejl detalje: {e}")
    # Definer dummy-funktioner for at undgå crash hvis import fejler under simpel kørsel
    def basin_match_logic_main(*args, **kwargs): return {"status": "error", "message": "Importfejl i tools.py"}
    def get_basin_attributes_main(*args, **kwargs): return {"kategori": "Fejl", "data": {"fejl": "Importfejl i tools.py"}}
    def analyze_natura2000_main(*args, **kwargs): return {"kategori": "Fejl", "data": {"fejl": "Importfejl i tools.py"}}
    def analyze_protected_nature_main(*args, **kwargs): return {"kategori": "Fejl", "data": {"fejl": "Importfejl i tools.py"}}
    def analyze_bilag_iv_arter_main(*args, **kwargs): return {"kategori": "Fejl", "data": {"fejl": "Importfejl i tools.py"}}
    def analyze_vp3_streams_main(*args, **kwargs): return {"kategori": "Fejl", "data": {"fejl": "Importfejl i tools.py"}}
    def generate_map_logic_main(*args, **kwargs): return "Importfejl i tools.py"
    def sanitize(text): return "sanitized_import_error"
    # *** NY DUMMY FUNKTION TILFØJET HER ***
    def create_simple_report_main(*args, **kwargs): print("Importfejl: create_simple_report_main ikke fundet."); return None

# ... (resten af imports som BaseTool, BaseModel etc. forbliver uændret) ...


# --- LangChain BaseTool Import ---
try:
    from langchain.tools import BaseTool
except ImportError:
    print("LangChain er ikke installeret. Installer med: pip install langchain")
    class BaseTool: # Simpel fallback
        name: str = "BaseTool"; description: str = "BaseTool description"; args_schema: Optional[Type[BaseModel]] = None
        def _run(self, *args, **kwargs): raise NotImplementedError
        def run(self, *args, **kwargs): return self._run(*args, **kwargs)


# === PATH HANDLING HELPER ===
def get_data_path(filename: str) -> str:
    """Konstruerer en relativ sti til en fil i data-mappen."""
    project_root = os.path.dirname(os.path.abspath(__file__)) # Sikrer absolut sti til rod
    data_path = os.path.join(project_root, 'data', filename)
    if not os.path.exists(data_path):
         # Giv en advarsel hvis en forventet datafil mangler ved opstart
         print(f"ADVARSEL: Forventet datafil ikke fundet: {data_path}")
    return data_path

def get_results_path(subfolder: Optional[str] = None) -> str:
    """Konstruerer en relativ sti til results-mappen (eller en undermappe)."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    results_path = os.path.join(project_root, 'results')
    if subfolder:
        results_path = os.path.join(results_path, subfolder)
    os.makedirs(results_path, exist_ok=True) # Sikrer at mappen findes
    return results_path


# === TOOL DEFINITIONS ===

# --- 1. Basin Match ---
class BasinMatchInput(BaseModel):
    kommune_query: Optional[str] = Field(None, description="Helt eller delvist kommune-navn at søge efter (f.eks. 'Køge', 'køg'). Case-insensitive.")
    basin_id_query: Optional[str] = Field(None, description="Helt eller delvist bassin ID at søge efter (f.eks. '40/0513', '0513 Højre'). Søger primært i Frakmt. Case-insensitive.")

class BasinMatchTool(BaseTool):
    name: str = "Basin_Match"
    description: str = (
        "**ALTID FØRSTE SKRIDT:** Finder og validerer bassiner i masterlisten (ID-Betegnelser.csv) "
        "baseret på kommune-navn (helt eller delvist) og/eller bassin ID (helt eller delvist). "
        "**SKAL bruges før andre analyseværktøjer** for at få korrekt `basin_identifier` og `kommune`. "
        "Kan også bruges til at liste alle bassiner i en kommune. "
        "Returnerer `status` ('found_exact', 'found_multiple', 'not_found') og tilhørende data (eksakte værdier eller liste/besked til brugeren)."
    )
    args_schema: Type[BaseModel] = BasinMatchInput

    def _run(self, kommune_query: Optional[str] = None, basin_id_query: Optional[str] = None) -> Dict[str, Any]:
        print(f"--- Running BasinMatchTool (Input: kommune='{kommune_query}', id='{basin_id_query}') ---")
        try:
            result = basin_match_logic_main(kommune_query=kommune_query, basin_id_query=basin_id_query)
            print(f"--- BasinMatchTool Output Status: {result.get('status')} ---")
            return result
        except Exception as e:
            print(f"ERROR in BasinMatchTool: {e}")
            return {"status": "error", "message": f"Uventet fejl under Basin_Match: {type(e).__name__}"}

# --- 2. Get Basin Attributes ---
class GetBasinAttributesInput(BaseModel):
    basin_identifier: str = Field(..., description="Det PRÆCISE basin identifier (typisk Frakmt værdi) returneret af `Basin_Match` værktøjet.")
    kommune: str = Field(..., description="Det PRÆCISE kommune navn returneret af `Basin_Match` værktøjet.")

class GetBasinAttributesTool(BaseTool):
    name: str = "Get_Basin_Attributes"
    description: str = (
        "Henter attribut-detaljer (datoer, type, vurdering etc.) for et specifikt bassin. "
        "Kræver det **eksakte** `basin_identifier` og `kommune` som returneret af `Basin_Match` værktøjet "
        "med status 'found_exact'."
    )
    args_schema: Type[BaseModel] = GetBasinAttributesInput

    def _run(self, basin_identifier: str, kommune: str) -> Dict[str, Any]:
        print(f"--- Running GetBasinAttributesTool (Input: id='{basin_identifier}', kommune='{kommune}') ---")
        try:
            basin_gpkg_path = get_data_path('BASIN_FINAL.gpkg')
            # Minimal check - _load_data i funktionen håndterer mere
            if not os.path.exists(basin_gpkg_path):
                return {"kategori": "Fejl", "data": {"fejl": f"Nødvendig datafil ikke fundet: {basin_gpkg_path}"}}
            result = get_basin_attributes_main(basin_gpkg_path=basin_gpkg_path, basin_identifier=basin_identifier, kommune=kommune)
            print(f"--- GetBasinAttributesTool Output Kategori: {result.get('kategori')} ---")
            return result
        except Exception as e:
            print(f"ERROR in GetBasinAttributesTool: {e}")
            return {"kategori": "Fejl", "data": {"fejl": f"Uventet fejl under Get_Basin_Attributes: {type(e).__name__}"}}

# --- 3. Check Natura2000 Overlap ---
class CheckNatura2000OverlapInput(BaseModel):
    basin_identifier: str = Field(..., description="Det PRÆCISE basin identifier returneret af `Basin_Match` værktøjet.")
    kommune: str = Field(..., description="Det PRÆCISE kommune navn returneret af `Basin_Match` værktøjet.")

class CheckNatura2000OverlapTool(BaseTool):
    name: str = "Check_Natura2000_Overlap"
    description: str = (
        "Udfører en spatial analyse for at vurdere, om et specifikt bassin (identificeret via `Basin_Match`) "
        "geografisk overlapper med Natura2000 habitat- eller fuglebeskyttelsesområder. "
        "Returnerer JSON-resultat, der angiver overlap ('ja'/'nej') for hver type og evt. områdenavne."
    )
    args_schema: Type[BaseModel] = CheckNatura2000OverlapInput

    def _run(self, basin_identifier: str, kommune: str) -> Dict[str, Any]:
        print(f"--- Running CheckNatura2000OverlapTool (Input: id='{basin_identifier}', kommune='{kommune}') ---")
        try:
            basin_path = get_data_path('BASIN_FINAL.gpkg')
            habitat_path = get_data_path('natura_2000_habitatomraader.gpkg')
            bird_path = get_data_path('natura_2000_fugleomraader.gpkg')
            if not all(os.path.exists(p) for p in [basin_path, habitat_path, bird_path]):
                 return {"kategori": "Fejl", "data": {"fejl": "En eller flere Natura2000 datafiler mangler."}}
            result = analyze_natura2000_main(basin_gdf_path=basin_path, habitat_path=habitat_path, bird_path=bird_path, basin_identifier=basin_identifier, kommune=kommune)
            print(f"--- CheckNatura2000OverlapTool Output Kategori: {result.get('kategori')} ---")
            return result
        except Exception as e:
            print(f"ERROR in CheckNatura2000OverlapTool: {e}")
            return {"kategori": "Fejl", "data": {"fejl": f"Uventet fejl under Natura2000 analyse: {type(e).__name__}"}}

# --- 4. Check Protected Nature ---
class CheckProtectedNatureInput(BaseModel):
    basin_identifier: str = Field(..., description="Det PRÆCISE basin identifier returneret af `Basin_Match` værktøjet.")
    kommune: str = Field(..., description="Det PRÆCISE kommune navn returneret af `Basin_Match` værktøjet.")
    buffer_distance: Optional[int] = Field(100, description="Valgfri afstand i meter til at vurdere sammenhæng med nærliggende beskyttet natur. Default er 100 meter hvis intet angives.")

class CheckProtectedNatureTool(BaseTool):
    name: str = "Check_Protected_Nature"
    description: str = (
        "Tjekker om et specifikt bassin (identificeret via `Basin_Match`) er registreret som §3 beskyttet natur, "
        "og om det (inden for en given buffer) er geografisk sammenhængende med nærliggende §3 natur. "
        "Returnerer JSON-resultat med ja/nej status for overlap/sammenhæng, fundne naturtyper og samlet areal."
    )
    args_schema: Type[BaseModel] = CheckProtectedNatureInput

    def _run(self, basin_identifier: str, kommune: str, buffer_distance: int = 100) -> Dict[str, Any]: # Default i run også
        print(f"--- Running CheckProtectedNatureTool (Input: id='{basin_identifier}', kommune='{kommune}', buffer={buffer_distance}) ---")
        try:
            basin_path = get_data_path('BASIN_FINAL.gpkg')
            nature_path = get_data_path('beskyttede_naturtyper.gpkg')
            if not all(os.path.exists(p) for p in [basin_path, nature_path]):
                 return {"kategori": "Fejl", "data": {"fejl": "En eller flere §3 natur datafiler mangler."}}
            result = analyze_protected_nature_main(basin_gdf_path=basin_path, nature_path=nature_path, basin_identifier=basin_identifier, kommune=kommune, buffer=buffer_distance)
            print(f"--- CheckProtectedNatureTool Output Kategori: {result.get('kategori')} ---")
            return result
        except Exception as e:
            print(f"ERROR in CheckProtectedNatureTool: {e}")
            return {"kategori": "Fejl", "data": {"fejl": f"Uventet fejl under §3 natur analyse: {type(e).__name__}"}}

# --- 5. Check Species Annex IV Proximity ---
class CheckSpeciesAnnexIVProximityInput(BaseModel):
    basin_identifier: str = Field(..., description="Det PRÆCISE basin identifier returneret af `Basin_Match` værktøjet.")
    kommune: str = Field(..., description="Det PRÆCISE kommune navn returneret af `Basin_Match` værktøjet.")
    search_distance: Optional[int] = Field(2000, description="Valgfri søgeafstand i meter for artsfund omkring bassinet. Default er 2000 meter hvis intet angives.")

class CheckSpeciesAnnexIVProximityTool(BaseTool):
    name: str = "Check_Species_AnnexIV_Proximity"
    description: str = (
        "Tjekker for registrerede fund af Bilag IV-arter inden for en given afstand af et specifikt bassin (identificeret via `Basin_Match`). "
        "Returnerer JSON-resultat med status ('ja'/'nej') og en liste over eventuelle artsfund nær bassinet (art, dato, afstand)."
    )
    args_schema: Type[BaseModel] = CheckSpeciesAnnexIVProximityInput

    def _run(self, basin_identifier: str, kommune: str, search_distance: int = 2000) -> Dict[str, Any]:
        print(f"--- Running CheckSpeciesAnnexIVProximityTool (Input: id='{basin_identifier}', kommune='{kommune}', distance={search_distance}) ---")
        try:
            basin_path = get_data_path('BASIN_FINAL.gpkg')
            species_path = get_data_path('bilag_iv_arter.gpkg')
            if not all(os.path.exists(p) for p in [basin_path, species_path]):
                 return {"kategori": "Fejl", "data": {"fejl": "En eller flere Bilag IV datafiler mangler."}}
            result = analyze_bilag_iv_arter_main(basin_gdf_path=basin_path, species_gdf_path=species_path, basin_identifier=basin_identifier, kommune=kommune, distance=search_distance)
            print(f"--- CheckSpeciesAnnexIVProximityTool Output Kategori: {result.get('kategori')} ---")
            return result
        except Exception as e:
            print(f"ERROR in CheckSpeciesAnnexIVProximityTool: {e}")
            return {"kategori": "Fejl", "data": {"fejl": f"Uventet fejl under Bilag IV analyse: {type(e).__name__}"}}

# --- 6. Check VP3 Streams Proximity ---
class CheckVP3StreamsProximityInput(BaseModel):
    basin_identifier: str = Field(..., description="Det PRÆCISE basin identifier returneret af `Basin_Match` værktøjet.")
    kommune: str = Field(..., description="Det PRÆCISE kommune navn returneret af `Basin_Match` værktøjet.")
    # Vi fjerner distance herfra, da den er fast 100m i beskrivelsen

class CheckVP3StreamsProximityTool(BaseTool):
    name: str = "Check_VP3_Streams_Proximity"
    description: str = (
        "Tjekker for VP3-klassificerede vandløb inden for en standardafstand (100m) af et specifikt bassin (identificeret via `Basin_Match`). "
        "Returnerer JSON-resultat med ja/nej status, detaljer om det *nærmeste* fundne vandløb (navn, tilstand, mål jf. vandområdeplaner), "
        "samt navnet på det kystvandopland bassinet ligger i."
    )
    args_schema: Type[BaseModel] = CheckVP3StreamsProximityInput

    def _run(self, basin_identifier: str, kommune: str) -> Dict[str, Any]:
        # Bruger altid default distance på 100m her
        distance = 100
        print(f"--- Running CheckVP3StreamsProximityTool (Input: id='{basin_identifier}', kommune='{kommune}', distance=100) ---")
        try:
            basin_path = get_data_path('BASIN_FINAL.gpkg')
            stream_path = get_data_path('vp3_vandloeb.gpkg')
            kystvand_path = get_data_path('Kystvandoplande.gpkg')
            if not all(os.path.exists(p) for p in [basin_path, stream_path, kystvand_path]):
                 return {"kategori": "Fejl", "data": {"fejl": "En eller flere VP3/Kystvand datafiler mangler."}}
            result = analyze_vp3_streams_main(basin_gdf_path=basin_path, stream_path=stream_path, kystvand_path=kystvand_path, basin_identifier=basin_identifier, kommune=kommune, distance=distance)
            print(f"--- CheckVP3StreamsProximityTool Output Kategori: {result.get('kategori')} ---")
            return result
        except Exception as e:
            print(f"ERROR in CheckVP3StreamsProximityTool: {e}")
            return {"kategori": "Fejl", "data": {"fejl": f"Uventet fejl under VP3 vandløbsanalyse: {type(e).__name__}"}}

# --- 7. Generate Basin Map ---
class GenerateBasinMapInput(BaseModel):
    basin_identifier: str = Field(..., description="Det PRÆCISE basin identifier returneret af `Basin_Match` værktøjet.")
    kommune: str = Field(..., description="Det PRÆCISE kommune navn returneret af `Basin_Match` værktøjet.")
    map_scale: int = Field(..., description="Påkrævet målestoksforhold for kortet (f.eks. 3000 for 1:3000). En værdi omkring 1500-5000 er typisk passende.")

class GenerateBasinMapTool(BaseTool):
    name: str = "Generate_Basin_Map"
    description: str = (
        "Genererer et kortbillede (PNG) af et specifikt bassin (identificeret via `Basin_Match`) med relevante omkringliggende datalag "
        "(f.eks. §3 natur, vandløb, Bilag IV arter) vist i en specificeret målestok. "
        "Returnerer den relative sti til den gemte kortfil i 'results/<kommune_navn>/' mappen."
    )
    args_schema: Type[BaseModel] = GenerateBasinMapInput
    # Bemærk: Denne funktion kan tage lidt tid at køre
    # return_direct = True # Overvej om agenten skal returnere resultatet direkte til brugeren

    def _run(self, basin_identifier: str, kommune: str, map_scale: int) -> str:
        print(f"--- Running GenerateBasinMapTool (Input: id='{basin_identifier}', kommune='{kommune}', scale={map_scale}) ---")
        try:
            # Definer stier til data
            b_path = get_data_path('BASIN_FINAL.gpkg')
            n_path = get_data_path('beskyttede_naturtyper.gpkg')
            # Tjek om vp3_vandloeb eller beskyttede_vandloeb skal bruges til kortet? Antager vp3 for konsistens.
            st_path = get_data_path('vp3_vandloeb.gpkg')
            sp_path = get_data_path('bilag_iv_arter.gpkg')

            # Definer output sti
            safe_kommune_folder = sanitize(kommune)
            output_dir = get_results_path(subfolder=safe_kommune_folder) # Bruger helper til at sikre mappen findes
            output_filename = f"MAP_{safe_kommune_folder}_{sanitize(basin_identifier)}_scale{map_scale}.png"
            output_file_path = os.path.join(output_dir, output_filename)

            # Tjek om input datafiler findes
            if not all(os.path.exists(p) for p in [b_path, n_path, st_path, sp_path]):
                return f"Fejl: En eller flere nødvendige datafiler til kortgenerering mangler."

            # Kald den importerede map generation logik
            # Antager at generate_map_logic_main har den korrekte signatur nu
            result_path = generate_map_logic_main(
                basin_identifier=basin_identifier,
                kommune=kommune,
                scale=map_scale,
                basin_path=b_path,
                nature_path=n_path,
                streams_path=st_path,
                species_path=sp_path,
                output_map_path=output_file_path
                # base_map_token kan evt. sættes her hvis nødvendigt
            )
            # Returner den relative sti (eller absolutte hvis generate_map returnerer det)
            # Gør stien relativ til projektets rod for konsistens med web app etc.
            project_root = os.path.dirname(os.path.abspath(__file__))
            relative_path = os.path.relpath(result_path, project_root)
            print(f"--- GenerateBasinMapTool Output Path: {relative_path} ---")
            # Returner stien som en brugervenlig streng
            return f"Kort genereret og gemt her: {relative_path.replace(os.sep, '/')}" # Brug forward slash for web-venlighed

        except Exception as e:
            print(f"ERROR in GenerateBasinMapTool: {e}")
            # Returner en fejlbesked som streng
            return f"Fejl under kortgenerering: {type(e).__name__}"


# --- 8. Generate Simple PDF Report (MED PATHLIB IMPORT OG EXISTS TJEK) ---
class GenerateSimpleReportInput(BaseModel):
    basin_identifier: str = Field(..., description="Det PRÆCISE basin identifier returneret af `Basin_Match` værktøjet.")
    kommune: str = Field(..., description="Det PRÆCISE kommune navn returneret af `Basin_Match` værktøjet.")
    map_scale: Optional[int] = Field(3000, description="Valgfrit målestoksforhold for kortet, der inkluderes i PDF'en. Default er 3000.")

class GenerateSimpleReportTool(BaseTool):
    name: str = "Generate_Simple_Report"
    description: str = (
        "Genererer en simpel PDF-rapport for et specifikt bassin (identificeret via `Basin_Match`). "
        # ... (resten af beskrivelsen) ...
        "Returnerer strengen 'Fil gemt her: [relativ_sti]' ved succes, ellers en fejlbesked."
    )
    args_schema: Type[BaseModel] = GenerateSimpleReportInput

    def _run(self, basin_identifier: str, kommune: str, map_scale: int = 3000) -> str:
        print(f"--- Running GenerateSimpleReportTool (Input: id='{basin_identifier}', kommune='{kommune}', scale={map_scale}) ---")
        try:
            relative_pdf_path = create_simple_report_main(
                basin_identifier=basin_identifier,
                kommune=kommune,
                map_scale=map_scale
            )

            if relative_pdf_path:
                try:
                    # Antager tools.py ligger i projektets rodmappe (basin_agent)
                    project_root = Path(__file__).parent
                    expected_abs_path = project_root / relative_pdf_path

                    # VENT på og VERIFICER at filen eksisterer
                    if expected_abs_path.exists() and expected_abs_path.is_file():
                        print(f"--- GenerateSimpleReportTool VERIFIED Path: {relative_pdf_path} ---")
                        return f"Fil gemt her: {relative_pdf_path}" # Returner succes-streng
                    else:
                        print(f"--- GenerateSimpleReportTool ERROR: Fil findes IKKE på forventet sti efter generering: {expected_abs_path} ---")
                        return f"Fejl: PDF blev rapporteret genereret, men kunne ikke findes på serveren ({relative_pdf_path})."

                except Exception as path_e:
                     print(f"--- GenerateSimpleReportTool ERROR: Kunne ikke verificere filsti: {path_e} ---")
                     return f"Fejl under verificering af filsti for {relative_pdf_path}: {path_e}"
            else:
                print("--- GenerateSimpleReportTool FAILED: create_simple_report_main returnerede None ---")
                return "Fejl: Kunne desværre ikke generere PDF rapporten (intern fejl)."

        except Exception as e:
            print(f"ERROR in GenerateSimpleReportTool _run: {e}")
            import traceback
            traceback.print_exc() # Print fuld traceback for bedre fejlfinding
            return f"Uventet fejl under PDF rapportgenerering: {type(e).__name__}"
        
# === Liste over alle tools til agenten ===
# Når alle tools er defineret, samler man dem typisk i en liste
available_tools = [
    BasinMatchTool(),
    GetBasinAttributesTool(),
    CheckNatura2000OverlapTool(),
    CheckProtectedNatureTool(),
    CheckSpeciesAnnexIVProximityTool(),
    CheckVP3StreamsProximityTool(),
    GenerateBasinMapTool(),
    GenerateSimpleReportTool(), # <-- TILFØJET HER
]

# === Simpel test af tools (hvis filen køres direkte) ===
if __name__ == '__main__':
    print("--- Manuel test af tools.py ---")

    # Eksempel på at køre et par tools i sekvens
    test_input_kommune = "Køge" # Prøv evt. med "Aabenrå" også
    test_input_id_part = "0513" # Del af ID

    print(f"\n>>> 1. Kører Basin_Match med kommune='{test_input_kommune}', id='{test_input_id_part}'...")
    match_tool = BasinMatchTool()
    match_res = match_tool.run({"kommune_query": test_input_kommune, "basin_id_query": test_input_id_part})
    print("--- Match Resultat ---")
    print(json.dumps(match_res, indent=2, ensure_ascii=False))

    if match_res.get("status") == "found_exact":
        exact_id = match_res.get("basin_identifier")
        exact_kom = match_res.get("kommune")

        print(f"\n>>> 2. Match fundet! Kører Get_Basin_Attributes for '{exact_id}' / '{exact_kom}'...")
        attr_tool = GetBasinAttributesTool()
        attr_res = attr_tool.run({"basin_identifier": exact_id, "kommune": exact_kom})
        print("--- Attribut Resultat ---")
        print(json.dumps(attr_res, indent=2, ensure_ascii=False))

        print(f"\n>>> 3. Kører Check_Natura2000_Overlap...")
        n2k_tool = CheckNatura2000OverlapTool()
        n2k_res = n2k_tool.run({"basin_identifier": exact_id, "kommune": exact_kom})
        print("--- Natura2000 Resultat ---")
        print(json.dumps(n2k_res, indent=2, ensure_ascii=False))

        print(f"\n>>> 4. Kører Check_Protected_Nature...")
        pn_tool = CheckProtectedNatureTool()
        pn_res = pn_tool.run({"basin_identifier": exact_id, "kommune": exact_kom}) # Bruger default buffer
        print("--- Protected Nature Resultat ---")
        print(json.dumps(pn_res, indent=2, ensure_ascii=False))

        print(f"\n>>> 5. Kører Check_Species_AnnexIV_Proximity...")
        sp_tool = CheckSpeciesAnnexIVProximityTool()
        sp_res = sp_tool.run({"basin_identifier": exact_id, "kommune": exact_kom}) # Bruger default distance
        print("--- Species Resultat ---")
        print(json.dumps(sp_res, indent=2, ensure_ascii=False))

        print(f"\n>>> 6. Kører Check_VP3_Streams_Proximity...")
        vp3_tool = CheckVP3StreamsProximityTool()
        vp3_res = vp3_tool.run({"basin_identifier": exact_id, "kommune": exact_kom}) # Bruger fast distance
        print("--- VP3 Streams Resultat ---")
        print(json.dumps(vp3_res, indent=2, ensure_ascii=False))

        print(f"\n>>> 7. Kører Generate_Basin_Map (scale 3000)...")
        map_tool = GenerateBasinMapTool()
        map_res = map_tool.run({"basin_identifier": exact_id, "kommune": exact_kom, "map_scale": 3000})
        print("--- Map Resultat ---")
        print(map_res) # map_res er bare en streng med stien

        print(f"\n>>> 8. Kører Generate_Simple_Report (scale 3000)...") # Ny test
        report_tool = GenerateSimpleReportTool()
        report_res = report_tool.run({"basin_identifier": exact_id, "kommune": exact_kom, "map_scale": 3000})
        print("--- Simple Report Resultat ---")
        print(report_res) # report_res er en streng med stien eller fejlbesked

    elif match_res.get("status") == "found_multiple":
         print("\n>>> Flere matches fundet af Basin_Match. Agenten ville skulle spørge brugeren.")
         print(f"Besked: {match_res.get('message_to_user')}")
    else:
         print("\n>>> Intet eksakt match fundet af Basin_Match eller fejl opstod.")

    print("\n--- Manuel test slut ---")