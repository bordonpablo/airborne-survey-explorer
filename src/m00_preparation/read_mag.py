"""
Parser for GeoDuster MAG files.

MAG files are fixed-width ASCII produced by Mux1 at ~10 Hz. They record data from
both magnetometers (GEMK1/GEMK2), the radar altimeter, VLF channels, and the XSENS
attitude sensor (Roll, Pitch, Yaw).

The 'Wayp' field is populated in real-time by the onboard navigation system and
identifies which survey line the aircraft is currently flying. When blank, the
aircraft is in transit or turning (not on a survey line).

Dropped columns:
  Xpr, M1st  — acquisition status bytes, not useful for processing
  Xst        — long hex status word
  Bin        — binary data block
"""

import re
import pandas as pd
from pathlib import Path

from src.utils.fwf_parser import load_fwf, hhmmss_to_seconds

_DROP = {'Xpr', 'M1st', 'Xst', 'Bin'}


def read_mag(path: Path | str, flight_id: str | None = None) -> pd.DataFrame:
    """
    Read a MAG file and return a cleaned DataFrame.

    Parameters
    ----------
    path      : path to MAG file (e.g. MAG00427.txt)
    flight_id : 5-digit string (e.g. '00427'). Extracted from filename if None.

    Returns
    -------
    DataFrame indexed by M1clk (ms from system start) with columns:
        flight_id, line_id (from Wayp), time_s (UTC seconds from midnight),
        Xgps, Ygps, Zgps, Lalt, Raltr, Ralt,
        Mag1, Mag2, Mag1C, Mag2C, MagL, MagLC,
        Mag1D, Mag2D,
        A1, T1, X1, Y1, Z1, A2, T2, X2, Y2, Z2,
        Vlf1, Vlf2, Vlf3, Vlf4,
        Roll, Pitch, Yaw
    """
    path = Path(path)
    if flight_id is None:
        flight_id = re.search(r'\d+', path.stem).group().zfill(5)

    df = load_fwf(path, drop_cols=_DROP)

    # Wayp: nullable integer line ID (NaN = not on a survey line)
    if 'Wayp' in df.columns:
        df['Wayp'] = df['Wayp'].astype('Int64')

    # Date: keep as integer YYYYMMDD
    if 'Date' in df.columns:
        df['Date'] = df['Date'].astype('Int64')

    df['time_s'] = hhmmss_to_seconds(df['Time'])
    df = df.rename(columns={'Wayp': 'line_id'})
    df['flight_id'] = flight_id

    col_order = ['flight_id', 'M1clk', 'line_id', 'Date', 'Time', 'time_s',
                 'Xgps', 'Ygps', 'Zgps', 'Lalt', 'Raltr', 'Ralt',
                 'Mag1', 'Mag2', 'Mag1C', 'Mag2C', 'MagL', 'MagLC',
                 'Mag1D', 'Mag2D',
                 'A1', 'T1', 'X1', 'Y1', 'Z1',
                 'A2', 'T2', 'X2', 'Y2', 'Z2',
                 'Vlf1', 'Vlf2', 'Vlf3', 'Vlf4',
                 'Roll', 'Pitch', 'Yaw']
    present = [c for c in col_order if c in df.columns]
    return df[present]
