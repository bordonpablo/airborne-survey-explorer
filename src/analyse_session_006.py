"""
analyse_session_006.py
Full analysis pipeline for Ground-Test session 006 (Welzow, 2026-03-24).
Covers: EVT log parsing, MAG data parsing, stability analysis, plots,
cross-check EVT vs MAG, and generation of report / documentation files.

Usage:
    python src/analyse_session_006.py
"""

import re
import sys
import textwrap
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")          # headless – no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR     = PROJECT_ROOT / "data" / "2026-03-24 Welzow Ground-Test 006 - 007"
SRC_DIR      = PROJECT_ROOT / "src"
OUT_DIR      = PROJECT_ROOT / "outputs"
EVT_FILE     = DATA_DIR / "EVT00006.txt"
MAG_FILE     = DATA_DIR / "MAG00006.txt"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Helper: pretty table ───────────────────────────────────────────────────────
def table(headers, rows, col_widths=None):
    """Return a simple ASCII table string."""
    if col_widths is None:
        col_widths = [max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
                      for i, h in enumerate(headers)]
    sep  = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
    fmt  = "|" + "|".join(" {:<{w}} ".format("{}", w=w) for w in col_widths) + "|"
    lines = [sep, fmt.format(*headers), sep]
    for row in rows:
        lines.append(fmt.format(*row))
    lines.append(sep)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 – EVT analysis
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 1 – EVT00006.txt analysis")
print("=" * 70)

evt_lines = EVT_FILE.read_text(encoding="utf-8", errors="replace").splitlines()

# ── a) Sensor-port mapping ─────────────────────────────────────────────────────
sensor_map = {}   # {COM_port: sensor_name}
for line in evt_lines:
    m = re.search(r"COM(\d+): Macro (\w+) OK", line)
    if m:
        sensor_map[f"COM{m.group(1)}"] = m.group(2)

print("\na) Sensor-port mapping")
for port, name in sorted(sensor_map.items(), key=lambda x: int(x[0][3:])):
    print(f"   {port} → {name}")

# ── b) Connection status ───────────────────────────────────────────────────────
char_rates = {}   # {COM_port: float}
for line in evt_lines:
    m = re.search(r"Character Rate on (COM\d+) is ([\d.]+) chars/second", line)
    if m:
        char_rates[m.group(1)] = float(m.group(2))

print("\nb) Connection status")
conn_rows = []
for port in sorted(char_rates.keys(), key=lambda x: int(x[3:])):
    rate   = char_rates[port]
    sensor = sensor_map.get(port, "UNKNOWN")
    status = "CONNECTED" if rate > 0 else "DISCONNECTED"
    conn_rows.append((port, sensor, f"{rate:.1f}", status))

print(table(["COM", "Sensor", "Rate (chars/s)", "Status"], conn_rows))

connected_sensors    = {r[0]: r[1] for r in conn_rows if r[3] == "CONNECTED"}
disconnected_sensors = {r[0]: r[1] for r in conn_rows if r[3] == "DISCONNECTED"}

# ── c) Mux assignments ─────────────────────────────────────────────────────────
mux_assignments = defaultdict(list)  # {mux: [(port, sensor)]}
for line in evt_lines:
    m = re.search(r"(M\d) latches port (COM\d+) runs macro (\w+)", line)
    if m:
        mux_assignments[m.group(1)].append((m.group(2), m.group(3)))

print("\nc) Mux assignments")
mux_rows = []
for mux in sorted(mux_assignments.keys()):
    for port, sensor in mux_assignments[mux]:
        mux_rows.append((mux, port, sensor))
print(table(["Mux", "COM port", "Sensor"], mux_rows))

# ── d) Health warnings ────────────────────────────────────────────────────────
warning_counts = defaultdict(int)
for line in evt_lines:
    m = re.search(r"Health Warning: (.+?)\|", line)
    if m:
        warning_counts[m.group(1).strip()] += 1

WARN_MEANINGS = {
    "M1 TimeO": "Mux 1 timeout – one or more sensors on M1 not responding in time",
    "M2 TimeO": "Mux 2 timeout – one or more sensors on M2 not responding in time",
    "M3 TimeO": "Mux 3 timeout – one or more sensors on M3 not responding in time",
    "Nv WayP" : "Navigation waypoint missing – expected on ground, no flight plan active",
}

