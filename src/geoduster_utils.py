"""
geoduster_utils.py
Shared parsers, constants, and analysis functions for GeoDuster airborne data.
Imported by step1_status.py and step2_compare.py.
"""

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════

SENSOR_REFERENCE = {
    "GEMK1" : {
        "port": "COM3", "label": "P3",
        "full_name": "Magnetometer #1 (Port side)",
        "description": "GEM Systems KING-AIR towed fluxgate magnetometer – total field",
        "mag_cols": ["Mag1", "Mag1D", "Mag1C", "A1", "T1", "X1", "Y1", "Z1"],
    },
    "GEMK2" : {
        "port": "COM4", "label": "P4",
        "full_name": "Magnetometer #2 (Starboard side)",
        "description": "GEM Systems KING-AIR towed fluxgate magnetometer – total field",
        "mag_cols": ["Mag2", "Mag2D", "Mag2C", "A2", "T2", "X2", "Y2", "Z2"],
    },
    "GDRAlt": {
        "port": "COM5", "label": "P5",
        "full_name": "Radar Altimeter",
        "description": "Measures height above ground (AGL) in metres",
        "mag_cols": ["Ralt", "Raltr"],
    },
    "GD485" : {
        "port": "COM6", "label": "P6",
        "full_name": "ADC 4-channel VLF receiver (RS-485 bus)",
        "description": "Analogue-to-digital converter for VLF EM channels",
        "mag_cols": ["MagL", "MagLC", "Vlf1", "Vlf2", "Vlf3", "Vlf4"],
    },
    "XSENS" : {
        "port": "COM7", "label": "P7",
        "full_name": "AHRS / GPS attitude sensor",
        "description": "XSENS MTi inertial measurement unit – Roll, Pitch, Yaw",
        "mag_cols": ["Roll", "Pitch", "Yaw"],
    },
    "GDGPS" : {
        "port": "COM8", "label": "P8",
        "full_name": "Septentrio differential GPS",
        "description": "High-precision GNSS receiver – position and altitude",
        "mag_cols": ["Xgps", "Ygps", "Zgps", "Lalt"],
    },
    "GDSpec": {
        "port": "COM9", "label": "P9",
        "full_name": "Medusa Gamma-Ray Spectrometer",
        "description": "Gamma-ray spectrometer with environmental sensors",
        "mag_cols": ["Vlf1", "Vlf2", "Vlf3", "Vlf4"],
    },
    "GDLas" : {
        "port": "COM10", "label": "P10",
        "full_name": "Laser Altimeter",
        "description": "Laser rangefinder for precise terrain clearance",
        "mag_cols": [],
    },
}

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

# Stability thresholds for ground-test checks (unit, max acceptable std)
STABILITY_THRESHOLDS = {
    "Mag1"  : ("nT",  10.0), "Mag2"  : ("nT",  10.0),
    "Mag1C" : ("nT",  10.0), "Mag2C" : ("nT",  10.0),
    "Roll"  : ("°",    1.0), "Pitch" : ("°",    1.0), "Yaw"  : ("°",   2.0),
    "Ralt"  : ("m",    0.5), "Raltr" : ("m",    0.5),
    "Xgps"  : ("°", 0.001),  "Ygps"  : ("°",  0.001),
    "Xdgps" : ("°",  5e-5),  "Ydgps" : ("°",   5e-5),
    "dHdop" : ("",    1.0),
}

WARN_MEANINGS = {
    "M1 TimeO" : "Mux1 timeout – sensor not responding within 80 ms",
    "M2 TimeO" : "Mux2 timeout – sensor not responding within 200 ms",
    "M3 TimeO" : "Mux3 timeout – sensor not responding within 100 ms",
    "Nv WayP"  : "Navigation waypoint missing (normal on ground – no flight plan active)",
}

