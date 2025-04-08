import os
import json
from typing import Dict, Any, Optional, List, Tuple

# --- Necessary Imports ---
# Absolutte imports fra pakken er nødvendige
from agent_tools.get_basin_attributes import get_basin_attributes_main
from agent_tools.check_natura2000 import analyze_natura2000_main
from agent_tools.check_protected_nature import analyze_protected_nature_main
from agent_tools.check_species_bilag_iv import analyze_bilag_iv_arter_main
from agent_tools.check_vp3_streams import analyze_vp3_streams_main
from agent_tools.generate_map import generate_map as generate_map_logic_main, sanitize

# External libs
from langchain_openai import ChatOpenAI
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors
from PIL import Image as PILImage
from dotenv import load_dotenv

# --- Config & LLM Setup ---
load_dotenv(dotenv_path='.env') # Load from CWD (expected to be project root)
llm = ChatOpenAI(model="gpt-4o", temperature=0.2, openai_api_key=os.getenv("OPENAI_API_KEY"))

# --- Helper: Flatten Dictionary for Table ---
def flatten_for_table(d: Dict[str, Any], parent: str = '') -> List[Tuple[str, str]]:
    items = []
    for k, v in d.items():
        new_k = f"{parent} - {k}" if parent else k
        if isinstance(v, dict) and v: items.extend(flatten_for_table(v, new_k))
        elif isinstance(v, list) and v: items.append((new_k, (', '.join(map(str, v)))[:200] + ('...' if len(str(v)) > 200 else '')))
        else: items.append((new_k, str(v if v is not None else 'Ingen data')[:200] + ('...' if len(str(v)) > 200 else '')))
    return items

# --- PDF Generation Function ---
def _make_pdf(title: str, summary: str, map_img_path: Optional[str], raw_data: Dict[str, Any], out_path: str):
    doc = SimpleDocTemplate(out_path, pagesize=A4, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()
    styles['h1'].alignment = 1 # Center title
    story = [Paragraph(title, styles['h1']), Spacer(1, 0.2*inch), Paragraph(summary, styles['Normal']), Spacer(1, 0.2*inch)]

    # Map
    if map_img_path and os.path.exists(map_img_path):
        try:
            img = PILImage.open(map_img_path); w, h = img.size; max_w = A4[0] - 2*inch; aspect = h/float(w) if w else 0
            new_w = max_w; new_h = min(aspect * new_w if aspect else 0, A4[1] * 0.5) # Limit height
            if aspect and new_h == A4[1] * 0.5: new_w = new_h / aspect # Adjust width if height limited
            story.append(Image(map_img_path, width=new_w, height=new_h))
        except Exception as e: story.append(Paragraph(f"[Kort Fejl: {e}]", styles['Code']))
    else: story.append(Paragraph("[Kort ikke tilgængeligt]", styles['Normal']))

    # Data Table
    story.append(PageBreak()); story.append(Paragraph("Rå Analysedata", styles['h2']))
    table_data = [("Analyse / Attribut", "Resultat / Værdi")] + flatten_for_table(raw_data)
    if len(table_data) > 1:
        table = Table(table_data, colWidths=[2.5*inch, 4*inch], repeatRows=1)
        table.setStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey), ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'), ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9), ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0,0), (-1,-1), 5), ('RIGHTPADDING', (0,0),(-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0),(-1,-1), 3)
        ])
        story.append(table)
    else: story.append(Paragraph("Ingen rå data fundet.", styles['Normal']))

    try: doc.build(story); return out_path
    except Exception as e: print(f"PDF Build Fejl: {e}"); return None

