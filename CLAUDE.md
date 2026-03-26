# Airborne Geophysics – Welzow Ground Test

This project processes and analyses airborne geophysical survey data
collected by a GeoDuster system installed on an aircraft. The data
includes magnetic field measurements, GPS positioning, radar altimetry,
gamma-ray spectrometry, and VLF electromagnetic data. This repository
contains data from a **ground test** conducted at Welzow on 2026-03-24
(sessions 006 and 007). The aircraft was stationary; the tests verify
sensor connectivity and data quality before a real survey flight.

---

## Project structure

```
airborne-data/
├── data/
│   └── 2026-03-24 Welzow Ground-Test 006 - 007/
│       ├── EVT00006.txt / EVT00007.txt   ← system event logs
│       ├── MAG00006.txt / MAG00007.txt   ← main multi-sensor data
│       ├── GGA00006.txt / GGA00007.txt   ← differential GPS log
│       ├── SPC00006.txt / SPC00007.txt   ← spectrometer/env data
│       ├── Cfg00006.xml / Cfg00007.xml   ← system configuration snapshots
│       └── CMP_0043.*                    ← magnetic compensation model
├── src/
│   ├── analyse_session_006.py             ← original single-session script
│   └── analyse_sessions_006_007.py        ← full dual-session pipeline
└── outputs/
    ├── session_006/    ← plots + report_006.txt
    ├── session_007/    ← plots + report_007.txt
    └── comparison_006_007.txt
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

| Sensor | Port | Label | Full Name | Status 006 | Status 007 | MAG cols | Description |
|--------|------|-------|-----------|------------|------------|----------|-------------|
| GEMK1 | COM3 | P3 | Magnetometer #1 (Port side) | CONNECTED | CONNECTED | Mag1, Mag1D, Mag1C, A1, T1, X1, Y1, Z1 | GEM Systems KING-AIR towed fluxgate magnetometer – total field |
| GEMK2 | COM4 | P4 | Magnetometer #2 (Starboard side) | CONNECTED | CONNECTED | Mag2, Mag2D, Mag2C, A2, T2, X2, Y2, Z2 | GEM Systems KING-AIR towed fluxgate magnetometer – total field |
| GDRAlt | COM5 | P5 | Radar Altimeter | CONNECTED | CONNECTED | Ralt, Raltr | Measures height above ground (AGL) in metres |
| GD485 | COM6 | P6 | ADC 4-channel VLF receiver (RS-485 bus) | DISCONNECTED | DISCONNECTED | MagL, MagLC, Vlf1, Vlf2, Vlf3, Vlf4 | Analogue-to-digital converter for VLF EM channels |
| XSENS | COM7 | P7 | AHRS / GPS attitude sensor | CONNECTED | CONNECTED | Roll, Pitch, Yaw | XSENS MTi inertial measurement unit – Roll, Pitch, Yaw |
| GDGPS | COM8 | P8 | Septentrio differential GPS | CONNECTED | CONNECTED | Xgps, Ygps, Zgps, Lalt | High-precision GNSS receiver – position and altitude |
| GDSpec | COM9 | P9 | Medusa Gamma-Ray Spectrometer | DISCONNECTED | DISCONNECTED | Vlf1, Vlf2, Vlf3, Vlf4 | Gamma-ray spectrometer with environmental sensors |
| GDLas | COM10 | P10 | Laser Altimeter | DISCONNECTED | DISCONNECTED | — | Laser rangefinder for precise terrain clearance |

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

## Conventions for future scripts

- **Working directory**: `PROJECT_ROOT = Path(__file__).resolve().parents[1]`
- **Session IDs**: zero-padded 5-digit, e.g. `"00006"`, `"00007"`
- **Fixed-width parsing**: use `m.end()` of header tokens as column right boundaries
- **NaN encoding**: replace `#`-only cells before numeric conversion
- **Time axis**: convert `HHMMSS.sss` → elapsed seconds from first sample
- **Plots**: save to `outputs/session_NNN/` at 150 dpi, `matplotlib.use("Agg")`
- **NaN gaps in plots**: use `plt.plot()` directly – NaN naturally breaks the line
  (no interpolation, no vertical artefacts)
- **Excluded from analysis**: `Xst`, `Bin`, `Sbin` columns (hex/binary)
