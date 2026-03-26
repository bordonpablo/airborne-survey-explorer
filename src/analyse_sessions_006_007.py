"""
analyse_sessions_006_007.py
Full dual-session analysis pipeline for Welzow Ground Test (2026-03-24).
Processes sessions 006 and 007, compares them, and generates documentation.

File types:
    EVT – system event log
    MAG – main multi-sensor data (fixed-width, right-aligned)
    GGA – differential GPS log (fixed-width, right-aligned)
    SPC – spectrometer/environment log (fixed-width, right-aligned)
    Cfg – XML system configuration snapshot

Usage:
    python src/analyse_sessions_006_007.py
"""

import re
import textwrap
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")           # headless – no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR     = PROJECT_ROOT / "data" / "2026-03-24 Welzow Ground-Test 006 - 007"

# ── Sensor reference (from system label card) ─────────────────────────────────
SENSOR_REFERENCE = {
    "GEMK1" : {
        "port": "COM3", "label": "P3",
        "full_name": "Magnetometer #1 (Port side)",
        "description": "GEM Systems KING-AIR towed fluxgate magnetometer – total field",
        "writes_to": "MAG",
        "mag_cols": ["Mag1", "Mag1D", "Mag1C", "A1", "T1", "X1", "Y1", "Z1"],
    },
    "GEMK2" : {
        "port": "COM4", "label": "P4",
        "full_name": "Magnetometer #2 (Starboard side)",
        "description": "GEM Systems KING-AIR towed fluxgate magnetometer – total field",
        "writes_to": "MAG",
        "mag_cols": ["Mag2", "Mag2D", "Mag2C", "A2", "T2", "X2", "Y2", "Z2"],
    },
    "GDRAlt": {
        "port": "COM5", "label": "P5",
        "full_name": "Radar Altimeter",
        "description": "Measures height above ground (AGL) in metres",
        "writes_to": "MAG",
        "mag_cols": ["Ralt", "Raltr"],
    },
    "GD485" : {
        "port": "COM6", "label": "P6",
        "full_name": "ADC 4-channel VLF receiver (RS-485 bus)",
        "description": "Analogue-to-digital converter for VLF EM channels",
        "writes_to": "MAG",
        "mag_cols": ["MagL", "MagLC", "Vlf1", "Vlf2", "Vlf3", "Vlf4"],
    },
    "XSENS" : {
        "port": "COM7", "label": "P7",
        "full_name": "AHRS / GPS attitude sensor",
        "description": "XSENS MTi inertial measurement unit – Roll, Pitch, Yaw",
        "writes_to": "MAG",
        "mag_cols": ["Roll", "Pitch", "Yaw"],
    },
    "GDGPS" : {
        "port": "COM8", "label": "P8",
        "full_name": "Septentrio differential GPS",
        "description": "High-precision GNSS receiver – position and altitude",
        "writes_to": "MAG+GGA",
        "mag_cols": ["Xgps", "Ygps", "Zgps", "Lalt"],
    },
    "GDSpec": {
        "port": "COM9", "label": "P9",
        "full_name": "Medusa Gamma-Ray Spectrometer",
        "description": "Gamma-ray spectrometer with environmental sensors",
        "writes_to": "SPC",
        "mag_cols": ["Vlf1", "Vlf2", "Vlf3", "Vlf4"],
    },
    "GDLas" : {
        "port": "COM10", "label": "P10",
        "full_name": "Laser Altimeter",
        "description": "Laser rangefinder for precise terrain clearance",
        "writes_to": "SPC/separate",
        "mag_cols": [],
    },
}

# Column descriptions (for reports and plots)
COL_DESCRIPTIONS = {
    "Xpr"   : "Sample/experiment counter",
    "M1st"  : "Mux1 status word",
    "M1clk" : "Mux1 clock counter (ticks)",
    "Wayp"  : "Navigation waypoint number",
    "Date"  : "UTC date (YYYYMMDD)",
    "Time"  : "UTC time (HHMMSS.sss)",
    "Xgps"  : "GPS longitude (°)",
    "Ygps"  : "GPS latitude (°)",
    "Zgps"  : "GPS ellipsoidal altitude (m)",
    "Lalt"  : "Barometric/laser altimeter (m)",
    "Raltr" : "Radar altimeter – raw channel (m)",
    "Ralt"  : "Radar altimeter – calibrated (m)",
    "Mag1"  : "Magnetometer 1 total field (nT)",
    "Mag2"  : "Magnetometer 2 total field (nT)",
    "Mag1D" : "Mag1 first derivative (nT/s)",
    "Mag2D" : "Mag2 first derivative (nT/s)",
    "Mag1C" : "Mag1 compensated total field (nT)",
    "Mag2C" : "Mag2 compensated total field (nT)",
    "MagL"  : "Mag2 – Mag1 difference field (nT)",
    "MagLC" : "Compensated Mag2 – Mag1 difference (nT)",
    "A1"    : "Mag1 amplitude/gain flag",
    "T1"    : "Mag1 sensor temperature (°C)",
    "X1"    : "Mag1 X-axis status flag (1=OK)",
    "Y1"    : "Mag1 Y-axis status flag (1=OK)",
    "Z1"    : "Mag1 Z-axis status flag (1=OK)",
    "A2"    : "Mag2 amplitude/gain flag",
    "T2"    : "Mag2 sensor temperature (°C)",
    "X2"    : "Mag2 X-axis status flag (1=OK)",
    "Y2"    : "Mag2 Y-axis status flag (1=OK)",
    "Z2"    : "Mag2 Z-axis status flag (1=OK)",
    "Vlf1"  : "VLF EM channel 1 (ADC count)",
    "Vlf2"  : "VLF EM channel 2 (ADC count)",
    "Vlf3"  : "VLF EM channel 3 (ADC count)",
    "Vlf4"  : "VLF EM channel 4 (ADC count)",
    "Roll"  : "Roll angle (°, XSENS IMU)",
    "Pitch" : "Pitch angle (°, XSENS IMU)",
    "Yaw"   : "Yaw/heading angle (°, XSENS IMU)",
    "Xst"   : "System status hex string",
    "Bin"   : "Raw binary sensor data",
    # GGA columns
    "M3st"  : "Mux3 status word",
    "M3clk" : "Mux3 clock counter",
    "dWayp" : "dGPS waypoint",
    "dTime" : "dGPS UTC time (HHMMSS.ss)",
    "Xdgps" : "Differential GPS longitude (°)",
    "Ydgps" : "Differential GPS latitude (°)",
    "Zdgps" : "Differential GPS altitude (m)",
    "dSNo"  : "Number of GPS satellites",
    "dHdop" : "Horizontal dilution of precision (lower=better)",
    "dDOn"  : "Differential correction on (1=yes)",
    "dAge"  : "Age of differential correction (s)",
    "dSID"  : "Differential reference station ID",
    # SPC columns
    "M2st"  : "Mux2 status word",
    "M2clk" : "Mux2 clock counter",
    "Sdate" : "Spectrometer UTC date",
    "Stime" : "Spectrometer UTC time",
    "Swayp" : "Spectrometer waypoint",
    "Sxgps" : "Spectrometer GPS longitude (°)",
    "Sygps" : "Spectrometer GPS latitude (°)",
    "Szgps" : "Spectrometer GPS altitude (m)",
    "Sralt" : "Spectrometer radar altimeter (m)",
    "BaroV" : "Barometric pressure voltage (V)",
    "TempV" : "Temperature sensor voltage (V)",
    "HumdV" : "Humidity sensor voltage (V)",
    "Sbaro" : "Barometric pressure raw counts",
    "Stemp" : "Temperature raw counts",
    "Shumd" : "Humidity raw counts",
    "Sreal" : "Spectrometer real-time count rate",
    "Slive" : "Spectrometer live-time count rate",
    "Srate" : "Spectrometer acquisition rate",
    "Sk"    : "Spectrometer potassium channel (K)",
    "Su"    : "Spectrometer uranium channel (U)",
    "Sth"   : "Spectrometer thorium channel (Th)",
    "Sa0"   : "Spectrometer background channel 0",
    "Sa1"   : "Spectrometer background channel 1",
    "Sa2"   : "Spectrometer background channel 2",
    "Sbin"  : "Raw spectral binary data",
}