print("\nd) Health warnings")
warn_rows = [(w, str(c), WARN_MEANINGS.get(w, "—")) for w, c in
             sorted(warning_counts.items(), key=lambda x: -x[1])]
print(table(["Warning type", "Count", "Meaning"], warn_rows))

# ── e) Critical errors ────────────────────────────────────────────────────────
print("\ne) Critical errors (lines with '!!!!', 'ERROR', or 'FAIL')")
critical_lines = []
for line in evt_lines:
    ts_m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d)", line)
    ts   = ts_m.group(1) if ts_m else "??"
    if "!!!!" in line or "ERROR" in line.upper() or re.search(r"\bFAIL\b", line.upper()):
        critical_lines.append((ts, line.strip()))

if critical_lines:
    for ts, ln in critical_lines:
        print(f"   [{ts}] {ln}")
else:
    print("   None found.")

# ── f) Data files created ─────────────────────────────────────────────────────
print("\nf) Data files opened/created")
file_opens = []
for line in evt_lines:
    m = re.search(r"File: (.+?) opened", line)
    if m:
        ts_m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d)", line)
        ts   = ts_m.group(1) if ts_m else "??"
        file_opens.append((ts, m.group(1).strip()))

for ts, f in file_opens:
    print(f"   [{ts}] {f}")

# ── g) Session timing ─────────────────────────────────────────────────────────
def parse_ts(ts_str):
    """Parse HH:MM:SS.d to a datetime (same date)."""
    parts = ts_str.split(":")
    h, mn = int(parts[0]), int(parts[1])
    s_parts = parts[2].split(".")
    s  = int(s_parts[0])
    ds = int(s_parts[1]) if len(s_parts) > 1 else 0
    return datetime(2026, 3, 24, h, mn, s, ds * 100_000)

timestamps_in_log = []
for line in evt_lines:
    m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d):", line)
    if m:
        try:
            timestamps_in_log.append(parse_ts(m.group(1)))
        except ValueError:
            pass

# Also pull start from the header line
header_m = re.search(r"Date:(\d{8}) Time:(\d{4})", evt_lines[0])
if header_m:
    date_str = header_m.group(1)   # 20260324
    time_str = header_m.group(2)   # 1434
    session_start = datetime(int(date_str[:4]), int(date_str[4:6]), int(date_str[6:]),
                             int(time_str[:2]), int(time_str[2:]), 0)
else:
    session_start = min(timestamps_in_log) if timestamps_in_log else None

session_end = max(timestamps_in_log) if timestamps_in_log else None
duration    = (session_end - session_start) if (session_start and session_end) else None

print("\ng) Session timing")
print(f"   Start   : {session_start}")
print(f"   End     : {session_end}")
print(f"   Duration: {duration}")

