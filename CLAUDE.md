# Airborne Survey Explorer

General-purpose pipeline for processing raw GeoDuster airborne geophysics data.
Works with any dataset (ground tests, calibration flights, survey missions).
The current dataset is a ground test at Welzow on 2026-03-24 (sessions 006 and 007).

---

## Pipeline stages

| Stage | Script | Status |
|-------|--------|--------|
| Step 1 – sensor status, data quality & session comparison | `src/step1_status.py` | done |
| Step 2 – flight line editing | `src/step2_lines.py` | planned |
| Step 3 – magnetic corrections | `src/step3_mag.py` | planned |
| Step 3 – radiometric corrections | `src/step3_rad.py` | future |
| Step 4 – variable maps | `src/step4_maps.py` | planned |

---

## Project structure

```
airborne-survey-explorer/
├── data/
│   └── <date> <location> <sessions>/   ← one subfolder per dataset
│       ├── EVT000NN.txt    ← system event logs
│       ├── MAG000NN.txt    ← main multi-sensor data
│       ├── GGA000NN.txt    ← differential GPS log
│       ├── SPC000NN.txt    ← spectrometer / environment
│       ├── Cfg000NN.xml    ← system configuration snapshot
│       └── CMP_*.*         ← magnetic compensation model
├── docs/
│   └── pipeline.md                 ← detailed pipeline reference
├── src/
│   ├── geoduster_utils.py          ← shared parsers, constants, analyse_session()
│   └── step1_status.py             ← Step 1: sensor health + data quality + comparison
└── outputs/
    ├── session_NNN/
    │   ├── report_NNN.txt
    │   └── plot_01_mag_raw.png  … (8 plots)
    └── comparison_NNN_MMM.txt
```

---

## Data formats

### EVT files (event log)
Plain-text timestamped event log produced by ICCS (GeoDuster acquisition
software). Each line: `HH:MM:SS.d: <message>`. Key patterns:

| Pattern | Meaning |
|---------|---------|
| `COMx: Macro SENSORNAME OK` | Sensor configured on port |
| `Character Rate on COMx is X.X chars/second` | Port activity (0=disconnected) |
| `Mx latches port COMx runs macro NAME` | Mux routing table |
| `Health Warning: Mx TimeO\|` | Multiplexer x timed out |
| `Health Warning: Nv WayP\|` | No navigation waypoint active |

### MAG / GGA / SPC files (fixed-width ASCII)
**Right-aligned fixed-width format.** Column boundaries align with the
RIGHT edge of each header token. Parse with `pd.read_fwf` using
colspecs derived from `m.end()` positions of regex matches on the
header line (NOT `m.start()`). Cells containing only `#` = NaN.

Key column rules:
- `Time` / `dTime` / `Stime` encode UTC as `HHMMSS.sss` float
- `Bin` / `Sbin` are raw hex – exclude from numeric analysis
- `Xst` is a long hex status word – exclude from numeric analysis

### Cfg XML files
GeoDuster system configuration snapshot. Key tags:
`COMPNAME` (compensation model), `NAVNAME` (navigation file),
`COMxSTATE` (On/Off per port), `MACRO` (sensor assigned per port).

---

## Sensors (full reference)

| Sensor | Port | Label | Full Name | MAG cols | Description |
|--------|------|-------|-----------|----------|-------------|
| GEMK1 | COM3 | P3 | Magnetometer #1 (Port side) | Mag1, Mag1D, Mag1C, A1, T1, X1, Y1, Z1 | GEM Systems KING-AIR towed fluxgate magnetometer – total field |
| GEMK2 | COM4 | P4 | Magnetometer #2 (Starboard side) | Mag2, Mag2D, Mag2C, A2, T2, X2, Y2, Z2 | GEM Systems KING-AIR towed fluxgate magnetometer – total field |
| GDRAlt | COM5 | P5 | Radar Altimeter | Ralt, Raltr | Measures height above ground (AGL) in metres |
| GD485 | COM6 | P6 | ADC 4-channel VLF receiver (RS-485 bus) | MagL, MagLC, Vlf1, Vlf2, Vlf3, Vlf4 | Analogue-to-digital converter for VLF EM channels |
| XSENS | COM7 | P7 | AHRS / GPS attitude sensor | Roll, Pitch, Yaw | XSENS MTi inertial measurement unit – Roll, Pitch, Yaw |
| GDGPS | COM8 | P8 | Septentrio differential GPS | Xgps, Ygps, Zgps, Lalt | High-precision GNSS receiver – position and altitude |
| GDSpec | COM9 | P9 | Medusa Gamma-Ray Spectrometer | Vlf1, Vlf2, Vlf3, Vlf4 | Gamma-ray spectrometer with environmental sensors |
| GDLas | COM10 | P10 | Laser Altimeter | — | Laser rangefinder for precise terrain clearance |

---

## Mux → file mapping (M1/M2/M3 system)

| Mux | Label | Writes to | Sensors it polls |
|-----|-------|-----------|-----------------|
| M1  | Mux1  | MAG file  | GEMK1, GEMK2, GDRAlt, GD485, XSENS, GDLas |
| M2  | Mux2  | GGA file  | GDSpec (provides GPS timestamp to GGA) |
| M3  | Mux3  | SPC file  | GDGPS (provides position to SPC) |

Note: M1/M2/M3 TimeO warnings are persistent during ground tests because
the synchronisation trigger relies on aircraft motion; this is normal.

---

## Coding conventions

- **Root path**: `PROJECT_ROOT = Path(__file__).resolve().parents[1]`
- **Session IDs**: zero-padded 5-digit for filenames (`"00006"`), 3-digit for output dirs (`"006"`)
- **Data folder**: passed as argument or auto-detected from first subfolder under `data/`
- **Sessions**: auto-detected by globbing `EVT*.txt` in the data folder
- **Fixed-width parsing**: use `m.end()` of header tokens as column right boundaries
- **NaN encoding**: replace `#`-only cells before numeric conversion
- **Time axis**: convert `HHMMSS.sss` → elapsed seconds from first sample
- **Plots**: save to `outputs/session_NNN/` at 150 dpi, `matplotlib.use("Agg")`
- **NaN gaps in plots**: use `plt.plot()` directly – NaN naturally breaks the line
- **Excluded from analysis**: `Xst`, `Bin`, `Sbin` columns (hex/binary)
- **Shared code**: put parsers and constants in `geoduster_utils.py`, not in step scripts
- **Terminal output**: only compact summary (sensor status + quality table + warning count); no file lists, no "Saved:" lines, no comparison file written to disk
- **No auto-generation**: CLAUDE.md and README.md are maintained manually