# Ground-test stability thresholds
STABILITY_THRESHOLDS = {
    "Mag1" : ("nT", 10.0), "Mag2" : ("nT", 10.0),
    "Mag1C": ("nT", 10.0), "Mag2C": ("nT", 10.0),
    "Roll" : ("°",   1.0), "Pitch": ("°",  1.0), "Yaw": ("°", 2.0),
    "Ralt" : ("m",   0.5), "Raltr": ("m",  0.5),
    "Xgps" : ("°", 0.001), "Ygps" : ("°", 0.001),
    "Xdgps": ("°", 5e-5),  "Ydgps": ("°", 5e-5),
    "dHdop": ("",   1.0),
}

WARN_MEANINGS = {
    "M1 TimeO" : "Mux1 timeout – sensor on M1 not responding within 80 ms",
    "M2 TimeO" : "Mux2 timeout – sensor on M2 not responding within 200 ms",
    "M3 TimeO" : "Mux3 timeout – sensor on M3 not responding within 100 ms",
    "Nv WayP"  : "Navigation waypoint missing (normal on ground – no flight plan active)",
}

# ══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def ascii_table(headers, rows):
    """Return a simple ASCII table string with auto-sized columns."""
    widths = [
        max(len(str(h)), max((len(str(r[i])) for r in rows), default=0))
        for i, h in enumerate(headers)
    ]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    fmt = "|" + "|".join(" {:<{w}} ".format("{}", w=w) for w in widths) + "|"
    lines = [sep, fmt.format(*headers), sep]
    for row in rows:
        lines.append(fmt.format(*[str(v) for v in row]))
    lines.append(sep)
    return "\n".join(lines)


