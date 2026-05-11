"""
Parser for GeoDuster Tagesgang files (magnetic base station).

Tagesgang files are space-separated plain text with a variable number of header
lines prefixed with '/'. They record the diurnal variation of the Earth's magnetic
field at a fixed ground station throughout the day, at ~3 Hz (one reading every ~3 s).

'Tagesgang' is German for 'daily variation'. These readings are used in Module 2
to remove the time-varying component of the ambient field from the airborne data.

File format (after header lines):
    HHMMSS.f  nT  sq
where sq is a quality flag (typically 95-96 for good data).
"""

import pandas as pd
from pathlib import Path

from src.utils.fwf_parser import hhmmss_to_seconds


def read_tagesgang(path: Path | str) -> pd.DataFrame:
    """
    Read a Tagesgang file and return a cleaned DataFrame.

    Parameters
    ----------
    path : path to Tagesgang file (e.g. Tagesgang00427.txt)

    Returns
    -------
    DataFrame with columns:
        time_s  — UTC seconds from midnight
        nT      — total magnetic field at base station
        quality — quality flag (95-96 = good)
    """
    path = Path(path)

    rows = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('/'):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    rows.append([float(parts[0]), float(parts[1]),
                                 int(parts[2]) if len(parts) >= 3 else None])
                except ValueError:
                    continue

    df = pd.DataFrame(rows, columns=['_time_raw', 'nT', 'quality'])
    df['time_s'] = hhmmss_to_seconds(df['_time_raw'])
    df = df.drop(columns=['_time_raw'])

    return df[['time_s', 'nT', 'quality']]
