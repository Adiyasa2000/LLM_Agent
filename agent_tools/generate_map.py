import geopandas as gpd
import matplotlib.pyplot as plt
from owslib.wmts import WebMapTileService # Keeping necessary imports only
from PIL import Image
import io
import os
import time
# No extra imports

# Original sanitize function
def sanitize(text):
    return ( text.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
             .replace("/", "-").replace("\\", "-").replace(" ", "_").replace(":", "_") )

# Original helper function (kept outside for readability)
def plot_layer_if_not_empty(ax, gdf, x_min, x_max, y_min, y_max, **kwargs):
    subset = gdf.cx[x_min:x_max, y_min:y_max]
    if not subset.empty:
        subset.plot(ax=ax, **kwargs)

# Original matching function (kept outside for readability)
def find_best_basin_match(df, ident):
    ident = ident.lower().strip()
    for col in ["New_FID", "Frakmt", "Stedfaestelse"]:
        match = df[df[col].astype(str).str.lower().str.contains(ident, na=False)]
        if not match.empty:
            return match
    print(f"[Match] No match for identifier '{ident}' in any column.")
    return gpd.GeoDataFrame()

# Modified signature; added base_map_token for completeness
def generate_map(basin_identifier: str, kommune: str, scale: int,
                 basin_path: str, nature_path: str, streams_path: str, species_path: str, # Input paths
                 output_map_path: str, # Output path
                 base_map_token: str = "5efbec2dca262336fd10c34abd033f3b"
                 ) -> str:

    # --- Load Data using arguments ---
    # Minimal error handling here - assumes files exist and are valid GPKGs
    basin_gdf = gpd.read_file(basin_path)
    nature_gdf = gpd.read_file(nature_path)
    streams_gdf = gpd.read_file(streams_path)
    species_gdf = gpd.read_file(species_path)
    # --- End Load Data ---

    # --- EXACTLY Original Logic Below ---
    basin_gdf = basin_gdf[basin_gdf["Kommune"].str.lower() == kommune.lower()]
    if basin_gdf.empty: raise ValueError(f"No basin found in municipality '{kommune}'")

    selected = find_best_basin_match(basin_gdf, basin_identifier)
    if selected.empty: raise ValueError(f"No basin found with identifier '{basin_identifier}' in '{kommune}'")

    basin_geom = selected.geometry.union_all()
    centroid = basin_geom.centroid
    dpi = 300
    map_width_meters = scale * 10 / 39.37 # Original calculation
    x_min = centroid.x - map_width_meters / 2
    x_max = centroid.x + map_width_meters / 2
    y_min = centroid.y - map_width_meters / 2
    y_max = centroid.y + map_width_meters / 2

    fig, ax = plt.subplots(figsize=(10, 10))
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.set_xticks([]); ax.set_yticks([]); ax.axis('off') # Minor condensation

    wmts_url = f"https://api.dataforsyningen.dk/orto_foraar_wmts_DAF?token={base_map_token}"
    try: # Basic try block around WMTS
        wmts = WebMapTileService(wmts_url)
        tile_matrix_set = "KortforsyningTilingDK"
        zoom_level = 11 # Original zoom
        tile_size = 256
        top_left_x = 120000.0; top_left_y = 6500000.0 # Original coords
        scale_denominator = 2857.142857142857 # Original scale denom
        meters_per_pixel = scale_denominator * 0.00028 # Original mpp

        col_min = max(0, int((x_min - top_left_x) / (tile_size * meters_per_pixel)))
        col_max = min(4296, int((x_max - top_left_x) / (tile_size * meters_per_pixel)))
        row_min = max(0, int((top_left_y - y_max) / (tile_size * meters_per_pixel)))
        row_max = min(2929, int((top_left_y - y_min) / (tile_size * meters_per_pixel)))

        total_width = (col_max - col_min + 1) * tile_size
        total_height = (row_max - row_min + 1) * tile_size

        if total_width > 0 and total_height > 0:
            background = Image.new('RGB', (total_width, total_height))
            for col in range(col_min, col_max + 1):
                for row in range(row_min, row_max + 1):
                    # Minimal error handling per tile
                    try:
                        tile = wmts.gettile(layer="orto_foraar_wmts", tilematrixset=tile_matrix_set,
                                            tilematrix=str(zoom_level), row=row, column=col, format="image/jpeg")
                        img = Image.open(io.BytesIO(tile.read()))
                        x_offset = (col - col_min) * tile_size; y_offset = (row - row_min) * tile_size
                        background.paste(img, (x_offset, y_offset))
                    except Exception as e: print(f"Warning: Tile error @ {col},{row}: {e}") # Simple warning

            tile_x_min = top_left_x + col_min * tile_size * meters_per_pixel
            tile_x_max = tile_x_min + total_width * meters_per_pixel
            tile_y_max = top_left_y - row_min * tile_size * meters_per_pixel
            tile_y_min = tile_y_max - total_height * meters_per_pixel
            ax.imshow(background, extent=[tile_x_min, tile_x_max, tile_y_min, tile_y_max], interpolation='nearest')
        else: print("Warning: Calculated tile dimensions invalid, skipping background.")
    except Exception as e: print(f"Warning: Failed WMTS background: {e}")

    # Plot vector layers using helper
    plot_layer_if_not_empty(ax, nature_gdf, x_min, x_max, y_min, y_max, color="green", alpha=0.5, edgecolor="darkgreen")
    plot_layer_if_not_empty(ax, streams_gdf, x_min, x_max, y_min, y_max, color="blue", linewidth=2)
    plot_layer_if_not_empty(ax, species_gdf, x_min, x_max, y_min, y_max, color="red", marker="o", markersize=50, edgecolor="black", linewidth=1, linestyle="None")
    selected.plot(ax=ax, facecolor="none", edgecolor="red", linewidth=2)

    # Original Legend
    from matplotlib.patches import Patch; from matplotlib.lines import Line2D # Inline import
    legend_elements = [ Patch(facecolor="none", edgecolor="red", label="Bassin"),
                        Patch(facecolor="green", edgecolor="darkgreen", alpha=0.5, label="Beskyttet natur"),
                        Line2D([0], [0], color="blue", linewidth=2, label="Vandløb"),
                        Line2D([0], [0], marker="o", color="red", markeredgecolor="black", markersize=10, linestyle="None", label="Bilag‑IV arter") ]
    ax.legend(handles=legend_elements, loc="upper right")
    ax.set_title(f"Kort over bassin: {basin_identifier} (Kommune: {kommune}) - Skala 1:{scale}", fontsize=14)

    # --- Save Figure using argument ---
    output_dir = os.path.dirname(output_map_path)
    if output_dir and not os.path.exists(output_dir): os.makedirs(output_dir, exist_ok=True) # Create dir if needed
    plt.savefig(output_map_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    # --- End Save Figure ---

    return output_map_path

# ✅ TEST BLOCK
if __name__ == "__main__":
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    # Brug de faktiske værdier direkte til at lave mappenavnet
    kommune_map_dir = os.path.join(project_root, 'results', sanitize("Køge"))
    os.makedirs(kommune_map_dir, exist_ok=True) # Opret mappen hvis den mangler
    # Konstruer output filnavn ved at indsætte værdierne direkte
    output_file_path = os.path.join(kommune_map_dir, f"MAP_{sanitize('Køge')}_{sanitize('20-0 40/0513 Venstre')}_scale{3000}.png")

    print(f"Outputting map to: {output_file_path}")
    start = time.time()
    try:
        generate_map(
            basin_identifier="20-0 40/0513 Venstre",
            kommune="Køge",
            scale=1000,
            basin_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'BASIN_FINAL.gpkg'),
            nature_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'beskyttede_naturtyper.gpkg'),
            # Antager 'vp3_vandloeb.gpkg' er korrekt her
            streams_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'vp3_vandloeb.gpkg'),
            species_path=os.path.join(os.path.dirname(__file__), '..', 'data', 'bilag_iv_arter.gpkg'),
            output_map_path=output_file_path
        )
        print(f"Map generation attempted. Check file.")
    except Exception as e: print(f"ERROR generating map: {type(e).__name__}: {e}")
    print(f"Time: {time.time() - start:.2f}s")