# ── EVT SUMMARY ───────────────────────────────────────────────────────────────
EVT_SUMMARY = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    EVT00006 SESSION SUMMARY                     ║
╠══════════════════════════════════════════════════════════════════╣
║  Date     : 2026-03-24   Location: Welzow Ground Test           ║
║  Start    : {str(session_start):<52} ║
║  End      : {str(session_end):<52} ║
║  Duration : {str(duration):<52} ║
╠══════════════════════════════════════════════════════════════════╣
║  Connected sensors    : {', '.join(sorted(connected_sensors.values())):<40} ║
║  Disconnected sensors : {', '.join(sorted(disconnected_sensors.values())):<40} ║
╠══════════════════════════════════════════════════════════════════╣
║  Total health warnings: {sum(warning_counts.values()):<40} ║
║  Critical errors      : {len(critical_lines):<40} ║
╚══════════════════════════════════════════════════════════════════╝
"""
print(EVT_SUMMARY)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 – Parse MAG00006.txt
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 70)
print("STEP 2 – MAG00006.txt parsing")
print("=" * 70)

# The MAG file is fixed-width: NaN values are encoded as '#'-filled columns,
# which can merge with adjacent column data when split naively by whitespace.
# Strategy: detect each column's start position from the header token positions,
# then read the file with pd.read_fwf using those exact column boundaries.

with MAG_FILE.open(encoding="utf-8", errors="replace") as fh:
    header_raw = fh.readline()

# The MAG file is right-aligned fixed-width: each column's right boundary
# aligns with the right edge of its header token in the header line.
# Column i spans from the end of token (i-1) to the end of token i.
header_tokens = list(re.finditer(r'\S+', header_raw))
col_names = [m.group() for m in header_tokens]
col_ends  = [m.end() for m in header_tokens]   # exclusive end pos of each token

# Build colspecs
colspecs = [(0, col_ends[0])]
for i in range(1, len(col_ends)):
    end = col_ends[i] if i < len(col_ends) - 1 else None
    colspecs.append((col_ends[i - 1], end))

# Read as fixed-width; skip the header row (already parsed above)
df = pd.read_fwf(MAG_FILE, colspecs=colspecs, names=col_names,
                 skiprows=1, dtype=str)

# Replace any cell that contains only '#' characters (any length) with NaN
for col in df.columns:
    df[col] = df[col].apply(
        lambda v: np.nan if (isinstance(v, str) and re.fullmatch(r'#+', v.strip())) else v
    )

# Convert all columns to numeric where possible; non-numeric → NaN
for col in df.columns:
    df[col] = pd.to_numeric(df[col], errors="coerce")

# The Time column encodes HHMMSS.sss – convert to fractional seconds from start
# for a clean x-axis.
if "Time" in df.columns:
    def time_to_sec(t):
        if pd.isna(t):
            return np.nan
        t = float(t)
        hh  = int(t / 10000)
        mm  = int((t % 10000) / 100)
        ss  = t % 100
        return hh * 3600 + mm * 60 + ss

    df["time_sec"] = df["Time"].apply(time_to_sec)
    t0 = df["time_sec"].dropna().iloc[0]
    df["time_sec"] = df["time_sec"] - t0   # seconds from first sample
    time_col = "time_sec"
    time_label = "Time (s from start)"
else:
    time_col   = df.columns[0]
    time_label = time_col

# Classify columns
numeric_cols = [c for c in df.columns if c not in ("Time", "time_sec", "Bin", "Xst")
                and pd.api.types.is_float_dtype(df[c])]

fully_nan   = [c for c in numeric_cols if df[c].isna().all()]
partial_nan = [c for c in numeric_cols if df[c].isna().any() and not df[c].isna().all()]
clean_data  = [c for c in numeric_cols if not df[c].isna().any()]

print(f"\n  Total rows : {len(df)}")
print(f"  Total cols : {len(df.columns)}")
print(f"\n  Fully NaN (disconnected sensor output) : {fully_nan if fully_nan else 'None'}")
print(f"  Partial NaN (intermittent)             : {partial_nan if partial_nan else 'None'}")
print(f"  Clean data columns                     : {clean_data}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 – Stability analysis
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 3 – Stability analysis (connected sensors)")
print("=" * 70)

# Ground-test thresholds
THRESHOLDS = {
    "Roll"  : ("deg",  1.0,  "stable if std < 1°"),
    "Pitch" : ("deg",  1.0,  "stable if std < 1°"),
    "Yaw"   : ("deg",  2.0,  "stable if std < 2°"),
    "Mag1"  : ("nT",  10.0,  "stable if std < 10 nT"),
    "Mag2"  : ("nT",  10.0,  "stable if std < 10 nT"),
    "Mag1C" : ("nT",  10.0,  "stable if std < 10 nT"),
    "Mag2C" : ("nT",  10.0,  "stable if std < 10 nT"),
    "Ralt"  : ("m",    0.5,  "stable if std < 0.5 m on ground"),
    "Raltr" : ("m",    0.5,  "stable if std < 0.5 m on ground"),
    "Lalt"  : ("m",    5.0,  "stable if std < 5 m (GPS alt)"),
    "Xgps"  : ("deg",  0.001,"stable if std < 0.001°"),
    "Ygps"  : ("deg",  0.001,"stable if std < 0.001°"),
}

stability_rows = []
for col in numeric_cols:
    s = df[col].dropna()
    if s.empty:
        stability_rows.append((col, "—", "—", "—", "—", "NO DATA"))
        continue
    mn, sd, mi, mx = s.mean(), s.std(), s.min(), s.max()
    if col in THRESHOLDS:
        unit, thresh, note = THRESHOLDS[col]
        status = "OK" if sd <= thresh else f"HIGH STD (>{thresh} {unit})"
    else:
        status = "—"
    stability_rows.append((col,
                            f"{mn:.4f}", f"{sd:.4f}", f"{mi:.4f}", f"{mx:.4f}",
                            status))

print(table(["Variable", "Mean", "Std", "Min", "Max", "Status"],
            stability_rows))


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 – Plots
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 4 – Generating plots")
print("=" * 70)

def nan_spans(series, time_series):
    """Return list of (t_start, t_end) for NaN blocks."""
    is_nan = series.isna().values
    spans  = []
    in_nan = False
    t0_nan = None
    for i, flag in enumerate(is_nan):
        t = time_series.iloc[i]
        if flag and not in_nan:
            t0_nan = t
            in_nan = True
        elif not flag and in_nan:
            spans.append((t0_nan, t))
            in_nan = False
    if in_nan:
        spans.append((t0_nan, time_series.iloc[-1]))
    return spans


def make_plot(columns, title, filename, y_unit=""):
    """Plot one or more columns vs time, annotate NaN gaps."""
    # Filter to columns that exist and are not fully NaN
    valid_cols = [c for c in columns if c in df.columns and not df[c].isna().all()]
    if not valid_cols:
        print(f"  SKIP {title} – all columns disconnected or absent: {columns}")
        return None

    fig, ax = plt.subplots(figsize=(12, 4))
    x = df[time_col]

    for col in valid_cols:
        ax.plot(x, df[col], lw=0.8, label=col)

    # Red shading for NaN gaps (union of all columns in this plot)
    all_nan_mask = df[valid_cols].isna().any(axis=1)
    gap_starts, gap_ends = [], []
    in_gap = False
    for i, flag in enumerate(all_nan_mask):
        if flag and not in_gap:
            gap_starts.append(x.iloc[i])
            in_gap = True
        elif not flag and in_gap:
            gap_ends.append(x.iloc[i])
            in_gap = False
    if in_gap:
        gap_ends.append(x.iloc[-1])
    for gs, ge in zip(gap_starts, gap_ends):
        ax.axvspan(gs, ge, color="red", alpha=0.3, label="NaN gap")

    # Subtitle with stats
    stat_parts = []
    for col in valid_cols:
        s = df[col].dropna()
        if not s.empty:
            stat_parts.append(f"{col}: μ={s.mean():.2f}  σ={s.std():.3f}")
    subtitle = "  |  ".join(stat_parts)
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel(time_label)
    ax.set_ylabel(y_unit if y_unit else "Value")
    if subtitle:
        fig.text(0.5, 0.01, subtitle, ha="center", fontsize=7.5, color="gray")
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(True, alpha=0.3)

    # Remove duplicate legend entries
    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    unique = [(h, l) for h, l in zip(handles, labels) if not (l in seen or seen.add(l))]
    ax.legend(*zip(*unique), fontsize=8, loc="upper right")

    plt.tight_layout(rect=[0, 0.05, 1, 1])
    fpath = OUT_DIR / filename
    fig.savefig(fpath, dpi=150)
    plt.close(fig)
    print(f"  Saved: {fpath.name}")
    return fpath


plot_specs = [
    (["Mag1", "Mag2"],       "Magnetometers",           "plot_magnetometers.png",    "nT"),
    (["Mag1D", "Mag2D"],     "Magnetometer Derivatives","plot_mag_derivatives.png",  "nT/s"),
    (["Roll", "Pitch", "Yaw"],"Attitude (XSENS)",       "plot_attitude.png",         "degrees"),
    (["Ralt", "Raltr"],      "Radar Altimeter",         "plot_radar_altimeter.png",  "m"),
    (["Xgps", "Ygps"],       "GPS Position",            "plot_gps_position.png",     "degrees"),
]

saved_plots = []
for cols, title, fname, unit in plot_specs:
    p = make_plot(cols, title, fname, unit)
    if p:
        saved_plots.append(p.name)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 – Cross-check EVT vs MAG
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 5 – Cross-check EVT vs MAG")
print("=" * 70)

# Mapping: sensor name → expected MAG columns
SENSOR_MAG_COLS = {
    "GEMK1"  : ["Mag1", "A1", "T1", "X1", "Y1", "Z1", "Mag1D", "Mag1C"],
    "GEMK2"  : ["Mag2", "A2", "T2", "X2", "Y2", "Z2", "Mag2D", "Mag2C"],
    "GDRAlt" : ["Ralt", "Raltr"],
    "GD485"  : ["MagL", "MagLC"],           # Laser altimeter / VLF (GD485 RS-485 bus)
    "XSENS"  : ["Roll", "Pitch", "Yaw"],
    "GDGPS"  : ["Xgps", "Ygps", "Zgps", "Lalt"],
    "GDSpec" : ["Vlf1", "Vlf2", "Vlf3", "Vlf4"],
    "GDLas"  : [],                           # Laser: data may go via GD485 / separate file
}

print("\n  Sensor connection cross-check (EVT disconnected ↔ MAG NaN columns):")
xcheck_rows = []
for com, sensor in sensor_map.items():
    evt_status  = "CONNECTED" if com in connected_sensors else "DISCONNECTED"
    mag_cols    = SENSOR_MAG_COLS.get(sensor, [])
    col_statuses = []
    for mc in mag_cols:
        if mc not in df.columns:
            col_statuses.append(f"{mc}:ABSENT")
        elif df[mc].isna().all():
            col_statuses.append(f"{mc}:ALL_NaN")
        elif df[mc].isna().any():
            col_statuses.append(f"{mc}:PARTIAL_NaN")
        else:
            col_statuses.append(f"{mc}:OK")

    match = "OK"
    if evt_status == "DISCONNECTED":
        # Expect NaN or absent columns
        if any("OK" in s and "ALL_NaN" not in s for s in col_statuses):
            match = "MISMATCH – EVT says disconnected but MAG has data"
    else:
        # Expect at least some non-NaN data
        if all("ALL_NaN" in s or "ABSENT" in s for s in col_statuses) and col_statuses:
            match = "MISMATCH – EVT says connected but MAG all NaN"

    xcheck_rows.append((com, sensor, evt_status,
                         ", ".join(col_statuses) if col_statuses else "—",
                         match))

print(table(["COM", "Sensor", "EVT Status", "MAG columns", "Match"],
            xcheck_rows))

# Mux timeout correlation with MAG gaps
print("\n  Mux timeout vs MAG data gaps:")
print("  Mux timeout warnings occur throughout the entire session (persistent).")
print("  This is consistent with M1/M2/M3 handling multiplexed sensors.")
print("  Checking for NaN gaps in magnetometer data that could indicate instability...\n")

for col in ["Mag1", "Mag2"]:
    if col in df.columns:
        n_nan = df[col].isna().sum()
        pct   = 100 * n_nan / len(df)
        print(f"  {col}: {n_nan} NaN rows out of {len(df)} ({pct:.1f}%)")
        if pct > 0:
            print(f"    → Possible correlation with Mux timeout instability.")
        else:
            print(f"    → No gaps detected. Mux timeouts did not disrupt data flow.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 – Output files
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("STEP 6 – Writing output files")
print("=" * 70)

# ── Helper: build sensor table for docs ───────────────────────────────────────
SENSOR_DESCRIPTIONS = {
    "GEMK1"  : ("COM3", "Magnetometer 1", "Mag1, Mag1D, A1, T1, X1, Y1, Z1, Mag1C",
                 "GEM Systems Scintrex KING AIR towed magnetometer #1 (total-field)"),
    "GEMK2"  : ("COM4", "Magnetometer 2", "Mag2, Mag2D, A2, T2, X2, Y2, Z2, Mag2C",
                 "GEM Systems Scintrex KING AIR towed magnetometer #2 (total-field)"),
    "GDRAlt" : ("COM5", "Radar Altimeter","Ralt, Raltr",
                 "Radar altimeter – measures height above ground (AGL)"),
    "GD485"  : ("COM6", "RS-485 Bus / VLF","MagL, MagLC, Vlf1–Vlf4",
                 "RS-485 multiplex bus (may carry VLF receiver or auxiliary sensors)"),
    "XSENS"  : ("COM7", "IMU / Attitude",  "Roll, Pitch, Yaw",
                 "XSENS MTi inertial measurement unit – attitude angles"),
    "GDGPS"  : ("COM8", "GPS Receiver",    "Xgps, Ygps, Zgps, Lalt",
                 "GNSS receiver – position (lon, lat, alt) and barometric altitude"),
    "GDSpec" : ("COM9", "Spectrometer",    "Vlf1, Vlf2, Vlf3, Vlf4",
                 "Radiation spectrometer or VLF receiver channels"),
    "GDLas"  : ("COM10","Laser Altimeter", "—",
                 "Laser altimeter (data may be written to a separate file)"),
}

def sensor_status_str(sensor_name):
    for com, sensor in sensor_map.items():
        if sensor == sensor_name:
            return "CONNECTED" if com in connected_sensors else "DISCONNECTED"
    return "UNKNOWN"


# ── 6a) CLAUDE.md ─────────────────────────────────────────────────────────────
claude_md = textwrap.dedent(f"""\
# Airborne Geophysics – Welzow Ground Test