# --- Main Report Function ---
def create_simple_report_main(basin_identifier: str, kommune: str, map_scale: int = 3000) -> Optional[str]:
    print(f"--- Genererer rapport: {basin_identifier} ({kommune}) ---")
    if not llm or not os.getenv("OPENAI_API_KEY"):
        print("FEJL: LLM eller API nøgle mangler."); return None

    all_raw_data = {}
    errors = []
    map_path_abs = None # Skal bruge absolut sti til PDF
    data_dir = 'data' # Relativt til CWD
    results_dir = os.path.join('results', sanitize(kommune))
    os.makedirs(results_dir, exist_ok=True)

    # Paths til datafiler
    b_path = os.path.join(data_dir, 'BASIN_FINAL.gpkg')
    h_path = os.path.join(data_dir, 'natura_2000_habitatomraader.gpkg')
    f_path = os.path.join(data_dir, 'natura_2000_fugleomraader.gpkg')
    n_path = os.path.join(data_dir, 'beskyttede_naturtyper.gpkg')
    s_path = os.path.join(data_dir, 'bilag_iv_arter.gpkg')
    st_path = os.path.join(data_dir, 'vp3_vandloeb.gpkg')
    k_path = os.path.join(data_dir, 'Kystvandoplande.gpkg')

    # 1. Kør Analyser
    analysis_funcs = {
        "Attributes": lambda: get_basin_attributes_main(b_path, basin_identifier, kommune),
        "Natura2000": lambda: analyze_natura2000_main(b_path, h_path, f_path, basin_identifier, kommune),
        "ProtectedNature": lambda: analyze_protected_nature_main(b_path, n_path, basin_identifier, kommune),
        "SpeciesAnnexIV": lambda: analyze_bilag_iv_arter_main(b_path, s_path, basin_identifier, kommune),
        "VP3Streams": lambda: analyze_vp3_streams_main(b_path, st_path, k_path, basin_identifier, kommune),
    }
    for name, func in analysis_funcs.items():
        try:
             result = func()
             all_raw_data[name] = result.get("data", {"error": "Ingen data returneret"}) if result else {"error": "Funktionskald fejlede"}
             if "error" in all_raw_data[name] or "fejl" in all_raw_data[name]: errors.append(name)
        except Exception as e: errors.append(f"{name} Kritisk: {type(e).__name__}"); all_raw_data[name] = {"error": f"Kritisk fejl: {type(e).__name__}"}

    # 2. Generer Kort
    try:
        map_filename = f"MAP_{sanitize(kommune)}_{sanitize(basin_identifier)}_scale{map_scale}.png"
        map_out_abs = os.path.abspath(os.path.join(results_dir, map_filename)) # Absolut sti til output
        generated_path = generate_map_logic_main(basin_identifier, kommune, map_scale, b_path, n_path, st_path, s_path, map_out_abs)
        if generated_path and os.path.exists(generated_path): map_path_abs = generated_path # Gem absolut sti
        else: errors.append("Kort generering")
    except Exception as e: errors.append(f"Kort Kritisk: {type(e).__name__}")

    # 3. LLM Summary
    summary = f"Opsummering for {basin_identifier} ({kommune})."
    if all_raw_data:
        try:
            # Gør JSON lidt mere læsbar for prompten, hvis den er stor
            json_data_str = json.dumps(all_raw_data, indent=1, default=str, ensure_ascii=False)
            # Begræns evt. længden af data sendt til LLM for at spare tokens/tid
            max_len = 3000
            if len(json_data_str) > max_len:
                json_data_str = json_data_str[:max_len] + "\n... (data forkortet)"

            # --- NY PROMPT ---
            prompt = (
                f"Baseret på følgende JSON-data for regnvandsbassin '{basin_identifier}' i {kommune} kommune, "
                f"skriv en god opsummering i **plain text**. Den skal dække de relevante oplysninger uden at være for langt."
                f"Fokuser på oplysningerne. Nævn evt. specifikke navne/typer hvis relevant. Hvis data mangler kan det også være vigtigt at nævne."
                f"BRUG IKKE Markdown (ingen ###, **, osv.). Skriv som en almindelig, flydende tekstblok.\n\n"
                f"Data:\n```json\n{json_data_str}\n```\n\nOpsummering (plain text):"
            )
            # --- SLUT NY PROMPT ---

            summary = llm.invoke(prompt).content
        except Exception as e:
            errors.append(f"LLM Kritisk: {type(e).__name__}")
            summary += f" (LLM Fejl: {type(e).__name__})"

    # 4. Generer PDF
    pdf_filename = f"Rapport_{sanitize(kommune)}_{sanitize(basin_identifier)}.pdf"
    pdf_out_abs = os.path.abspath(os.path.join(results_dir, pdf_filename))
    final_pdf_path_abs = _make_pdf(f"Rapport: {basin_identifier} ({kommune})", summary, map_path_abs, all_raw_data, pdf_out_abs)

    if errors: print(f"  Bemærk: Fejl opstod i flg. dele: {', '.join(errors)}")
    print(f"--- Rapportgenerering færdig for {basin_identifier} ---")

    # Returner RELATIV sti hvis succes
    if final_pdf_path_abs and os.path.exists(final_pdf_path_abs):
        try: return os.path.relpath(final_pdf_path_abs, start=os.getcwd()).replace(os.sep, '/')
        except ValueError: return final_pdf_path_abs # Fallback hvis relpath fejler
    return None

# === TEST BLOCK (Minimal) ===
# Kør fra projekt rod: python -m agent_tools.generate_pdf
if __name__ == "__main__":
    print("--- Test: create_simple_report_main ---")
    pdf_path = create_simple_report_main(basin_identifier="10-0 33/0380 Venstre", kommune="Solrød")
    if pdf_path: print(f"Success! PDF relativ sti: {pdf_path}")
    else: print("Fejl under PDF generering.")
    print("--- Test Slut ---")

# --- END OF agent_tools/generate_pdf.py (Compact Version) ---