"""
Module 2 — README.md written into every output folder.

Each folder of outputs/<campaign>/<run_name>/m02/ gets a short README.md that says what each
file or plot is and lists the notes worth knowing before reading it. The texts are general (no
campaign results): campaign-specific findings go in docs/findings_m02.md.

The README is rewritten every time the step runs, so editing it by hand is pointless: edit the
text below instead.
"""

from pathlib import Path

_MAP_NOTE = (
    "Maps are scatter plots of every sample (longitude / latitude), coloured in nT. Colour limits "
    "are the 2nd and 98th percentiles, so a few extreme points do not wash out the scale. Residual "
    "fields (after the IGRF removal) use a symmetric blue-red scale centred on zero."
)

_GPKG_NOTE = (
    "The .gpkg has one point layer per column (open it in QGIS): the column named in the layer, "
    "plus flight_id and line_id."
)

NOTES = {
    '01_02_lag': """# Steps 1-2 — GPS lag

The magnetometer reports each value slightly late, so anomalies end up shifted along the line.
Step 1 measures the shift on lines flown in both directions; step 2 applies it only if it is
larger than the tolerance (`lag_tolerable_s` in `project.yaml`).

| File | What it is |
|------|------------|
| `lag_summary.txt` | **Start here.** Plain-language result and decision. |
| `lag_report.json` | Same result as numbers (lag in s, decision, tolerance). |
| `lag_diagnosis_line<A>_line<B>.png` | One line flown in both directions, plotted along the track. If there is a lag the two curves are shifted against each other; after the correction they should overlap. |
| `lag_effect_map.png` | Map of how much each magnetic value would change if the lag were applied (after - before, nT). Near zero everywhere means the lag does not matter. |

Notes
- The diagnosis PNG file names depend on the pair of lines chosen. If the selection changes,
  old PNGs stay in the folder: delete them.
- No magnetic column changes in these steps; only `lag_applied` marks whether the shift was used.
""",

    '03_diurnal': """# Step 3 — Diurnal correction

The Earth's field varies during the day. A base station on the ground records that variation and
it is subtracted from the airborne data: `Mag_Diurnal = Mag - (base(t) - reference)`, with the
reference value from `project.yaml` (`diurnal_reference_nT`).

| File | What it is |
|------|------------|
| `diurnal_summary.txt` | **Start here.** What was done, what was not, what changed. |
| `diurnal_base_station.csv` | Base station readings used (UTC time, raw and filtered nT, source file). |
| `diurnal_base_station.png` | Base station during each flight: raw curve, filtered curve, and readings taken from the supplement table (red). |
| `diurnal_correction.png` | The correction added to the data during each flight (nT vs time). |
| `diurnal_maps.png` | Maps of Mag1, Mag2 and their mean, before and after the correction. |
| `diurnal_correction_map.png` | Map of the correction added at each point. |

Notes
- Red points in `diurnal_base_station.png` are NOT from our base station: they come from the
  supplement table (`base_station_supplement` in `project.yaml`), built from the reference
  specialist's data. A flight corrected only with them cannot be validated against his result.
- `base_station_use` in `project.yaml` chooses the raw or the filtered base curve.
""",

    '04_igrf': """# Step 4 — IGRF removal

Removes the Earth's main field (IGRF model, `igrf_model` in `project.yaml`) evaluated at each
sample's position, height and date: `Mag_IGRF = Mag_Diurnal - IGRF`.

| File | What it is |
|------|------------|
| `step_04_igrf_map.png` | Left: `Mag1_Diurnal` (total field). Right: `Mag1_IGRF` (residual). |
| `step_04_igrf.gpkg` | The same two columns as point layers. |

Notes
- **+55 nT constant of the reference processing.** The reference specialist's `Mag1_IGRF` is
  `Mag1_Diurnal - IGRF + 55.000 nT` (a fixed constant added after the removal to centre the
  anomaly around zero). We do NOT add it, so our `Mag_IGRF` columns are about 55 nT lower than
  his. When comparing, subtract that constant from his values (or add it to ours).
- The model must be the one in `project.yaml`: without a coefficient file `ppigrf` evaluates its
  newest model, which differs by tens of nT. The code selects it explicitly.
- A small constant difference to the specialist remains after that (see
  `docs/findings_m02.md`); it is not confirmed whether it is a height reference.

""" + _MAP_NOTE + "\n" + _GPKG_NOTE + "\n",

    '05_heading': """# Step 5 — Heading correction

The aircraft leaves a small magnetic signature that depends on its heading. It shows as an
offset between lines flown in opposite directions. Per sensor:
`bias = (mean_E - mean_W) / 2`, then E lines get `-bias` and W lines `+bias`.

| File | What it is |
|------|------------|
| `step_05_heading_map.png` | Left: `Mag1_IGRF`. Right: `Mag1_IGRF_head`. The difference is a few tenths of nT, so the two maps look almost identical. |
| `step_05_heading.gpkg` | The same two columns as point layers. |

Notes
- Each sensor has its own bias (they sit at different places on the aircraft). Only Mag1 is
  drawn in the map; Mag2 is in the parquet (`Mag2_IGRF_head`).
- The applied correction is saved per sample in `Mag1_heading_bias_nT` / `Mag2_heading_bias_nT`:
  plot that column to see the correction itself.
- N-S lines (tie lines) get no correction. Only the DC level is corrected, not the noise.
- This is an empirical method; the rigorous one (Tolles-Lawson) needs a calibration flight.

""" + _MAP_NOTE + "\n" + _GPKG_NOTE + "\n",

    '06_average': """# Step 6 — Average of the two magnetometers

Combines the two sensors into `Mag_IGRF_head`. If one sensor is clearly noisier than the other
in a flight, only the quieter one is used; otherwise the mean of the two.

| File | What it is |
|------|------------|
| `step_06_average_map.png` | Three panels: `Mag1_IGRF_head`, `Mag2_IGRF_head` and the combined `Mag_IGRF_head`. |
| `step_06_average.gpkg` | The same three columns as point layers. |

Notes
- `sensor_used` in the parquet says per flight which option was taken: `Mag1`, `Mag2` or `avg`.
- The residual field still carries the +55 nT difference to the reference specialist's values
  (see the step 4 README).

""" + _MAP_NOTE + "\n" + _GPKG_NOTE + "\n",

    '07_levelling': """# Step 7 — Tie-line levelling

Production lines and tie lines cross each other and should read the same value at each crossing.
The differences at the crossings are used to adjust each line by a constant:
`Mag_IGRF_head_level = Mag_IGRF_head - level_offset_nT`.

| File | What it is |
|------|------------|
| `step_07_levelling_map.png` | Left: `Mag_IGRF_head`. Right: `Mag_IGRF_head_level`. Stripes along the lines should be weaker on the right. |
| `step_07_levelling.gpkg` | The same two columns as point layers. |

Notes
- The offset of each line is saved in `level_offset_nT` (parquet).
- Quality depends on tie-line coverage: where tie lines are missing, the lines there are not
  levelled and stripes remain. Remaining stripes are handled by step 8.

""" + _MAP_NOTE + "\n" + _GPKG_NOTE + "\n",

    '08_microlevelling': """# Step 8 — Micro-levelling (decorrugation)

Removes the narrow stripes parallel to the lines that remain after the levelling: the along-line
smooth of each line is compared with its two neighbouring lines and the difference is subtracted.
The result is the final column `Mag_Final`.

| File | What it is |
|------|------------|
| `step_08_microlevelling_map.png` | Left: `Mag_IGRF_head_level`. Right: `Mag_Final`. |
| `step_08_microlevelling.gpkg` | The same two columns as point layers. |

Notes
- `Mag_Final` is the residual magnetic anomaly of module 2, without the +55 nT constant of the
  reference processing (see the step 4 README).
- The cutoff is 4 × the line spacing in `project.yaml` (`line_spacing_m`).
- Micro-levelling can remove real geology that is elongated across the lines: compare the two
  maps before trusting fine detail.

""" + _MAP_NOTE + "\n" + _GPKG_NOTE + "\n",

    'campaign': """# Module 2 — Campaign products

Consolidated outputs, written only when step 8 runs. Each step has its own subfolder with its own README.

| File | What it is |
|------|------------|
| `campaign_m02.gpkg` | All selected lines in one GeoPackage (open it in QGIS). |
| `campaign_m02_map.png` | Mag1C and Mag2C (compensated total field, after the lag step) for all selected lines: spatial coverage and signal level, to compare the two sensors. |

Notes
- The map shows the total field, not the final anomaly. The final column is `Mag_Final`
  (see `step_08_microlevelling/`).
- Subfolders: `step_01_02_lag/`, `step_03_diurnal/`, `step_04_igrf/`, `step_05_heading/`,
  `step_06_average/`, `step_07_levelling/`, `step_08_microlevelling/`.
""",
}


def write_readme(folder: Path, key: str) -> None:
    """
    Write README.md in `folder` with the notes of the step `key` (a key of NOTES).

    Does nothing if the key is unknown, so a new step without notes never breaks the run.
    """
    text = NOTES.get(key)
    if text is None:
        return
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'README.md').write_text(text, encoding='utf-8')
    print(f"  README: {folder.name}/README.md")