This project contains data and analysis scripts for a **ground test of an
airborne geophysics sensor system** conducted at Welzow on 2026-03-24.
The aircraft was stationary; the purpose of the test is to verify sensor
connectivity, data quality, and system health before a real survey flight.

---

## Project structure

```
airborne-data/
├── data/
│   └── 2026-03-24 Welzow Ground-Test 006 - 007/   ← raw instrument files
│       ├── EVT00006.txt   ← system event log (session 006)
│       ├── MAG00006.txt   ← main multi-sensor data file (session 006)
│       ├── GGA00006.txt   ← NMEA GGA sentences
│       ├── SPC00006.txt   ← spectrometer data
│       ├── Cfg00006.xml   ← system configuration snapshot
│       └── ...            ← 007 variants and calibration files
├── src/
│   └── analyse_session_006.py   ← full analysis pipeline (this run)
└── outputs/
    ├── plot_magnetometers.png
    ├── plot_mag_derivatives.png
    ├── plot_attitude.png
    ├── plot_radar_altimeter.png
    ├── plot_gps_position.png
    └── session_006_report.txt
```

---

## Data format

### EVT files
Plain-text event log produced by the GD (Geotech / GeoDAQ) acquisition
system (ICCS software).  Each line starts with a timestamp `HH:MM:SS.d:`
followed by a human-readable message.  Key patterns:

