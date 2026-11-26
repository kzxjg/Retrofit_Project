from pathlib import Path
import pandas as pd
import sys 
from eppy.modeleditor import IDF
from itertools import product
from idftool import energyplus_dir


def idf_name(*parts):
    text = " ".join(str(p).strip() for p in parts)
    for ch in ",;!":
        text = text.replace(ch, " ")
    return " ".join(text.split())


def edit_idf(excel_path, idf_file):

    sheets = pd.read_excel(excel_path, sheet_name=None)

    ext_wall = sheets["External wall insulation"]
    roof = sheets["Roof"]
    floor = sheets["Floor"]
    window = sheets["Window"]

    #add combinations of the sheets to the idf files and save all new idf files in a new folder
    IDF.setiddname(str(energyplus_dir() / "Energy+.idd"))
    idf_file = Path(idf_file)
    # Always write into Retrofit_Project/IDF new, wherever the input IDF lives
    outdir = Path(__file__).resolve().parent / "IDF new"
    outdir.mkdir(parents=True, exist_ok=True)

    # (sheet, surface type, which outside boundaries count, put insulation on the outside?)

    insulation_parts = [
        (ext_wall, "wall", ("outdoors",), True),
        (roof, "roof", ("outdoors",), False),
        (floor, "floor", ("ground", "groundfcfactormethod", "foundation", "outdoors"), False),
    ]
    wall_rows = [r for _, r in ext_wall.dropna(subset=[ext_wall.columns[0]]).iterrows()]
    roof_rows = [r for _, r in roof.dropna(subset=[roof.columns[0]]).iterrows()]
    floor_rows = [r for _, r in floor.dropna(subset=[floor.columns[0]]).iterrows()]
    window_rows = [r for _, r in window.dropna(subset=[window.columns[0]]).iterrows()]
    combos = list(product(wall_rows, roof_rows, floor_rows, window_rows))
    print(f"{len(combos)} combinations")

    for n, (w, r, f, g) in enumerate(combos, start=1):
        idf = IDF(str(idf_file)) 

        for row, (_, surface_type, boundaries, outside) in zip((w, r, f), insulation_parts):
            if str(row.iloc[1]).strip().lower().startswith("no retrofit"):
                continue
            fields = dict(Name=idf_name(row.iloc[0], row.iloc[1]), Roughness=row.iloc[5],
                          Thickness=float(row.iloc[2]) / 1000, Conductivity=float(row.iloc[3]),
                          Density=float(row.iloc[6]), Specific_Heat=float(row.iloc[7]))
            for field, i in (("Thermal_Absorptance", 8), ("Solar_Absorptance", 9), ("Visible_Absorptance", 10)):
                if pd.notna(row.iloc[i]):
                    fields[field] = float(row.iloc[i])
            mat = idf.newidfobject("MATERIAL", **fields)

            constructions = {s.Construction_Name for s in idf.idfobjects["BUILDINGSURFACE:DETAILED"]
                             if s.Surface_Type.lower() == surface_type
                             and s.Outside_Boundary_Condition.lower() in boundaries}

            # Add the new material as an extra layer in each of those existing constructions
            for name in constructions:
                con = idf.getobject("CONSTRUCTION", name)
                layers = [v for v in con.fieldvalues[2:] if v != ""]
                layers = [mat.Name] + layers if outside else layers + [mat.Name]
                con.Outside_Layer = layers[0]
                for i, layer in enumerate(layers[1:], start=2):
                    con[f"Layer_{i}"] = layer


        if not str(g.iloc[1]).strip().lower().startswith("no retrofit"):
            glazing = idf.newidfobject("WINDOWMATERIAL:SIMPLEGLAZINGSYSTEM", Name=idf_name(g.iloc[0], g.iloc[1]),
                                       UFactor=float(g.iloc[2]), Solar_Heat_Gain_Coefficient=float(g.iloc[3]))
            if pd.notna(g.iloc[4]):
                glazing.Visible_Transmittance = float(g.iloc[4])
            con = idf.newidfobject("CONSTRUCTION", Name=idf_name("Window", g.iloc[0]), Outside_Layer=glazing.Name)
            for win in idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]:
                if win.Surface_Type.lower() == "window":
                    win.Construction_Name = con.Name

        name = f"{idf_file.stem}_{w.iloc[0]}_{r.iloc[0]}_{f.iloc[0]}_{g.iloc[0]}.idf"
        outdir.mkdir(parents=True, exist_ok=True)  # in case the folder was removed mid-run
        idf.saveas(str(outdir / name))
        print(f"{n}/{len(combos)} {name}")


def apply_idf_combinations(excel_path, idf_file):
    """
    Apply the combinations of retrofit options from the Excel file to the IDF file.
    This function is a wrapper for edit_idf to be used in other scripts or modules.
    """
    edit_idf(excel_path, idf_file)


if __name__ == "__main__":
    excel_path = sys.argv[1]
    idf_files = Path(sys.argv[2])
    #Loop through the folders in excel and idf_file 
    for idf in idf_files.glob("*.idf"): 
        apply_idf_combinations(excel_path, idf)
    # apply_idf_combinations(excel_path, idf_files)
    