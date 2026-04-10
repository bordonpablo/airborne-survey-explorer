# Airborne Survey Explorer

A Python pipeline for processing and analysing raw data from **GeoDuster airborne geophysics systems**. Designed to work with any dataset produced by the system — ground tests, calibration flights, or full survey missions.

The pipeline starts with an initial status check (sensor health, data quality) and is designed to grow toward a full analysis suite: flight line editing, variable mapping, geophysical corrections, and export.

---

## Pipeline overview

| Step | Script | Purpose |
|------|--------|---------|
| **Step 1** | `src/step1_status.py` | Sensor health check and data-quality check for one or more sessions; prints side-by-side comparison when 2+ sessions are given |
| *(planned)* | `src/step2_lines.py` | Flight line definition, editing, and session merging |
| *(planned)* | `src/step3_mag.py` | Magnetic corrections (diurnal, IGRF, lag, compensation) |
| *(future)* | `src/step3_rad.py` | Radiometric corrections (Medusa spectrometer) |
| *(planned)* | `src/step4_maps.py` | Gridding, colour maps, and export |

See [`docs/pipeline.md`](docs/pipeline.md) for detailed explanations of each step.

---

## Usage

```bash
# Auto-detects data folder and all sessions
python src/step1_status.py

# Specify folder (sessions auto-detected)
python src/step1_status.py "data/MyFolder"

# Specify folder and sessions explicitly; prints comparison table when 2+ given
python src/step1_status.py "data/MyFolder" 6 7
```

---

## Project structure

```
airborne-survey-explorer/
├── data/
│   └── <date> <location> <session range>/   ← one subfolder per dataset
│       ├── EVT000NN.txt    ← system event logs (ICCS)
│       ├── MAG000NN.txt    ← main multi-sensor data (~10 Hz)
│       ├── GGA000NN.txt    ← differential GPS log (~10 Hz)
│       ├── SPC000NN.txt    ← spectrometer / environment (~1 Hz)
│       ├── Cfg000NN.xml    ← system configuration snapshot
│       └── CMP_*.{bin,cff} ← magnetic compensation model
├── docs/
│   └── pipeline.md                 ← detailed step-by-step pipeline reference
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

## Step 1 outputs

For each session, `step1_status.py` produces:

- **EVT analysis**: sensor-port mapping, connection status (char rates), mux assignments, health warnings, critical errors, session timing, Cfg XML summary
- **MAG / GGA / SPC**: row counts, NaN classification (fully/partial/clean per column), GPS quality indicators
- **Plots** (saved as PNG at 150 dpi):
  1. Magnetometers raw (Mag1, Mag2)
  2. Attitude – Roll, Pitch, Yaw (XSENS)
  3. Radar altimeter (Ralt)
  4. GPS quality indicators (HDOP, satellite count)
  5. Spectrometer channels (Sk, Su, Sth) if available
- **Stability table**: mean, std, min, max, and threshold check for all key variables
- **Cross-check**: EVT connection status vs actual NaN presence in MAG

The terminal prints only a compact summary per session (sensor status + key variable quality table + warning count). Detailed output goes to the report file only.

---

## Data formats

### EVT files (event log)
Plain-text timestamped log from the ICCS acquisition software.
Each line: `HH:MM:SS.d: <message>`. Key patterns:

| Pattern | Meaning |
|---------|---------|
| `COMx: Macro SENSORNAME OK` | Sensor configured on port |
| `Character Rate on COMx is X.X chars/second` | Port activity (0 = disconnected) |
| `Mx latches port COMx runs macro NAME` | Mux routing table |
| `Health Warning: Mx TimeO\|` | Multiplexer x timed out |
| `Health Warning: Nv WayP\|` | No navigation waypoint active |

### MAG / GGA / SPC files (fixed-width ASCII)
Right-aligned fixed-width format. Column boundaries align with the **right edge** of each header token (`m.end()` of regex match, not `m.start()`). Cells containing only `#` = NaN.

- `Time` / `dTime` / `Stime`: UTC encoded as `HHMMSS.sss` float
- `Bin` / `Sbin` / `Xst`: raw hex/binary – excluded from numeric analysis

### Cfg XML files
System configuration snapshot. Key tags: `COMPNAME`, `NAVNAME`, `COMxSTATE`, `MACRO`.

---

## Sensor reference (GeoDuster system)

| Sensor | Port | Full Name | MAG columns | Description |
|--------|------|-----------|-------------|-------------|
| GEMK1 | COM3 | Magnetometer #1 (Port side) | Mag1, Mag1D, Mag1C, A1, T1, X1, Y1, Z1 | GEM Systems fluxgate – total field |
| GEMK2 | COM4 | Magnetometer #2 (Starboard side) | Mag2, Mag2D, Mag2C, A2, T2, X2, Y2, Z2 | GEM Systems fluxgate – total field |
| GDRAlt | COM5 | Radar Altimeter | Ralt, Raltr | Height above ground (AGL) in metres |
| GD485 | COM6 | ADC 4-channel VLF receiver | MagL, MagLC, Vlf1–Vlf4 | Analogue-to-digital converter for VLF EM |
| XSENS | COM7 | AHRS / GPS attitude sensor | Roll, Pitch, Yaw | XSENS MTi inertial measurement unit |
| GDGPS | COM8 | Septentrio differential GPS | Xgps, Ygps, Zgps, Lalt | High-precision GNSS receiver |
| GDSpec | COM9 | Medusa Gamma-Ray Spectrometer | Vlf1–Vlf4, Sk, Su, Sth | Gamma-ray spectrometer + environmental |
| GDLas | COM10 | Laser Altimeter | — | Laser rangefinder for terrain clearance |

### Mux → file mapping

| Mux | Writes to | Sensors polled |
|-----|-----------|----------------|
| M1 | MAG file | GEMK1, GEMK2, GDRAlt, GD485, XSENS, GDLas |
| M2 | GGA file | GDSpec (GPS timestamp) |
| M3 | SPC file | GDGPS (position) |

M1/M2/M3 TimeO warnings are persistent during ground tests (no aircraft motion trigger) — this is normal and does not indicate data loss.

---

## Current dataset

`data/2026-03-24 Welzow Ground-Test 006 - 007/`

Ground test at Welzow, Germany on 2026-03-24. Aircraft parked; sessions 006 and 007 verify sensor connectivity before a real survey flight.