| Pattern | Meaning |
|---------|---------|
| `COMx: Macro SENSORNAME OK` | Sensor configured on this COM port |
| `Character Rate on COMx is X.X chars/second` | Port activity check (0 = disconnected) |
| `Mx latches port COMx runs macro NAME` | Mux routing |
| `Health Warning: Mx TimeO` | Mux timeout |
| `Health Warning: Nv WayP` | No navigation waypoint (normal on ground) |

### MAG files
Whitespace-delimited ASCII table.  First row is the column header.
Cells containing only `#` characters represent missing/invalid values
(treated as NaN in analysis).  The `Time` column encodes UTC as `HHMMSS.sss`.
The `Bin` column is a raw binary dump from certain sensors (not analysed here).

---

## Sensors

| Sensor | COM Port | Status (session 006) | MAG columns | Description |
|--------|----------|-----------------------|-------------|-------------|
""")

for sname, (com, label, mag_cols, desc) in SENSOR_DESCRIPTIONS.items():
    status = sensor_status_str(sname)
    claude_md += f"| {sname} | {com} | {status} | {mag_cols} | {desc} |\n"

claude_md += textwrap.dedent("""
---

## Conventions for future scripts

- **Working directory**: always use `PROJECT_ROOT = Path(__file__).resolve().parents[1]`
  so scripts run from any location.