# Sensor → expected MAG columns (for cross-check EVT vs data)
SENSOR_MAG_COLS = {
    "GEMK1"  : ["Mag1", "Mag1D", "Mag1C"],
    "GEMK2"  : ["Mag2", "Mag2D", "Mag2C"],
    "GDRAlt" : ["Ralt", "Raltr"],
    "GD485"  : ["MagL", "MagLC"],
    "XSENS"  : ["Roll", "Pitch", "Yaw"],
    "GDGPS"  : ["Xgps", "Ygps", "Zgps", "Lalt"],
    "GDSpec" : ["Vlf1", "Vlf2", "Vlf3", "Vlf4"],
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def ascii_table(headers, rows):
    """Return a plain ASCII table string with auto-sized columns."""
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


def find_sessions(data_dir):
    """Return sorted list of session numbers found as EVT*.txt in data_dir."""
    sessions = []
    for p in sorted(data_dir.glob("EVT*.txt")):
        m = re.match(r"EVT(\d+)\.txt", p.name)
        if m:
            sessions.append(int(m.group(1)))
    return sessions


# ══════════════════════════════════════════════════════════════════════════════
# FILE PARSERS
# ══════════════════════════════════════════════════════════════════════════════

def parse_fwf(filepath):
    """
    Parse a GeoDuster fixed-width file (MAG, GGA, SPC).
    Column right boundaries align with the right edge of each header token
    (m.end() positions). '#'-only cells → NaN. Numeric conversion applied.
    """
    with open(filepath, encoding="utf-8", errors="replace") as fh:
        header_raw = fh.readline()

    tokens    = list(re.finditer(r"\S+", header_raw))
    col_names = [t.group() for t in tokens]
    col_ends  = [t.end()   for t in tokens]

    colspecs = [(0, col_ends[0])]
    for i in range(1, len(col_ends)):
        end = col_ends[i] if i < len(col_ends) - 1 else None
        colspecs.append((col_ends[i - 1], end))

    df = pd.read_fwf(filepath, colspecs=colspecs, names=col_names,
                     skiprows=1, dtype=str)

    hash_re = re.compile(r"^#+$")
    for col in df.columns:
        df[col] = df[col].apply(
            lambda v: np.nan if isinstance(v, str) and hash_re.fullmatch(v.strip()) else v
        )

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
    """Return (mean, std, min, max, status) tuple for one column."""
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


def make_plot(df, columns, title, filename, out_dir, y_label="Value", label=""):
    """
    Plot columns vs time_sec. NaN gaps appear as natural line breaks.
    Grey shading marks NaN spans. Mean ± std shown in subtitle.
    """
    valid_cols = [c for c in columns if c in df.columns and not df[c].isna().all()]
    if not valid_cols:
        return None

    x = df["time_sec"]
    fig, ax = plt.subplots(figsize=(12, 4))

    for col in valid_cols:
        ax.plot(x, df[col], lw=0.9, label=col)

    # Grey shading for NaN gaps (union of all plotted columns)
    union_nan = df[valid_cols].isna().any(axis=1)
    in_gap, gap_drawn, t0_gap = False, False, None
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

    # Subtitle: mean ± std per channel
    stat_parts = []
    for col in valid_cols:
        s = df[col].dropna()
        if not s.empty:
            stat_parts.append(f"{col}: μ={s.mean():.3f} ± σ={s.std():.4f}")

    tag = f"[{label}]  " if label else ""
    ax.set_title(f"{tag}{title}", fontsize=11, fontweight="bold")
    ax.set_xlabel("Elapsed time (s from session start)")
    ax.set_ylabel(y_label)
    if stat_parts:
        fig.text(0.5, 0.01, "   |   ".join(stat_parts),
                 ha="center", fontsize=7, color="#555555")

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
    return fpath


def parse_evt(filepath):
    """
    Parse a GeoDuster EVT event log.
    Returns a dict: sensor_map, char_rates, mux_assignments, warning_counts,
    critical_lines, file_opens, session_start, session_end, duration,
    connected, disconnected.
    """
    lines = Path(filepath).read_text(encoding="utf-8", errors="replace").splitlines()

    # Parse survey date from EVT header (avoids any hardcoded date)
    survey_date = None
    if lines:
        hm0 = re.search(r"Date:(\d{8})", lines[0])
        if hm0:
            d = hm0.group(1)
            survey_date = (int(d[:4]), int(d[4:6]), int(d[6:]))

    sensor_map      = {}
    char_rates      = {}
    mux_assignments = defaultdict(list)
    warning_counts  = defaultdict(int)
    critical_lines  = []
    file_opens      = []
    timestamps      = []

    for line in lines:
        ts_m = re.match(r"(\d{2}:\d{2}:\d{2}\.\d):", line)

        m = re.search(r"COM(\d+): Macro (\w+) OK", line)
        if m:
            sensor_map[f"COM{m.group(1)}"] = m.group(2)

        m = re.search(r"Character Rate on (COM\d+) is ([\d.]+) chars/second", line)
        if m:
            char_rates[m.group(1)] = float(m.group(2))

        m = re.search(r"(M\d) latches port (COM\d+) runs macro (\w+)", line)
        if m:
            mux_assignments[m.group(1)].append((m.group(2), m.group(3)))

        m = re.search(r"Health Warning: (.+?)\|", line)
        if m:
            warning_counts[m.group(1).strip()] += 1

        if "!!!!" in line:
            ts = ts_m.group(1) if ts_m else "??"
            critical_lines.append((ts, line.strip()))

        m2 = re.search(r"File: (.+?) opened", line)
        if m2:
            ts = ts_m.group(1) if ts_m else "??"
            file_opens.append((ts, m2.group(1).strip()))

        if ts_m and survey_date:
            try:
                parts = ts_m.group(1).split(":")
                h, mn_s = int(parts[0]), int(parts[1])
                s_str, ds_str = parts[2].split(".")
                timestamps.append(
                    datetime(*survey_date, h, mn_s, int(s_str), int(ds_str) * 100_000))
            except (ValueError, IndexError):
                pass

    # Session start from EVT header; fallback to first timestamp
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

    connected    = {p: s for p, s in sensor_map.items() if char_rates.get(p, 0.0) > 0}
    disconnected = {p: s for p, s in sensor_map.items() if char_rates.get(p, 0.0) == 0.0}

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


def parse_cfg(filepath):
    """
    Extract key configuration parameters from a GeoDuster Cfg XML file.
    Returns a dict with compensation, nav_file, port_data (per-COM settings), raw.
    """
    tree = ET.parse(filepath)
    root = tree.getroot()

    raw = {}
    for obj in root.iter("Object"):
        tag = obj.get("Tag", "")
        val_el = obj.find("Value")
        if val_el is not None and tag:
            raw[tag] = (val_el.text or "").strip()

    port_data = {}
    for obj in root.iter("Object"):
        tag = obj.get("Tag", "")
        m = re.match(r"COM(\d+)STATE", tag)
        if m:
            com = f"COM{m.group(1)}"
            state = raw.get(tag, "—")
            baud, macro = "?", "?"
            for child in obj:
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

def analyse_session(data_dir, session_num, out_root, plots=True):
    """
    Full status analysis for one GeoDuster session.

    Parameters
    ----------
    data_dir    : Path – folder containing EVT/MAG/GGA/SPC/Cfg files
    session_num : int  – session number, e.g. 6 or 7
    out_root    : Path – root outputs folder; session subdir created here
    plots       : bool – generate PNG plots (default True)

    Returns
    -------
    dict with parsed data and summary statistics for further use (e.g. comparison)
    """
    sid  = str(session_num).zfill(5)   # "00006"
    snum = str(session_num).zfill(3)   # "006"
    out  = out_root / f"session_{snum}"
    out.mkdir(parents=True, exist_ok=True)

    report_lines = []
    def rprint(*args, **kwargs):
        msg = " ".join(str(a) for a in args)
        report_lines.append(msg)

    rprint()
    rprint("=" * 72)
    rprint(f"  SESSION {snum}  –  {data_dir.name}")
    rprint("=" * 72)

    # ── STEP 1: EVT ───────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 1 — EVT{sid}.txt")
    rprint(f"{'─'*72}")

    evt = parse_evt(data_dir / f"EVT{sid}.txt")
    sm  = evt["sensor_map"]
    cr  = evt["char_rates"]
    mux = evt["mux_assignments"]
    wrn = evt["warning_counts"]

    rprint("\na) Sensor-port mapping:")
    for port, name in sorted(sm.items(), key=lambda x: int(x[0][3:])):
        rprint(f"   {port} → {name}")

    rprint("\nb) Connection status:")
    conn_rows = []
    for port in sorted(cr.keys(), key=lambda x: int(x[3:])):
        rate   = cr[port]
        sensor = sm.get(port, "?")
        fname  = SENSOR_REFERENCE.get(sensor, {}).get("full_name", "—")
        status = "CONNECTED" if rate > 0 else "DISCONNECTED"
        conn_rows.append((port, sensor, fname, f"{rate:.1f}", status))
    rprint(ascii_table(["COM", "Sensor", "Full Name", "Rate (chars/s)", "Status"],
                       conn_rows))

    rprint("\nc) Mux assignments:")
    mux_rows = [(mx, port, sensor)
                for mx in sorted(mux.keys())
                for port, sensor in mux[mx]]
    rprint(ascii_table(["Mux", "COM Port", "Sensor"], mux_rows) if mux_rows
           else "   None found.")

    rprint("\nd) Health warnings:")
    warn_rows = [(w, str(c), WARN_MEANINGS.get(w, "Unknown"))
                 for w, c in sorted(wrn.items(), key=lambda x: -x[1])]
    rprint(ascii_table(["Warning", "Count", "Meaning"], warn_rows) if warn_rows
           else "   None.")

    rprint("\ne) Critical errors (lines with '!!!!'):")
    if evt["critical_lines"]:
        for ts, ln in evt["critical_lines"]:
            rprint(f"   [{ts}] {ln}")
    else:
        rprint("   None found.")

    rprint("\nf) Data files opened:")
    for ts, f in evt["file_opens"]:
        rprint(f"   [{ts}] {f}")

    rprint(f"\ng) Session timing:")
    rprint(f"   Start   : {evt['session_start']}")
    rprint(f"   End     : {evt['session_end']}")
    rprint(f"   Duration: {evt['duration']}")

    rprint(f"\nh) Cfg{sid}.xml configuration summary:")
    cfg = parse_cfg(data_dir / f"Cfg{sid}.xml")
    rprint(f"   Compensation file : {cfg['compensation']}")
    rprint(f"   Navigation file   : {cfg['nav_file']}")
    rprint(f"   Clock port        : {cfg['clock_port']}")
    rprint(f"   Web host          : {cfg['web_host']}")
    rprint(f"   Survey line num   : {cfg['line_num']}")
    rprint(f"   Log level         : {cfg['log_level']}")
    rprint("\n   Port configuration (from XML):")
    cfg_port_rows = [
        (com, pd_["state"], pd_["baud"], pd_["macro"])
        for com, pd_ in sorted(cfg["port_data"].items(), key=lambda x: int(x[0][3:]))
    ]
    rprint(ascii_table(["COM", "State", "Baud", "Macro"], cfg_port_rows))

    # ── STEP 2: MAG ───────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 2 — MAG{sid}.txt")
    rprint(f"{'─'*72}")

    mag = parse_fwf(data_dir / f"MAG{sid}.txt")
    mag = add_time_axis(mag, "Time")

    MAG_SKIP = {"time_sec", "Date", "Time", "M1st", "M1clk", "Xpr", "Wayp", "Xst", "Bin"}
    fully_nan_m, partial_nan_m, clean_m = classify_columns(mag, skip_cols=MAG_SKIP)

    rprint(f"\n  Rows: {len(mag)}   Columns: {len(mag.columns)}")
    rprint(f"  Fully NaN   : {fully_nan_m or 'None'}")
    rprint(f"  Partial NaN : {partial_nan_m or 'None'}")
    rprint(f"  Clean       : {clean_m or 'None'}")

    # ── STEP 3: GGA ───────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 3 — GGA{sid}.txt")
    rprint(f"{'─'*72}")

    gga = parse_fwf(data_dir / f"GGA{sid}.txt")
    gga = add_time_axis(gga, "dTime")

    GGA_SKIP = {"time_sec", "M3st", "M3clk", "dWayp", "dTime"}
    fully_nan_g, partial_nan_g, clean_g = classify_columns(gga, skip_cols=GGA_SKIP)

    rprint(f"\n  Rows: {len(gga)}   Columns: {len(gga.columns)}")
    rprint(f"  Fully NaN   : {fully_nan_g or 'None'}")
    rprint(f"  Partial NaN : {partial_nan_g or 'None'}")
    rprint(f"  Clean       : {clean_g or 'None'}")

    if "dHdop" in gga.columns and not gga["dHdop"].isna().all():
        rprint(f"\n  GPS quality (mean ± std):")
        for col, desc in [("dSNo",  "Satellites"),
                           ("dHdop", "HDOP"),
                           ("dAge",  "Diff age (s)")]:
            if col in gga.columns and not gga[col].isna().all():
                s = gga[col].dropna()
                note = ""
                if col == "dHdop":
                    note = "  [EXCELLENT]" if s.mean() < 1.0 else "  [GOOD]"
                rprint(f"    {desc:<18}: {s.mean():.3f} ± {s.std():.4f}{note}")
        for col in ["Xdgps", "Ydgps"]:
            if col in gga.columns and not gga[col].isna().all():
                rprint(f"    {col} σ           : {gga[col].std():.6f}°")

    # ── STEP 4: SPC ───────────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 4 — SPC{sid}.txt")
    rprint(f"{'─'*72}")

    spc = parse_fwf(data_dir / f"SPC{sid}.txt")
    spc = add_time_axis(spc, "Stime")

    SPC_SKIP = {"time_sec", "M2st", "M2clk", "Sdate", "Stime", "Swayp", "Sbin"}
    fully_nan_s, partial_nan_s, clean_s = classify_columns(spc, skip_cols=SPC_SKIP)

    rprint(f"\n  Rows: {len(spc)}   Columns: {len(spc.columns)}")

    gdspec_port   = SENSOR_REFERENCE.get("GDSpec", {}).get("port", "COM9")
    gdspec_status = "CONNECTED" if cr.get(gdspec_port, 0) > 0 else "DISCONNECTED"
    rprint(f"  GDSpec ({gdspec_port}): {gdspec_status}")

    for col in ["Sralt", "BaroV", "TempV", "HumdV", "Sk", "Su", "Sth",
                "Sbaro", "Stemp", "Shumd"]:
        if col in spc.columns and not spc[col].isna().all():
            s = spc[col].dropna()
            note = "  [CONSTANT]" if s.std() < 0.001 else ""
            rprint(f"  {col:8s}: mean={s.mean():.3f}  std={s.std():.4f}"
                   f"  ({COL_DESCRIPTIONS.get(col, '')}){note}")

    rprint(f"  Fully NaN   : {fully_nan_s or 'None'}")
    rprint(f"  Partial NaN : {partial_nan_s or 'None'}")
    rprint(f"  Clean       : {clean_s or 'None'}")

    # ── STEP 5: PLOTS ─────────────────────────────────────────────────────────
    if plots:
        rprint(f"\n{'─'*72}")
        rprint(f"STEP 5 — Plots  →  {out.relative_to(PROJECT_ROOT)}/")
        rprint(f"{'─'*72}")

        make_plot(mag, ["Mag1", "Mag2"],
                  "Magnetometers (raw)", "plot_01_mag_raw.png",
                  out, "nT", snum)
        make_plot(mag, ["Mag1C", "Mag2C"],
                  "Magnetometers (compensated)", "plot_02_mag_compensated.png",
                  out, "nT", snum)
        make_plot(mag, ["Mag1D", "Mag2D"],
                  "Magnetometer first derivatives", "plot_03_mag_derivatives.png",
                  out, "nT/s", snum)
        make_plot(mag, ["Roll", "Pitch", "Yaw"],
                  "Attitude – XSENS AHRS", "plot_04_attitude.png",
                  out, "degrees", snum)
        make_plot(mag, ["Ralt"],
                  "Radar Altimeter", "plot_05_radar_alt.png",
                  out, "m AGL", snum)
        make_plot(gga, ["Xdgps", "Ydgps"],
                  "Differential GPS position", "plot_06_dgps_position.png",
                  out, "degrees", snum)
        make_plot(gga, ["dHdop", "dSNo"],
                  "GPS quality indicators", "plot_07_gps_quality.png",
                  out, "HDOP / #sat", snum)

        spc_cols = [c for c in ["Sk", "Su", "Sth", "BaroV", "Sbaro"]
                    if c in spc.columns and not spc[c].isna().all()]
        if spc_cols:
            make_plot(spc, spc_cols,
                      "Spectrometer channels", "plot_08_spc_channels.png",
                      out, "counts", snum)
        else:
            rprint(f"  SKIP [{snum}] Spectrometer – all NaN")

    # ── STEP 6: STABILITY ─────────────────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 6 — Stability analysis")
    rprint(f"{'─'*72}")

    analysis_cols = {
        **{c: "MAG" for c in ["Mag1", "Mag2", "Mag1C", "Mag2C",
                               "Mag1D", "Mag2D", "MagL", "MagLC",
                               "Roll", "Pitch", "Yaw", "Ralt", "Raltr",
                               "Xgps", "Ygps", "Zgps"]},
        **{c: "GGA" for c in ["Xdgps", "Ydgps", "Zdgps", "dSNo", "dHdop", "dAge"]},
        **{c: "SPC" for c in ["BaroV", "Sralt", "Sk", "Su", "Sth",
                               "Sbaro", "Stemp", "Shumd"]},
    }
    src_dfs = {"MAG": mag, "GGA": gga, "SPC": spc}

    stab_rows = []
    for col, src in analysis_cols.items():
        df_src = src_dfs[src]
        if col not in df_src.columns or df_src[col].isna().all():
            stab_rows.append((col, COL_DESCRIPTIONS.get(col, "—"),
                               "—", "—", "—", "—", "NO DATA / DISCONNECTED"))
            continue
        mn, sd, mi, mx, st = stability_row(col, df_src)
        stab_rows.append((col, COL_DESCRIPTIONS.get(col, "—"), mn, sd, mi, mx, st))

    rprint(ascii_table(
        ["Variable", "Description", "Mean", "Std", "Min", "Max", "Status"],
        stab_rows))

    # ── STEP 7: CROSS-CHECK EVT vs MAG ────────────────────────────────────────
    rprint(f"\n{'─'*72}")
    rprint(f"STEP 7 — Cross-check EVT vs data files")
    rprint(f"{'─'*72}")

    xcheck_rows = []
    mismatches  = []
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
                col_stats.append(f"{mc}:PARTIAL({100*n/len(mag):.1f}%)")
            else:
                col_stats.append(f"{mc}:OK")

        match = "OK"
        if evt_status == "DISCONNECTED":
            if any("OK" in s and "ALL_NaN" not in s and "PARTIAL" not in s
                   for s in col_stats):
                match = "MISMATCH"
                mismatches.append(f"{sensor} EVT=DISCONNECTED but MAG has data")
        elif evt_status == "CONNECTED":
            if col_stats and all("ALL_NaN" in s or "ABSENT" in s for s in col_stats):
                match = "MISMATCH"
                mismatches.append(f"{sensor} EVT=CONNECTED but MAG all NaN")

        xcheck_rows.append((port, sensor, evt_status,
                            "; ".join(col_stats) if col_stats else "—", match))

    rprint(ascii_table(["COM", "Sensor", "EVT Status", "MAG column NaN", "Match"],
                       xcheck_rows))

    if mismatches:
        rprint("\n  MISMATCHES:")
        for m in mismatches:
            rprint(f"  !! {m}")
    else:
        rprint("\n  All sensor statuses consistent between EVT and MAG. ✓")

    total_warn = sum(wrn.values())
    rprint(f"\n  Total health warnings: {total_warn}")
    for col in ["Mag1", "Mag2"]:
        if col in mag.columns:
            n = mag[col].isna().sum()
            rprint(f"  {col}: {n}/{len(mag)} NaN rows ({100*n/len(mag):.1f}%)"
                   + (" – gaps may correlate with Mux TimeO events" if n > 0
                      else " – no gaps"))

    # Save text report
    report_path = out / f"report_{snum}.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    # ── COMPACT TERMINAL SUMMARY ──────────────────────────────────────────────
    print()
    print("-" * 72)
    _date_str = evt["session_start"].strftime("%Y-%m-%d") if evt["session_start"] else "-"
    _dur_str  = str(evt["duration"]).split(".")[0] if evt["duration"] else "-"
    print(f"  SESSION {snum}  |  {_date_str}  |  Duration: {_dur_str}")
    print(f"  MAG: {len(mag)} rows   GGA: {len(gga)} rows   SPC: {len(spc)} rows")

    # a) Sensor status table
    _sensor_rows = []
    for _sensor, _info in SENSOR_REFERENCE.items():
        _port = _info["port"]
        _full = _info["full_name"]
        _rate = evt["char_rates"].get(_port, 0.0)
        if _rate == 0.0:
            _st = "DISCONNECTED"
        else:
            _cols = SENSOR_MAG_COLS.get(_sensor, [])
            _has  = any(c in mag.columns and not mag[c].isna().all() for c in _cols)
            if not _has and _sensor == "GDSpec":
                _has = any(c in spc.columns and not spc[c].isna().all()
                           for c in ["Sk", "Su", "Sth"])
            if not _cols and _sensor != "GDSpec":
                _has = True  # GDLas: no data columns to verify - trust EVT rate
            _st = "OK  connected" if _has else "NO DATA"
        _sensor_rows.append((_sensor, _full, _st))
    print()
    print(ascii_table(["Sensor", "Full Name", "Status"], _sensor_rows))

    # b) Data quality table
    _TERM_VARS = [
        ("Mag1",  mag), ("Mag2",  mag), ("Mag1C", mag), ("Mag2C", mag),
        ("Roll",  mag), ("Pitch", mag), ("Yaw",   mag), ("Ralt",  mag),
        ("dHdop", gga), ("dSNo",  gga),
        ("Sk",    spc), ("Su",    spc), ("Sth",   spc),
    ]
    _qual_rows = []
    for _col, _df in _TERM_VARS:
        if _col not in _df.columns or _df[_col].isna().all():
            continue
        _s = _df[_col].dropna()
        _mn, _sd = f"{_s.mean():.3f}", f"{_s.std():.4f}"
        if _col in STABILITY_THRESHOLDS:
            _, _thresh = STABILITY_THRESHOLDS[_col]
            _qst = "! HIGH STD" if _s.std() > _thresh else "OK"
        else:
            _qst = "OK"
        _qual_rows.append((_col, _mn, _sd, _qst))
    if _qual_rows:
        print()
        print(ascii_table(["Variable", "Mean", "Std", "Status"], _qual_rows))

    # c) Warning summary
    _n_crit   = len(evt["critical_lines"])
    _n_mux_to = sum(wrn.get(k, 0) for k in ["M1 TimeO", "M2 TimeO", "M3 TimeO"])
    print()
    print(f"  {_n_crit} critical errors   {_n_mux_to} Mux TimeO warnings (normal on ground)")
    print(f"  Full report: outputs/session_{snum}/report_{snum}.txt")
    print("-" * 72)

    return {
        "session"         : snum,
        "data_dir"        : data_dir,
        "evt"             : evt,
        "cfg"             : cfg,
        "mag"             : mag,
        "gga"             : gga,
        "spc"             : spc,
        "stab_rows"       : stab_rows,
        "conn_rows"       : conn_rows,
        "warn_counts"     : wrn,
        "critical_lines"  : evt["critical_lines"],
        "fully_nan_mag"   : fully_nan_m,
        "partial_nan_mag" : partial_nan_m,
    }
