"""
Parser for GeoDuster GGA files.

GGA files are fixed-width ASCII produced by Mux2 at ~10 Hz. They record
differential GPS data from the Septentrio receiver: position (Xdgps, Ydgps, Zdgps)
and quality indicators (HDOP, satellite count, age of corrections).

GGA is used as the primary time axis for sensor synchronisation because it carries
the highest-accuracy position data (differential GPS vs. the standard GPS in MAG).
"""

import re
import pandas as pd
from pathlib import Path

from src.utils.fwf_parser import load_fwf, hhmmss_to_seconds

_DROP = {'M3st'}


def read_gga(path: Path | str, flight_id: str | None = None) -> pd.DataFrame:
    """
    Read a GGA file and return a cleaned DataFrame.

    Parameters
    ----------
    path      : path to GGA file (e.g. GGA00427.txt)
    flight_id : 5-digit string (e.g. '00427'). Extracted from filename if None.

    Returns
    -------
    DataFrame with columns:
        flight_id, M3clk, time_s,
        Xdgps, Ydgps, Zdgps,
        dSNo (satellite count), dHdop, dDOn, dAge, dSID
    """
    path = Path(path)
    if flight_id is None:
        flight_id = re.search(r'\d+', path.stem).group().zfill(5)

    df = load_fwf(path, drop_cols=_DROP)

    df['time_s'] = hhmmss_to_seconds(df['dTime'])
    df['flight_id'] = flight_id

    col_order = ['flight_id', 'M3clk', 'time_s',
                 'Xdgps', 'Ydgps', 'Zdgps',
                 'dSNo', 'dHdop', 'dDOn', 'dAge', 'dSID']
    present = [c for c in col_order if c in df.columns]
    return df[present]