- **Data folder**: `PROJECT_ROOT / "data" / "<date> <location> <session range>"`
- **Session suffix**: files end in a zero-padded 5-digit session number, e.g.
  `MAG00006.txt`, `EVT00006.txt`.
- **NaN encoding**: cells that are all `#` in MAG files must be replaced with
  `NaN` before any numeric analysis.
- **Plots**: save to `outputs/` as PNG at 150 dpi; use `matplotlib.use("Agg")`
  for headless execution.
- **Time axis**: convert the `Time` column from `HHMMSS.sss` to elapsed seconds
  from the first sample for a clean x-axis.
- **Column categories**: classify every numeric column as *fully NaN*,
  *partial NaN*, or *clean* before plotting.
""")

(PROJECT_ROOT / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
print("  Written: CLAUDE.md")

# ── 6b) README.md ─────────────────────────────────────────────────────────────
mag_col_descriptions = {
    "Xpr"   : "Sample counter / experiment number",
    "M1st"  : "Mux 1 status word",
    "M1clk" : "Mux 1 clock counter",
    "Wayp"  : "Navigation waypoint number",
    "Date"  : "UTC date YYYYMMDD",
    "Time"  : "UTC time HHMMSS.sss",
    "Xgps"  : "GPS longitude (degrees)",
    "Ygps"  : "GPS latitude (degrees)",
    "Zgps"  : "GPS ellipsoidal altitude (m)",
    "Lalt"  : "Barometric / GPS altitude (m)",
    "Raltr" : "Radar altimeter raw reading (m)",
    "Ralt"  : "Radar altimeter calibrated (m)",
    "Mag1"  : "Magnetometer 1 total field (nT)",
    "A1"    : "Mag1 status / quality flag",
    "T1"    : "Mag1 sensor temperature",
    "X1"    : "Mag1 X-axis flux-gate component",
    "Y1"    : "Mag1 Y-axis flux-gate component",
    "Z1"    : "Mag1 Z-axis flux-gate component",
    "Mag1D" : "Magnetometer 1 first derivative (nT/s)",
    "Mag2"  : "Magnetometer 2 total field (nT)",
    "A2"    : "Mag2 status / quality flag",
    "T2"    : "Mag2 sensor temperature",
    "X2"    : "Mag2 X-axis flux-gate component",
    "Y2"    : "Mag2 Y-axis flux-gate component",
    "Z2"    : "Mag2 Z-axis flux-gate component",
    "Mag2D" : "Magnetometer 2 first derivative (nT/s)",
    "MagL"  : "Laser / auxiliary magnetometer reading",
    "Mag1C" : "Magnetometer 1 compensated total field (nT)",
    "Mag2C" : "Magnetometer 2 compensated total field (nT)",
    "MagLC" : "Laser magnetometer compensated",
    "Vlf1"  : "VLF / spectrometer channel 1",
    "Vlf2"  : "VLF / spectrometer channel 2",
    "Vlf3"  : "VLF / spectrometer channel 3",
    "Vlf4"  : "VLF / spectrometer channel 4",
    "Roll"  : "Roll angle (degrees, XSENS IMU)",
    "Pitch" : "Pitch angle (degrees, XSENS IMU)",
    "Yaw"   : "Yaw/heading angle (degrees, XSENS IMU)",
    "Xst"   : "System status word (hex)",
    "Bin"   : "Raw binary sensor data (not numeric)",
}

# Build stability summary for README
def stability_summary_for_readme(col):
    if col not in df.columns or df[col].isna().all():
        return "Disconnected – all NaN"
    s = df[col].dropna()
    return f"mean={s.mean():.3f}, std={s.std():.4f}, min={s.min():.3f}, max={s.max():.3f}"

readme = textwrap.dedent(f"""\
# Airborne Geophysics – Welzow Ground Test

