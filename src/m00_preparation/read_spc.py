"""
Parser for GeoDuster SPC files.

SPC files are fixed-width ASCII produced by Mux3 at ~1 Hz. They record data from
the Medusa gamma-ray spectrometer: radiometric channels (K, U, Th), environmental
sensors (barometric pressure, temperature, humidity), and GPS position.

The low sampling rate (1 Hz vs. 10 Hz for MAG/GGA) means that during synchronisation
each SPC row is forward-filled to ~10 adjacent MAG/GGA rows.

Dropped column:
  Sbin — binary spectral data block (raw pulse-height spectrum), not used in processing
"""

import re
import pandas as pd
from pathlib import Path

from src.utils.fwf_parser import load_fwf, hhmmss_to_seconds

_DROP = {'M2st', 'Sbin'}


def read_spc(path: Path | str, flight_id: str | None = None) -> pd.DataFrame:
    """
    Read a SPC file and return a cleaned DataFrame.

    Parameters
    ----------
    path      : path to SPC file (e.g. SPC00427.txt)
    flight_id : 5-digit string (e.g. '00427'). Extracted from filename if None.

    Returns
    -------
    DataFrame with columns:
        flight_id, M2clk, time_s,
        Sxgps, Sygps, Szgps, Sralt,
        Sbaro, Stemp, Shumd,
        Sk (potassium %), Su (uranium ppm), Sth (thorium ppm),
        Sa0, Sa1, Sa2, Srate
    """
    path = Path(path)
    if flight_id is None:
        flight_id = re.search(r'\d+', path.stem).group().zfill(5)

    df = load_fwf(path, drop_cols=_DROP)

    # Sdate: keep as integer YYYYMMDD
    if 'Sdate' in df.columns:
        df['Sdate'] = df['Sdate'].astype('Int64')

    df['time_s'] = hhmmss_to_seconds(df['Stime'])
    df['flight_id'] = flight_id

    col_order = ['flight_id', 'M2clk', 'Sdate', 'time_s',
                 'Sxgps', 'Sygps', 'Szgps', 'Sralt',
                 'Sbaro', 'Stemp', 'Shumd',
                 'Sk', 'Su', 'Sth',
                 'Sa0', 'Sa1', 'Sa2', 'Srate']
    present = [c for c in col_order if c in df.columns]
    return df[present]