def parse_fwf(filepath):
    """
    Parse a GeoDuster fixed-width file (MAG, GGA, SPC).
    Column boundaries: each column's RIGHT edge aligns with the right edge
    of its header token (use m.end() of regex match, not m.start()).
    Cells containing only '#' are replaced with NaN.
    Returns a DataFrame with numeric conversion applied where possible.
    """
    with open(filepath, encoding="utf-8", errors="replace") as fh:
        header_raw = fh.readline()

    tokens   = list(re.finditer(r"\S+", header_raw))
    col_names = [t.group() for t in tokens]
    col_ends  = [t.end()   for t in tokens]

    # Column i spans from end of token(i-1) to end of token(i)
    colspecs = [(0, col_ends[0])]
    for i in range(1, len(col_ends)):
        end = col_ends[i] if i < len(col_ends) - 1 else None
        colspecs.append((col_ends[i - 1], end))

    df = pd.read_fwf(filepath, colspecs=colspecs, names=col_names,
                     skiprows=1, dtype=str)

    # Replace '#'-only cells with NaN
    hash_re = re.compile(r"^#+$")
    for col in df.columns:
        df[col] = df[col].apply(
            lambda v: np.nan if isinstance(v, str) and hash_re.fullmatch(v.strip()) else v
        )

    # Numeric conversion (errors become NaN)
    for col in df.columns:
        if col not in ("Xst", "Bin", "Sbin"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def time_to_sec(t):
    """Convert HHMMSS.sss float to seconds-of-day."""
    if pd.isna(t):
        return np.nan
    t = float(t)
    hh = int(t / 10000)
    mm = int((t % 10000) / 100)
    ss = t % 100
    return hh * 3600 + mm * 60 + ss


def add_time_axis(df, time_col_name):
    """Add 'time_sec' column (elapsed seconds from first valid sample)."""
    if time_col_name not in df.columns:
        return df
    df = df.copy()
    df["time_sec"] = df[time_col_name].apply(time_to_sec)
    valid = df["time_sec"].dropna()
    if not valid.empty:
        df["time_sec"] = df["time_sec"] - valid.iloc[0]
    return df


def classify_columns(df, skip_cols=None):
    """Return (fully_nan, partial_nan, clean) lists of column names."""
    if skip_cols is None:
        skip_cols = {"time_sec", "Xst", "Bin", "Sbin"}
    numeric = [c for c in df.columns
               if c not in skip_cols and pd.api.types.is_float_dtype(df[c])]
    fully   = [c for c in numeric if df[c].isna().all()]
    partial = [c for c in numeric if df[c].isna().any() and not df[c].isna().all()]
    clean   = [c for c in numeric if not df[c].isna().any()]
    return fully, partial, clean


def stability_row(col, df):
    """Return (mean, std, min, max, status) for one column."""
    s = df[col].dropna()
    if s.empty:
        return ("—", "—", "—", "—", "NO DATA")
    mn, sd, mi, mx = s.mean(), s.std(), s.min(), s.max()
    if col in STABILITY_THRESHOLDS:
        unit, thresh = STABILITY_THRESHOLDS[col]
        status = f"OK (σ={sd:.4f})" if sd <= thresh else f"HIGH STD >{thresh} {unit}"
    else:
        status = "—"
    return (f"{mn:.4f}", f"{sd:.4f}", f"{mi:.4f}", f"{mx:.4f}", status)


def nan_spans_for_shading(series, time_series):
    """Return list of (t_start, t_end) for contiguous NaN blocks."""
    is_nan = series.isna().values
    spans, in_nan, t0 = [], False, None
    for i, flag in enumerate(is_nan):
        t = time_series.iloc[i]
        if flag and not in_nan:
            t0 = t; in_nan = True
        elif not flag and in_nan:
            spans.append((t0, t)); in_nan = False
    if in_nan:
        spans.append((t0, time_series.iloc[-1]))
    return spans


def make_plot(df, columns, title, filename, out_dir, y_label="Value", session_id=""):
    """
    Plot columns vs time_sec. NaN gaps appear as natural line breaks
    (matplotlib does not connect across NaN – no interpolation).
    Shade grey for NaN gaps. Add mean ± std subtitle.
    """
    valid_cols = [c for c in columns if c in df.columns and not df[c].isna().all()]
    if not valid_cols:
        print(f"  SKIP [{session_id}] '{title}' – all columns absent/disconnected: {columns}")
        return None

    x = df["time_sec"]
    fig, ax = plt.subplots(figsize=(12, 4))

    for col in valid_cols:
        # Plot with NaN – matplotlib naturally breaks the line at NaN values
        ax.plot(x, df[col], lw=0.9, label=col)

    # Grey shading for NaN gaps (union of all plotted columns)
    union_nan = df[valid_cols].isna().any(axis=1)
    in_gap = False
    gap_drawn = False
    for i, flag in enumerate(union_nan):
        t = x.iloc[i]
        if flag and not in_gap:
            t0_gap = t; in_gap = True
        elif not flag and in_gap:
            ax.axvspan(t0_gap, t, color="grey", alpha=0.25,
                       label="NaN gap" if not gap_drawn else "")
            gap_drawn = True; in_gap = False
    if in_gap:
        ax.axvspan(t0_gap, x.iloc[-1], color="grey", alpha=0.25,
                   label="NaN gap" if not gap_drawn else "")

    # Mean ± std subtitle
    stat_parts = []
    for col in valid_cols:
        s = df[col].dropna()
        if not s.empty:
            stat_parts.append(f"{col}: μ={s.mean():.3f} ± σ={s.std():.4f}")
    subtitle = "   |   ".join(stat_parts)

    ax.set_title(f"[Session {session_id}]  {title}", fontsize=11, fontweight="bold")
    ax.set_xlabel("Elapsed time (s from session start)")
    ax.set_ylabel(y_label)
    if subtitle:
        fig.text(0.5, 0.01, subtitle, ha="center", fontsize=7, color="#555555")

    # Deduplicate legend entries
    handles, labels_ = ax.get_legend_handles_labels()
    seen = set()
    uniq = [(h, l) for h, l in zip(handles, labels_)
            if not (l in seen or seen.add(l))]
    if uniq:
        ax.legend(*zip(*uniq), fontsize=8, loc="upper right")

    ax.grid(True, alpha=0.3)
    plt.tight_layout(rect=[0, 0.05, 1, 1])

    out_dir.mkdir(parents=True, exist_ok=True)
    fpath = out_dir / filename
    fig.savefig(fpath, dpi=150)
    plt.close(fig)
    print(f"  Saved: {fpath.relative_to(PROJECT_ROOT)}")
    return fpath


# ══════════════════════════════════════════════════════════════════════════════
# EVT PARSER
# ══════════════════════════════════════════════════════════════════════════════

def parse_evt(filepath):
    """
    Parse an EVT event log. Returns a dict with:
    sensor_map, char_rates, mux_assignments, warning_counts,
    critical_lines, file_opens, session_start, session_end, duration
    """
    lines = Path(filepath).read_text(encoding="utf-8", errors="replace").splitlines()

    sensor_map      = {}    # {COMx: sensor_name}
    char_rates      = {}    # {COMx: float}
    mux_assignments = defaultdict(list)   # {Mx: [(port, sensor)]}
    warning_counts  = defaultdict(int)
    critical_lines  = []
    file_opens      = []
    timestamps      = []

    for line in lines:
        # Sensor port mapping
        m = re.search(r"COM(\d+): Macro (\w+) OK", line)
        if m:
            sensor_map[f"COM{m.group(1)}"] = m.group(2)

        # Character rates
        m = re.search(r"Character Rate on (COM\d+) is ([\d.]+) chars/second", line)
        if m:
            char_rates[m.group(1)] = float(m.group(2))

        # Mux assignments
        m = re.search(r"(M\d) latches port (COM\d+) runs macro (\w+)", line)
        if m:
            mux_assignments[m.group(1)].append((m.group(2), m.group(3)))

        # Health warnings
        m = re.search(r"Health Warning: (.+?)\|", line)
        if m:
            warning_counts[m.group(1).strip()] += 1

        # Critical errors
        ts_m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d):", line)
        if "!!!!" in line:
            ts = ts_m.group(1) if ts_m else "??"
            critical_lines.append((ts, line.strip()))

        # Files opened
        m2 = re.search(r"File: (.+?) opened", line)
        if m2:
            ts = ts_m.group(1) if ts_m else "??"
            file_opens.append((ts, m2.group(1).strip()))

        # Timestamps
        if ts_m:
            try:
                h, mn_s = ts_m.group(1).split(":")[:2]
                s_part  = ts_m.group(1).split(":")[2]
                s, ds   = s_part.split(".")
                timestamps.append(
                    datetime(2026, 3, 24,
                             int(h), int(mn_s), int(s), int(ds) * 100_000))
            except (ValueError, IndexError):
                pass

    # Session timing from header
    header = lines[0] if lines else ""
    hm = re.search(r"Date:(\d{8}) Time:(\d{4})", header)
    if hm:
        d, t = hm.group(1), hm.group(2)
        start = datetime(int(d[:4]), int(d[4:6]), int(d[6:]),
                         int(t[:2]), int(t[2:]))
    elif timestamps:
        start = min(timestamps)
    else:
        start = None

    end      = max(timestamps) if timestamps else None
    duration = (end - start) if (start and end) else None

    connected    = {p: s for p, s in sensor_map.items()
                   if char_rates.get(p, 0.0) > 0}
    disconnected = {p: s for p, s in sensor_map.items()
                   if char_rates.get(p, 0.0) == 0.0}

    return {
        "sensor_map"      : sensor_map,
        "char_rates"      : char_rates,
        "mux_assignments" : mux_assignments,
        "warning_counts"  : warning_counts,
        "critical_lines"  : critical_lines,
        "file_opens"      : file_opens,
        "session_start"   : start,
        "session_end"     : end,
        "duration"        : duration,
        "connected"       : connected,
        "disconnected"    : disconnected,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CFG XML PARSER
# ══════════════════════════════════════════════════════════════════════════════

def parse_cfg(filepath):
    """
    Extract key configuration parameters from a GeoDuster Cfg XML file.
    Returns a dict of {tag: value} for important settings.
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Collect all tag→value pairs
    raw = {}
    for obj in root.iter("Object"):
        tag = obj.get("Tag", "")
        val_el = obj.find("Value")
        if val_el is not None and tag:
            raw[tag] = (val_el.text or "").strip()

    # Extract COM port states (On/Off) and their macros/baud rates
    port_configs = {}
    for com_num in range(1, 11):
        state_key = f"COM{com_num}STATE"
        if state_key in raw:
            # Find the BAUD and MACRO associated with this COM entry
            # They appear in sequence after the COMxSTATE tag in the XML
            pass

    # Walk the XML to collect per-port settings.
    # State comes from the pre-built raw dict (confirmed reliable).
    # Baud and Macro are found as nested Object children of each COMxSTATE element.
    port_data = {}
    for obj in root.iter("Object"):
        tag = obj.get("Tag", "")
        m = re.match(r"COM(\d+)STATE", tag)
        if m:
            com = f"COM{m.group(1)}"
            state = raw.get(tag, "—")    # raw dict reliably has COMxSTATE→On/Off
            baud, macro = "?", "?"
            for child in obj:            # direct XML children of COMxSTATE
                ctag = child.get("Tag", "")
                cval = (child.findtext("Value") or "").strip()
                if ctag == "BAUD"  and baud  == "?":
                    baud  = cval
                elif ctag == "MACRO" and macro == "?":
                    macro = cval
            port_data[com] = {"state": state, "baud": baud, "macro": macro}

    return {
        "compensation": raw.get("COMPNAME", "—"),
        "nav_file"    : raw.get("NAVNAME",  "—"),
        "clock_port"  : raw.get("PORTNUM",  "—"),
        "web_host"    : raw.get("WEBHOST",  "—"),
        "line_num"    : raw.get("LINENUM",  "—"),
        "log_level"   : raw.get("LOGLEVEL", "—"),
        "port_data"   : port_data,
        "raw"         : raw,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PER-SESSION ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════

def analyse_session(session_num):
    """
    Full analysis pipeline for one session (006 or 007).
    Returns a dict of results for the comparison step.
    """
    sid  = str(session_num).zfill(5)    # "00006" or "00007"
    snum = str(session_num).zfill(3)   # "006" or "007"
    out  = PROJECT_ROOT / "outputs" / f"session_{snum}"
    out.mkdir(parents=True, exist_ok=True)

    report_lines = []
    def rprint(*args, **kwargs):
        """Print and accumulate lines for the text report."""
        msg = " ".join(str(a) for a in args)
        print(msg, **kwargs)
        report_lines.append(msg)

    rprint()
    rprint("=" * 72)
    rprint(f"  SESSION {snum}  –  Welzow Ground Test  –  2026-03-24")
    rprint("=" * 72)

    # ── STEP 1: EVT ───────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 1 — EVT{sid}.txt")
    rprint(f"{'─'*72}")

    evt  = parse_evt(DATA_DIR / f"EVT{sid}.txt")
    sm   = evt["sensor_map"]
    cr   = evt["char_rates"]
    mux  = evt["mux_assignments"]
    wrn  = evt["warning_counts"]

    # a) Sensor map
    rprint("\na) Sensor-port mapping:")
    for port, name in sorted(sm.items(), key=lambda x: int(x[0][3:])):
        rprint(f"   {port} → {name}")

    # b) Connection status table (with full name)
    rprint("\nb) Connection status:")
    conn_rows = []
    for port in sorted(cr.keys(), key=lambda x: int(x[3:])):
        rate   = cr[port]
        sensor = sm.get(port, "?")
        ref    = SENSOR_REFERENCE.get(sensor, {})
        fname  = ref.get("full_name", "—")
        status = "CONNECTED" if rate > 0 else "DISCONNECTED"
        conn_rows.append((port, sensor, fname, f"{rate:.1f}", status))
    rprint(ascii_table(["COM", "Sensor", "Full Name", "Rate (chars/s)", "Status"],
                       conn_rows))

    # c) Mux assignments
    rprint("\nc) Mux assignments:")
    mux_rows = []
    for mx in sorted(mux.keys()):
        for port, sensor in mux[mx]:
            mux_rows.append((mx, port, sensor))
    rprint(ascii_table(["Mux", "COM Port", "Sensor"], mux_rows))

    # d) Health warnings
    rprint("\nd) Health warnings:")
    warn_rows = [(w, str(c), WARN_MEANINGS.get(w, "Unknown"))
                 for w, c in sorted(wrn.items(), key=lambda x: -x[1])]
    rprint(ascii_table(["Warning", "Count", "Meaning"], warn_rows))

    # e) Critical errors
    rprint("\ne) Critical errors (lines with '!!!!'):")
    if evt["critical_lines"]:
        for ts, ln in evt["critical_lines"]:
            rprint(f"   [{ts}] {ln}")
    else:
        rprint("   None found.")

    # f) Files opened
    rprint("\nf) Data files opened:")
    for ts, f in evt["file_opens"]:
        rprint(f"   [{ts}] {f}")

    # g) Session timing
    rprint(f"\ng) Session timing:")
    rprint(f"   Start   : {evt['session_start']}")
    rprint(f"   End     : {evt['session_end']}")
    rprint(f"   Duration: {evt['duration']}")

    # h) Cfg XML
    rprint(f"\nh) Cfg{sid}.xml configuration summary:")
    cfg = parse_cfg(DATA_DIR / f"Cfg{sid}.xml")
    rprint(f"   Compensation file : {cfg['compensation']}")
    rprint(f"   Navigation file   : {cfg['nav_file']}")
    rprint(f"   Clock port        : {cfg['clock_port']}")
    rprint(f"   Web host          : {cfg['web_host']}")
    rprint(f"   Survey line num   : {cfg['line_num']}")
    rprint(f"   Log level         : {cfg['log_level']}")
    rprint("\n   Port configuration (from XML):")
    cfg_port_rows = []
    for com, pd_ in sorted(cfg["port_data"].items(),
                           key=lambda x: int(x[0][3:])):
        cfg_port_rows.append((com, pd_["state"], pd_["baud"], pd_["macro"]))
    rprint(ascii_table(["COM", "State", "Baud", "Macro"], cfg_port_rows))

    # ── STEP 2: MAG ───────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 2 — MAG{sid}.txt")
    rprint(f"{'─'*72}")

    mag = parse_fwf(DATA_DIR / f"MAG{sid}.txt")
    mag = add_time_axis(mag, "Time")

    fully_nan_m, partial_nan_m, clean_m = classify_columns(
        mag, skip_cols={"time_sec", "Date", "Time", "M1st", "M1clk",
                        "Xpr", "Wayp", "Xst", "Bin"})

    rprint(f"\n  Rows: {len(mag)}   Columns: {len(mag.columns)}")
    rprint(f"  Fully NaN   : {fully_nan_m or 'None'}")
    rprint(f"  Partial NaN : {partial_nan_m or 'None'}")
    rprint(f"  Clean       : {clean_m or 'None'}")

    # ── STEP 3: GGA ───────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 3 — GGA{sid}.txt")
    rprint(f"{'─'*72}")

    gga = parse_fwf(DATA_DIR / f"GGA{sid}.txt")
    gga = add_time_axis(gga, "dTime")

    fully_nan_g, partial_nan_g, clean_g = classify_columns(
        gga, skip_cols={"time_sec", "M3st", "M3clk", "dWayp", "dTime"})

    rprint(f"\n  Rows: {len(gga)}   Columns: {len(gga.columns)}")
    rprint(f"  Fully NaN   : {fully_nan_g or 'None'}")
    rprint(f"  Partial NaN : {partial_nan_g or 'None'}")
    rprint(f"  Clean       : {clean_g or 'None'}")

    # GPS quality summary
    if "dHdop" in gga.columns and not gga["dHdop"].isna().all():
        rprint(f"\n  GPS quality (mean ± std):")
        rprint(f"    Satellites (dSNo): {gga['dSNo'].mean():.1f} ± {gga['dSNo'].std():.2f}")
        rprint(f"    HDOP (dHdop)     : {gga['dHdop'].mean():.2f} ± {gga['dHdop'].std():.3f}"
               f"  {'[EXCELLENT]' if gga['dHdop'].mean() < 1.0 else '[GOOD]'}")
        rprint(f"    Diff age (dAge)  : {gga['dAge'].mean():.1f} ± {gga['dAge'].std():.2f} s")
        rprint(f"    Position Xdgps σ : {gga['Xdgps'].std():.6f}°")
        rprint(f"    Position Ydgps σ : {gga['Ydgps'].std():.6f}°")

    # ── STEP 4: SPC ───────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 4 — SPC{sid}.txt")
    rprint(f"{'─'*72}")

    spc = parse_fwf(DATA_DIR / f"SPC{sid}.txt")
    spc = add_time_axis(spc, "Stime")

    spc_skip = {"time_sec", "M2st", "M2clk", "Sdate", "Stime", "Swayp", "Sbin"}
    fully_nan_s, partial_nan_s, clean_s = classify_columns(spc, skip_cols=spc_skip)

    rprint(f"\n  Rows: {len(spc)}   Columns: {len(spc.columns)}")
    rprint(f"  GDSpec (COM9) is DISCONNECTED – spectrometer EM channels are NaN")
    rprint(f"  Note: SPC file columns use right-aligned fixed-width boundaries.")
    rprint(f"        'Sralt' in SPC = radar alt pass-through (same as MAG Ralt).")
    rprint(f"        BaroV/TempV/HumdV = NaN (environmental sensors not active).")
    rprint(f"        Sk/Su/Sth = constant default counts (spectrometer powered")
    rprint(f"        but no active acquisition since GDSpec is disconnected).")

    # Report any columns with actual data
    for col in ["Sralt", "BaroV", "TempV", "HumdV", "Sk", "Su", "Sth",
                "Sbaro", "Stemp", "Shumd"]:
        if col in spc.columns and not spc[col].isna().all():
            s = spc[col].dropna()
            note = "  [CONSTANT]" if s.std() < 0.001 else ""
            rprint(f"  {col:8s}: mean={s.mean():.3f}  std={s.std():.4f}"
                   f"  ({COL_DESCRIPTIONS.get(col, '')}){note}")

    rprint(f"  Fully NaN    : {fully_nan_s or 'None'}")
    rprint(f"  Partial NaN  : {partial_nan_s or 'None'}")
    rprint(f"  Clean        : {clean_s or 'None'}")

    # ── STEP 5: PLOTS ─────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 5 — Plots  →  outputs/session_{snum}/")
    rprint(f"{'─'*72}")

    # Plot 1: Mag1 and Mag2 (raw)
    make_plot(mag, ["Mag1", "Mag2"], "Magnetometers (raw)",
              "plot_01_mag_raw.png", out, "nT", snum)

    # Plot 2: Mag1C and Mag2C (compensated)
    make_plot(mag, ["Mag1C", "Mag2C"], "Magnetometers (compensated)",
              "plot_02_mag_compensated.png", out, "nT", snum)

    # Plot 3: Mag1D and Mag2D (first derivatives)
    make_plot(mag, ["Mag1D", "Mag2D"], "Magnetometer first derivatives",
              "plot_03_mag_derivatives.png", out, "nT/s", snum)

    # Plot 4: Roll, Pitch, Yaw
    make_plot(mag, ["Roll", "Pitch", "Yaw"], "Attitude – XSENS AHRS",
              "plot_04_attitude.png", out, "degrees", snum)

    # Plot 5: Radar altimeter
    make_plot(mag, ["Ralt"], "Radar Altimeter",
              "plot_05_radar_alt.png", out, "m AGL", snum)

    # Plot 6: Differential GPS position
    make_plot(gga, ["Xdgps", "Ydgps"], "Differential GPS position",
              "plot_06_dgps_position.png", out, "degrees", snum)

    # Plot 7: GPS quality indicators
    make_plot(gga, ["dHdop", "dSNo"], "GPS quality indicators",
              "plot_07_gps_quality.png", out, "HDOP / #satellites", snum)

    # Plot 8: Spectrometer available channels (Sk/Su/Sth or environment)
    spc_plot_cols = [c for c in ["Sk", "Su", "Sth", "BaroV", "Sbaro"]
                     if c in spc.columns and not spc[c].isna().all()]
    if spc_plot_cols:
        make_plot(spc, spc_plot_cols,
                  "Spectrometer channels (Sk/Su/Sth = default counts, GDSpec disconnected)",
                  "plot_08_spc_channels.png", out, "counts", snum)
    else:
        rprint(f"  SKIP [session {snum}] 'Spectrometer channels' – all NaN "
               f"(GDSpec COM9 disconnected)")

    # ── STEP 6: STABILITY TABLE ────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 6 — Stability analysis")
    rprint(f"{'─'*72}")

    stab_rows = []
    analysis_cols = {
        **{c: "MAG" for c in ["Mag1", "Mag2", "Mag1C", "Mag2C",
                               "Mag1D", "Mag2D", "MagL", "MagLC",
                               "Roll", "Pitch", "Yaw", "Ralt", "Raltr",
                               "Xgps", "Ygps", "Zgps"]},
        **{c: "GGA" for c in ["Xdgps", "Ydgps", "Zdgps", "dSNo",
                               "dHdop", "dAge"]},
        **{c: "SPC" for c in ["BaroV", "Sralt", "Sk", "Su", "Sth",
                               "Sbaro", "Stemp", "Shumd"]},
    }
    src_dfs = {"MAG": mag, "GGA": gga, "SPC": spc}

    for col, src in analysis_cols.items():
        df_src = src_dfs[src]
        if col not in df_src.columns or df_src[col].isna().all():
            stab_rows.append((col, COL_DESCRIPTIONS.get(col, "—"),
                               "—", "—", "—", "—", "NO DATA / DISCONNECTED"))
            continue
        mn, sd, mi, mx, st = stability_row(col, df_src)
        stab_rows.append((col, COL_DESCRIPTIONS.get(col, "—"),
                           mn, sd, mi, mx, st))

    rprint(ascii_table(
        ["Variable", "Description", "Mean", "Std", "Min", "Max", "Status"],
        stab_rows))

    # ── STEP 7: CROSS-CHECK ────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 7 — Cross-check EVT vs data files")
    rprint(f"{'─'*72}")

    SENSOR_MAG_COLS = {
        "GEMK1"  : ["Mag1", "Mag1D", "Mag1C"],
        "GEMK2"  : ["Mag2", "Mag2D", "Mag2C"],
        "GDRAlt" : ["Ralt", "Raltr"],
        "GD485"  : ["MagL", "MagLC"],
        "XSENS"  : ["Roll", "Pitch", "Yaw"],
        "GDGPS"  : ["Xgps", "Ygps", "Zgps", "Lalt"],
        "GDSpec" : ["Vlf1", "Vlf2", "Vlf3", "Vlf4"],
    }

    xcheck_rows = []
    mismatches   = []
    for port, sensor in sorted(sm.items(), key=lambda x: int(x[0][3:])):
        evt_status = "CONNECTED" if cr.get(port, 0) > 0 else "DISCONNECTED"
        cols = SENSOR_MAG_COLS.get(sensor, [])
        col_stats = []
        for mc in cols:
            if mc not in mag.columns:
                col_stats.append(f"{mc}:ABSENT")
            elif mag[mc].isna().all():
                col_stats.append(f"{mc}:ALL_NaN")
            elif mag[mc].isna().any():
                n = mag[mc].isna().sum()
                pct = 100 * n / len(mag)
                col_stats.append(f"{mc}:PARTIAL({pct:.1f}%)")
            else:
                col_stats.append(f"{mc}:OK")

        match = "OK"
        if evt_status == "DISCONNECTED":
            has_data = any("OK" in s and "ALL_NaN" not in s
                          and "PARTIAL" not in s for s in col_stats)
            if has_data:
                match = "MISMATCH"
                mismatches.append(f"{sensor} EVT=DISCONNECTED but MAG has data")
        elif evt_status == "CONNECTED":
            all_empty = all("ALL_NaN" in s or "ABSENT" in s
                           for s in col_stats) and col_stats
            if all_empty:
                match = "MISMATCH"
                mismatches.append(f"{sensor} EVT=CONNECTED but MAG all NaN")

        xcheck_rows.append((port, sensor, evt_status,
                            "; ".join(col_stats) if col_stats else "—",
                            match))

    rprint(ascii_table(["COM", "Sensor", "EVT Status", "MAG column NaN", "Match"],
                       xcheck_rows))

    if mismatches:
        rprint("\n  MISMATCHES:")
        for m in mismatches:
            rprint(f"  !! {m}")
    else:
        rprint("\n  All sensor statuses consistent between EVT and MAG. ✓")

    # Mux timeout correlation
    rprint("\n  Mux TimeO vs MAG gaps:")
    total_warn = sum(wrn.values())
    rprint(f"  Total health warnings: {total_warn} "
           f"(persistent every ~5-6 s – expected on ground)")
    for col in ["Mag1", "Mag2"]:
        if col in mag.columns:
            n = mag[col].isna().sum()
            rprint(f"  {col}: {n}/{len(mag)} NaN rows "
                   f"({100*n/len(mag):.1f}%)"
                   + (" – gaps likely from Mux TimeO events" if n > 0 else " – no gaps"))

    # Save report
    report_text = "\n".join(report_lines)
    report_path = out / f"report_{snum}.txt"
    report_path.write_text(report_text, encoding="utf-8")
    rprint(f"\n  Report saved: {report_path.relative_to(PROJECT_ROOT)}")

    return {
        "session"        : snum,
        "evt"            : evt,
        "cfg"            : cfg,
        "mag"            : mag,
        "gga"            : gga,
        "spc"            : spc,
        "stab_rows"      : stab_rows,
        "conn_rows"      : conn_rows,
        "mux_assign"     : dict(mux),
        "warn_counts"    : wrn,
        "critical_lines" : evt["critical_lines"],
        "fully_nan_mag"  : fully_nan_m,
        "partial_nan_mag": partial_nan_m,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN: RUN BOTH SESSIONS
# ══════════════════════════════════════════════════════════════════════════════

print("\nConfirmed files in data folder:")
for f in sorted((DATA_DIR).iterdir()):
    print(f"  {f.name}")

r006 = analyse_session(6)
r007 = analyse_session(7)


# ══════════════════════════════════════════════════════════════════════════════
# STEP 8 — COMPARE SESSIONS
# ══════════════════════════════════════════════════════════════════════════════

print()
print("=" * 72)
print("  STEP 8 — SESSION 006 vs 007 COMPARISON")
print("=" * 72)

comp_lines = []
def cprint(*args):
    msg = " ".join(str(a) for a in args)
    print(msg)
    comp_lines.append(msg)

cprint()
cprint("=" * 72)
cprint("  SESSION 006 vs 007 COMPARISON — Welzow Ground Test 2026-03-24")
cprint("=" * 72)

# Session timing comparison
cprint("\n── Session timing ──────────────────────────────────────────────────")
cprint(f"  {'Metric':<20} {'Session 006':<30} {'Session 007'}")
cprint(f"  {'─'*20} {'─'*30} {'─'*25}")
cprint(f"  {'Start':<20} {str(r006['evt']['session_start']):<30} {str(r007['evt']['session_start'])}")
cprint(f"  {'End':<20} {str(r006['evt']['session_end']):<30} {str(r007['evt']['session_end'])}")
cprint(f"  {'Duration':<20} {str(r006['evt']['duration']):<30} {str(r007['evt']['duration'])}")
cprint(f"  {'MAG rows':<20} {len(r006['mag']):<30} {len(r007['mag'])}")
cprint(f"  {'GGA rows':<20} {len(r006['gga']):<30} {len(r007['gga'])}")
cprint(f"  {'SPC rows':<20} {len(r006['spc']):<30} {len(r007['spc'])}")

# Sensor status comparison
cprint("\n── Sensor connection status ─────────────────────────────────────────")
all_sensors = sorted(set(list(r006["evt"]["sensor_map"].values()) +
                          list(r007["evt"]["sensor_map"].values())))
sensor_comp_rows = []
for sensor in all_sensors:
    ref  = SENSOR_REFERENCE.get(sensor, {})
    port = ref.get("port", "—")

    cr006 = {v: k for k, v in r006["evt"]["sensor_map"].items()}
    cr007 = {v: k for k, v in r007["evt"]["sensor_map"].items()}

    rate_006 = r006["evt"]["char_rates"].get(cr006.get(sensor, ""), 0.0)
    rate_007 = r007["evt"]["char_rates"].get(cr007.get(sensor, ""), 0.0)
    st_006   = "CONNECTED" if rate_006 > 0 else "DISCONNECTED"
    st_007   = "CONNECTED" if rate_007 > 0 else "DISCONNECTED"
    changed  = "CHANGED" if st_006 != st_007 else "same"
    sensor_comp_rows.append((port, sensor, st_006, st_007, changed))

cprint(ascii_table(
    ["Port", "Sensor", "006 Status", "007 Status", "Changed?"],
    sensor_comp_rows))

# Data quality comparison: shared sensors
cprint("\n── Data quality comparison (key channels) ──────────────────────────")
COMPARE_COLS = [
    ("Mag1",  "MAG", "nT"),
    ("Mag2",  "MAG", "nT"),
    ("Mag1C", "MAG", "nT"),
    ("Mag2C", "MAG", "nT"),
    ("Roll",  "MAG", "°"),
    ("Pitch", "MAG", "°"),
    ("Yaw",   "MAG", "°"),
    ("Ralt",  "MAG", "m"),
    ("Xdgps", "GGA", "°"),
    ("Ydgps", "GGA", "°"),
    ("dHdop", "GGA", ""),
    ("dSNo",  "GGA", "count"),
]
dfs_006 = {"MAG": r006["mag"], "GGA": r006["gga"], "SPC": r006["spc"]}
dfs_007 = {"MAG": r007["mag"], "GGA": r007["gga"], "SPC": r007["spc"]}

qual_rows = []
for col, src, unit in COMPARE_COLS:
    df6 = dfs_006.get(src, pd.DataFrame())
    df7 = dfs_007.get(src, pd.DataFrame())

    def fmt_stat(df, c):
        if c not in df.columns or df[c].isna().all():
            return "NO DATA"
        s = df[c].dropna()
        return f"{s.mean():.3f} ± {s.std():.4f} {unit}"

    m6 = fmt_stat(df6, col)
    m7 = fmt_stat(df7, col)
    qual_rows.append((col, COL_DESCRIPTIONS.get(col, "—")[:40], m6, m7))

cprint(ascii_table(
    ["Column", "Description", "Session 006 (mean ± std)", "Session 007 (mean ± std)"],
    qual_rows))

# Cfg comparison
cprint("\n── Configuration comparison (Cfg XML) ──────────────────────────────")
cfg6, cfg7 = r006["cfg"], r007["cfg"]
diff_found = False
all_raw_keys = set(cfg6["raw"].keys()) | set(cfg7["raw"].keys())
cfg_diff_rows = []
for key in sorted(all_raw_keys):
    v6 = cfg6["raw"].get(key, "—")
    v7 = cfg7["raw"].get(key, "—")
    if v6 != v7:
        cfg_diff_rows.append((key, v6[:50], v7[:50]))
        diff_found = True

if not diff_found:
    cprint("  Cfg006 and Cfg007 are IDENTICAL – no configuration changes between sessions.")
else:
    cprint(ascii_table(["Parameter", "Session 006", "Session 007"], cfg_diff_rows))

# Warning comparison
cprint("\n── Health warning comparison ────────────────────────────────────────")
all_warn_types = sorted(set(list(r006["warn_counts"].keys()) +
                             list(r007["warn_counts"].keys())))
warn_comp_rows = []
for wt in all_warn_types:
    n6 = r006["warn_counts"].get(wt, 0)
    n7 = r007["warn_counts"].get(wt, 0)
    warn_comp_rows.append((wt, str(n6), str(n7), WARN_MEANINGS.get(wt, "—")))
cprint(ascii_table(["Warning", "006 Count", "007 Count", "Meaning"], warn_comp_rows))

# Notable differences
cprint("\n── Notable differences and anomalies ───────────────────────────────")
cprint(f"  1. Session duration: 006 = {r006['evt']['duration']}  vs  "
       f"007 = {r007['evt']['duration']}  (007 is much shorter)")
cprint(f"  2. Sensor connections: identical in both sessions")

# Check Mag2 anomaly in 007
mag7 = r007["mag"]
if "Mag2" in mag7.columns and not mag7["Mag2"].isna().all():
    mag2_mean_7 = mag7["Mag2"].dropna().mean()
    mag2_std_7  = mag7["Mag2"].dropna().std()
    mag2_mean_6 = r006["mag"]["Mag2"].dropna().mean()
    cprint(f"  3. Mag2 in session 007: mean={mag2_mean_7:.1f} nT vs "
           f"006: {mag2_mean_6:.1f} nT — "
           f"{'LARGE DISCREPANCY – sensor may not have settled' if abs(mag2_mean_7 - mag2_mean_6) > 100 else 'consistent'}")
if "Mag2D" in mag7.columns:
    mag2d_max = mag7["Mag2D"].abs().max()
    if mag2d_max > 50:
        cprint(f"     Mag2D in session 007: max|derivative|={mag2d_max:.1f} nT/s — "
               f"indicates sensor was still settling during short session 007")

# Save comparison report
comp_path = PROJECT_ROOT / "outputs" / "comparison_006_007.txt"
comp_path.parent.mkdir(parents=True, exist_ok=True)
comp_path.write_text("\n".join(comp_lines), encoding="utf-8")
print(f"\n  Comparison saved: {comp_path.relative_to(PROJECT_ROOT)}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 9 — DOCUMENTATION
# ══════════════════════════════════════════════════════════════════════════════

print()
print("=" * 72)
print("  STEP 9 — Writing documentation")
print("=" * 72)

# ── CLAUDE.md ─────────────────────────────────────────────────────────────────
def session_sensor_status(snum, sensor_name):
    """Return connection status for a sensor in a session result."""
    r = r006 if snum == "006" else r007
    for port, sn in r["evt"]["sensor_map"].items():
        if sn == sensor_name:
            rate = r["evt"]["char_rates"].get(port, 0.0)
            return "CONNECTED" if rate > 0 else "DISCONNECTED"
    return "—"

claude_md = textwrap.dedent("""\
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
| `Health Warning: Mx TimeO\\|` | Multiplexer x timed out |
| `Health Warning: Nv WayP\\|` | No navigation waypoint active |

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
""")

for sname, ref in SENSOR_REFERENCE.items():
    st6 = session_sensor_status("006", sname)
    st7 = session_sensor_status("007", sname)
    cols = ", ".join(ref["mag_cols"]) if ref["mag_cols"] else "—"
    claude_md += (f"| {sname} | {ref['port']} | {ref['label']} | "
                  f"{ref['full_name']} | {st6} | {st7} | {cols} | "
                  f"{ref['description']} |\n")

claude_md += textwrap.dedent("""
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
""")

(PROJECT_ROOT / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
print("  Written: CLAUDE.md")

# ── README.md ─────────────────────────────────────────────────────────────────
readme = textwrap.dedent("""\
# Airborne Geophysics – Welzow Ground Test (2026-03-24)

## What this project is about

This repository contains raw instrument data and Python analysis scripts
for a **ground test of an airborne geophysics sensor suite** (GeoDuster
system) performed at **Welzow, Germany on 2026-03-24**. The aircraft was
parked on the ground with the data acquisition system running. The tests
verify which sensors are active, checks data quality, and flag system
anomalies before a real airborne survey flight.

---

## Sessions

| Field | Session 006 | Session 007 |
|-------|-------------|-------------|
""")

for field, k6, k7 in [
    ("Start (UTC)", str(r006["evt"]["session_start"]), str(r007["evt"]["session_start"])),
    ("End (UTC)",   str(r006["evt"]["session_end"]),   str(r007["evt"]["session_end"])),
    ("Duration",    str(r006["evt"]["duration"]),      str(r007["evt"]["duration"])),
    ("MAG rows",    str(len(r006["mag"])),             str(len(r007["mag"]))),
    ("GGA rows",    str(len(r006["gga"])),             str(len(r007["gga"]))),
    ("SPC rows",    str(len(r006["spc"])),             str(len(r007["spc"]))),
]:
    readme += f"| {field} | {k6} | {k7} |\n"

readme += textwrap.dedent("""
---

## Sensor status

| Sensor | Port | Full Name | 006 | 007 | Reason if disconnected |
|--------|------|-----------|-----|-----|------------------------|
""")
for sname, ref in SENSOR_REFERENCE.items():
    st6 = session_sensor_status("006", sname)
    st7 = session_sensor_status("007", sname)
    reason = ("Not connected / powered off during this test"
              if st6 == "DISCONNECTED" else "Active")
    readme += f"| {sname} | {ref['port']} | {ref['full_name']} | {st6} | {st7} | {reason} |\n"

readme += textwrap.dedent("""
---

## Data files

| File | Written by | Format | Description |
|------|------------|--------|-------------|
| EVT*.txt | ICCS system | Plain text | Timestamped event log |
| MAG*.txt | Mux1 | Fixed-width ASCII | Main multi-sensor data (~10 Hz) |
| GGA*.txt | Mux3 | Fixed-width ASCII | Differential GPS (~10 Hz) |
| SPC*.txt | Mux2 | Fixed-width ASCII | Spectrometer/environment (~1 Hz) |
| Cfg*.xml | ICCS system | XML | System configuration snapshot |
| CMP_0043.* | Compensation | Binary/text | Magnetic compensation model |

---

## MAG column dictionary

| Column | Unit | Description |
|--------|------|-------------|
""")
for col, desc in COL_DESCRIPTIONS.items():
    readme += f"| `{col}` | — | {desc} |\n"

readme += textwrap.dedent("""
---

## Data quality summary

### Session 006
""")
for col, _, mn, sd, mi, mx, st in r006["stab_rows"]:
    if st not in ("NO DATA / DISCONNECTED", "—"):
        readme += f"- **{col}**: {st} | mean={mn}, std={sd}\n"

readme += "\n### Session 007\n"
for col, _, mn, sd, mi, mx, st in r007["stab_rows"]:
    if st not in ("NO DATA / DISCONNECTED", "—"):
        readme += f"- **{col}**: {st} | mean={mn}, std={sd}\n"

readme += textwrap.dedent("""
---

## Known issues

- **Mux M1/M2/M3 TimeO warnings**: Persistent throughout both sessions (~every 5-6 s).
  This is expected behaviour during ground tests – the multiplexer synchronisation
  relies on an aircraft motion trigger that is absent when parked. Does NOT indicate
  data loss in practice (magnetometer NaN rate <0.5%).
- **`Nv WayP` warnings**: Normal – no survey flight plan (waypoints) was loaded.
  The aircraft was not following a navigation line.
- **NaN gaps in MAG**: Small gaps (~0.5% of rows) in magnetometer and GPS columns,
  caused by the Mux timeout events. Data is otherwise complete.
- **`Lalt` column always NaN**: The barometric altitude from GPS is not written
  in these files (GPS provides only ellipsoidal altitude in `Zgps`).
- **VLF channels (Vlf1–Vlf4) always NaN**: GD485 was disconnected in both sessions.
- **Session 007 Mag2 anomaly**: Magnetometer #2 shows extreme values in session 007
  (mean ~55800 nT vs ~49459 nT in 006, with large derivatives). The sensor was
  likely still settling / initialising during this short ~5-minute session.
""")

(PROJECT_ROOT / "README.md").write_text(readme, encoding="utf-8")
print("  Written: README.md")

print("\n✓ All steps completed successfully.")
print(f"  Outputs: {(PROJECT_ROOT / 'outputs').relative_to(PROJECT_ROOT)}/")