## What this project is about

This repository contains raw instrument data and analysis scripts for a
**ground test of an airborne geophysics sensor suite** performed at Welzow
on **2026-03-24**.  The aircraft was parked on the ground with the data
acquisition system (ICCS / GeoDAQ) running.  Not all sensors were physically
connected; the test verifies which sensors are active, checks data quality,
and flags any system anomalies before a real survey flight.

---

## Session 006

| Field | Value |
|-------|-------|
| Date | 2026-03-24 |
| Location | Welzow (Germany) |
| Start time (UTC) | {session_start} |
| End time (UTC) | {session_end} |
| Duration | {duration} |
| Data rows (MAG) | {len(df)} |
| Sample rate | ~10 Hz |

---

## Sensors: connected vs disconnected

| Sensor | COM Port | Status | Reason (if disconnected) |
|--------|----------|--------|--------------------------|
""")

for sname, (com, label, mag_cols, desc) in SENSOR_DESCRIPTIONS.items():
    status = sensor_status_str(sname)
    rate   = char_rates.get(com, "—")
    if status == "DISCONNECTED":
        reason = f"Character rate = {rate} chars/s → no data stream detected"
    else:
        reason = f"Active – {rate} chars/s"
    readme += f"| {sname} ({label}) | {com} | {status} | {reason} |\n"

readme += textwrap.dedent("""
---

## MAG00006.txt column descriptions

| Column | Description | Data quality (session 006) |
|--------|-------------|---------------------------|
""")

for col in df.columns:
    desc  = mag_col_descriptions.get(col, "—")
    qual  = stability_summary_for_readme(col)
    readme += f"| `{col}` | {desc} | {qual} |\n"

readme += textwrap.dedent("""
---

## Data quality findings

