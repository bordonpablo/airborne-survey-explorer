"""
Read and parse Medusa SPC files.

Each SPC file contains ~1 Hz gamma-ray spectrometry data: scalar sensor
readings plus a raw 512-channel spectrum (Sbin) for every second of flight.

Parsing note: the last numeric column (Sa2) and Sbin share a token with no
separator between them. Sa2 is a calibration constant not needed for scalar
processing, so that token is discarded. Sbin is passed unmodified to GammAn.

The optional Swayp field (survey line ID) is detected by token count:
  23 tokens → Swayp absent (transit or ferry)
  24 tokens → Swayp present at position 4
"""

import pandas as pd
from pathlib import Path


def read_spc(path: Path | str) -> pd.DataFrame:
    """
    Parse one SPC file and return a DataFrame of scalar channels.

    Parameters
    ----------
    path : path to SPC*.txt

    Returns
    -------
    DataFrame with columns:
        flight_id, M2clk, Sdate, Stime, Swayp,
        Sxgps, Sygps, Szgps, Sralt,
        Sbaro, Stemp, Shumd,
        Sreal, Slive, Srate,
        Sk, Su, Sth, Sa0, Sa1,
        livetime_frac
    """
    path = Path(path)
    rows = []

    with open(path, encoding='latin-1') as f:
        f.readline()  # skip header
        for line in f:
            if '##' not in line:
                continue
            parts = line.split()
            n = len(parts)

            # Token count distinguishes whether Swayp is present:
            #   23 → no Swayp  (fields 0-21 = M2st..Sa1, field 22 = Sa2+Sbin)
            #   24 → Swayp at parts[4]  (fields 0-3 + 5-22 = M2st..Sa1, 23 = Sa2+Sbin)
            if n == 23:
                swayp = ''
                p = parts
            elif n == 24:
                swayp = parts[4]
                p = parts[:4] + parts[5:]
            else:
                continue

            try:
                rows.append({
                    'M2clk': float(p[1]),
                    'Sdate': p[2],
                    'Stime': float(p[3]),
                    'Sxgps': float(p[4]),
                    'Sygps': float(p[5]),
                    'Szgps': float(p[6]),
                    'Sralt': float(p[7]),
                    # p[8]=BaroV, p[9]=TempV, p[10]=HumdV — raw ADC voltages, skipped
                    'Sbaro': float(p[11]),
                    'Stemp': float(p[12]),
                    'Shumd': float(p[13]),
                    'Sreal': float(p[14]),
                    'Slive': float(p[15]),
                    'Srate': float(p[16]),
                    'Sk':    float(p[17]),
                    'Su':    float(p[18]),
                    'Sth':   float(p[19]),
                    'Sa0':   float(p[20]),
                    'Sa1':   float(p[21]),
                    # p[22] = Sa2+Sbin concatenated — discarded
                    'Swayp': swayp,
                })
            except (ValueError, IndexError):
                continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    stem = path.stem
    flight_id = stem[3:] if stem.upper().startswith('SPC') else stem
    df.insert(0, 'flight_id', flight_id)

    sreal = df['Sreal'].replace(0.0, float('nan'))
    df['livetime_frac'] = df['Slive'] / sreal

    return df
