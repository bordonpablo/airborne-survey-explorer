"""
Module 2 — Step 3 (supplement): base station readings rebuilt from the specialist's data.

Flight 00434 (26.04.2022) has no Tagesgang recording in our raw folders, but the specialist's
delivery (data/reference/magnetics_example.dat) has the filtered base station value of that
flight in its column BaseMag. This script turns that column into a table with the same layout
the diurnal correction reads (UTC time in seconds, nT, source), one reading every ~3 s like a
real Tagesgang file, so that diurnal.py can use it where our own base station has no data.

The specialist's BaseMag is already filtered, and with it we cannot validate that flight against
his result (it is his own input). Replace it when the original Tagesgang file is available.

Run (from the project root):
    python -m src.m02_magnetics.base_supplement            # flight 434
    python -m src.m02_magnetics.base_supplement 434 435    # several flights (none may cross midnight UTC)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DAT = PROJECT_ROOT / 'data' / 'reference' / 'magnetics_example.dat'
OUTPUT_CSV    = PROJECT_ROOT / 'data' / 'reference' / 'base_station_supplement.csv'
BIN_S         = 3.0            # one reading every 3 s, like the Tagesgang files

# Column positions in the .dat (see data/reference/magnetics.ddf)
COL_DATE, COL_FLIGHT, COL_GTIME, COL_BASEMAG = 2, 4, 6, 27
MISSING = 999990


def build_supplement(flights: list[int], dat_path: Path = REFERENCE_DAT) -> pd.DataFrame:
    """
    Base station readings of the given flights, taken from the specialist's BaseMag column.

    gtime is the UTC time of day in seconds; the date comes from YYYYMMDD. The 10 Hz values are
    reduced to the median of each BIN_S-second bin.
    """
    raw = pd.read_csv(dat_path, sep=r'\s+', header=None,
                      usecols=[COL_DATE, COL_FLIGHT, COL_GTIME, COL_BASEMAG],
                      names=['date', 'flight', 'gtime', 'nT'])
    raw = raw[raw['flight'].isin(flights) & (raw['nT'] < MISSING)]
    if raw.empty:
        raise ValueError(f"No BaseMag values for flights {flights} in {dat_path}")

    day = pd.to_datetime(raw['date'].astype(int).astype(str), format='%Y%m%d')
    raw['utc_s'] = day.values.astype('datetime64[D]').astype('int64') * 86400 + raw['gtime'].values
    raw['bin'] = np.floor(raw['utc_s'] / BIN_S)
    out = raw.groupby(['flight', 'bin']).agg(utc_s=('utc_s', 'median'), nT=('nT', 'median')).reset_index()
    out['source'] = 'specialist BaseMag, flight ' + out['flight'].astype(int).astype(str).str.zfill(5)
    return out[['utc_s', 'nT', 'source']].sort_values('utc_s').reset_index(drop=True)


if __name__ == '__main__':
    wanted = [int(a) for a in sys.argv[1:]] or [434]
    table = build_supplement(wanted)
    table.to_csv(OUTPUT_CSV, index=False)
    t = pd.to_datetime(table['utc_s'], unit='s')
    print(f"Flights {wanted}: {len(table):,} readings, {t.min()} to {t.max()} UTC, "
          f"{table['nT'].min():.1f} to {table['nT'].max():.1f} nT")
    print(f"Saved: {OUTPUT_CSV.relative_to(PROJECT_ROOT)}")