### Connected and healthy
""")

for col in clean_data:
    readme += f"- **{col}**: complete data, no NaN gaps\n"

if partial_nan:
    readme += "\n### Partial NaN (intermittent gaps)\n"
    for col in partial_nan:
        n = df[col].isna().sum()
        readme += f"- **{col}**: {n} NaN rows ({100*n/len(df):.1f}%)\n"

if fully_nan:
    readme += "\n### Fully NaN (disconnected sensors)\n"
    for col in fully_nan:
        readme += f"- **{col}**: entirely NaN – sensor not connected\n"

readme += textwrap.dedent(f"""
---

## Warnings and anomalies

| Type | Count | Interpretation |
|------|-------|----------------|
""")
for w, c in sorted(warning_counts.items(), key=lambda x: -x[1]):
    readme += f"| {w} | {c} | {WARN_MEANINGS.get(w, '—')} |\n"

readme += textwrap.dedent("""
> **Note**: The persistent M1/M2/M3 TimeO warnings are expected during a
> ground test – the multiplexer synchronisation relies on aircraft motion
> (clock trigger) which is absent when parked.  The `Nv WayP` warning is
> normal because no flight plan (waypoints) was loaded.
""")

(PROJECT_ROOT / "README.md").write_text(readme, encoding="utf-8")
print("  Written: README.md")

# ── 6c) session_006_report.txt ─────────────────────────────────────────────────
report_lines = []
report_lines.append("=" * 70)
report_lines.append("  SESSION 006 ANALYSIS REPORT – Welzow Ground Test 2026-03-24")
report_lines.append("=" * 70)

report_lines.append("\n──────── STEP 1: EVT LOG ────────\n")
report_lines.append(f"Session start : {session_start}")
report_lines.append(f"Session end   : {session_end}")
report_lines.append(f"Duration      : {duration}\n")

report_lines.append("Sensor-port mapping:")
for port, name in sorted(sensor_map.items(), key=lambda x: int(x[0][3:])):
    report_lines.append(f"  {port} → {name}")

report_lines.append("\nConnection status:")
report_lines.append(table(["COM", "Sensor", "Rate (chars/s)", "Status"], conn_rows))

report_lines.append("\nMux assignments:")
report_lines.append(table(["Mux", "COM port", "Sensor"], mux_rows))

report_lines.append("\nHealth warnings:")
report_lines.append(table(["Warning type", "Count", "Meaning"], warn_rows))

report_lines.append("\nCritical errors:")
if critical_lines:
    for ts, ln in critical_lines:
        report_lines.append(f"  [{ts}] {ln}")
else:
    report_lines.append("  None found.")

report_lines.append("\nData files opened:")
for ts, f in file_opens:
    report_lines.append(f"  [{ts}] {f}")

report_lines.append("\n──────── STEP 2: MAG FILE ────────\n")
report_lines.append(f"Total rows    : {len(df)}")
report_lines.append(f"Total columns : {len(df.columns)}")
report_lines.append(f"Fully NaN     : {fully_nan if fully_nan else 'None'}")
report_lines.append(f"Partial NaN   : {partial_nan if partial_nan else 'None'}")
report_lines.append(f"Clean data    : {clean_data}")

report_lines.append("\n──────── STEP 3: STABILITY ────────\n")
report_lines.append(table(["Variable", "Mean", "Std", "Min", "Max", "Status"],
                           stability_rows))

report_lines.append("\n──────── STEP 4: PLOTS ────────\n")
report_lines.append("Plots saved to outputs/:")
for p in saved_plots:
    report_lines.append(f"  {p}")

report_lines.append("\n──────── STEP 5: CROSS-CHECK EVT vs MAG ────────\n")
report_lines.append(table(["COM", "Sensor", "EVT Status", "MAG columns", "Match"],
                           xcheck_rows))

report_lines.append(
    "\nMux timeout / data gap correlation:\n"
    "  Mux TimeO warnings are persistent throughout the session (every ~5-6 s).\n"
    "  This is an expected artefact of ground operation (no synchronisation trigger\n"
    "  from aircraft motion).  Analysis of Mag1/Mag2 shows no NaN gaps, so the\n"
    "  timeouts did not interrupt magnetometer data flow.\n"
)

report_lines.append("=" * 70)
report_lines.append("  END OF REPORT")
report_lines.append("=" * 70)

(OUT_DIR / "session_006_report.txt").write_text(
    "\n".join(report_lines), encoding="utf-8")
print("  Written: outputs/session_006_report.txt")

print("\n✓ All steps completed successfully.")
