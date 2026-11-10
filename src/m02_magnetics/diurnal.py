"""
Module 2 — Step 3: Diurnal correction.

The Earth's magnetic field varies continuously due to external sources
(ionospheric currents, magnetospheric fluctuations, solar wind). This
variation — called the diurnal variation — can reach 10–100 nT on a quiet day
and several hundred nT during a magnetic storm. It must be removed from the
airborne data so that only the crustal/geological signal remains.

The correction is measured at a fixed ground base station (Tagesgang files)
throughout the day and interpolated to each airborne sample timestamp.

Formula
-------
    δ(t) = B_base(t) − B_ref
    Mag1_Diurnal(t) = Mag1C(t) − δ(t)

where:
    B_base(t)  : base station reading interpolated to flight time (nT)
    B_ref      : reference level = igrf_base_field_nT from project.yaml
    δ(t)       : diurnal variation (nT); positive when field is above reference
    Mag1C      : compensated total field from the aircraft (nT)
    Mag1_Diurnal: total field after diurnal removal (nT)

Sign convention
---------------
    Diurnal column = −δ(t) = B_ref − B_base(t)
    This is the Geosoft/Oasis Montaj convention: Mag1_Diurnal = Mag1C + Diurnal

Time matching
-------------
Base station and aircraft are matched on ABSOLUTE UTC time (date + time), never on the
time of day: each Tagesgang file crosses midnight UTC and the files are not always in
the folder of the day they belong to. The date of a file comes from its header, the date
of a flight from the MAG 'Date' column.

In Oasis Montaj this step is done with the DIURNAL menu under
Process → Diurnal → Apply Base Station Correction.
"""

import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from src.m00_preparation.read_tagesgang import read_tagesgang

MIN_QUALITY    = 94     # base station quality flag (sq): 95-96 is normal, lower ones are mostly spikes
SPIKE_NT       = 1.0    # reading further than this from the running median is discarded (normal scatter: ~0.25 nT)
MAX_BASE_GAP_S = 60.0   # no interpolation across a gap longer than this between two readings

_ROMAN_MONTHS = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6,
                 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10, 'XI': 11, 'XII': 12}


def _header_date(path: Path) -> date | None:
    """UTC date of the start of a Tagesgang file, from its header line '/ID ... file ...  21 IV 22'."""
    with open(path, 'r', errors='replace') as f:
        for line in f:
            m = re.search(r'file\s+\S+\s+(\d{1,2})\s+([IVX]+)\s+(\d{2})\b', line)
            if m and m.group(2) in _ROMAN_MONTHS:
                return date(2000 + int(m.group(3)), _ROMAN_MONTHS[m.group(2)], int(m.group(1)))
            if line.strip() and not line.startswith('/'):
                break
    return None


def read_base_station(raw_root: Path) -> pd.DataFrame:
    """
    Read every Tagesgang file of every day folder into one table with absolute UTC time.

    The time of a reading is the header date of its file plus the time of day, plus one day
    for each midnight crossed inside the file. Readings with quality below MIN_QUALITY,
    zero values and spikes are discarded, and readings that appear twice (the same
    recording copied into two folders) are kept once.

    Returns a DataFrame sorted by time with columns utc_s (seconds since 1970-01-01 UTC),
    nT and source ('<folder>/<file>'). The list of things worth telling the user is in
    df.attrs['notes'].
    """
    parts, notes = [], []
    for path in sorted(raw_root.glob('*/Tagesgang*')):
        source = f"{path.parent.name}/{path.name}"
        start  = _header_date(path)
        if start is None:
            notes.append(f"{source}: no date in the header, file ignored.")
            continue

        df = read_tagesgang(path)
        t  = df['time_s'].values
        wraps = np.cumsum(np.diff(t, prepend=t[0]) < -43200)          # midnight crossings
        t0 = np.datetime64(start, 'D').astype('int64') * 86400
        df['utc_s']  = t0 + t + 86400 * wraps
        df['source'] = source

        df = df[(df['nT'] > 1000) & (df['quality'] >= MIN_QUALITY)].copy()
        med = df['nT'].rolling(31, center=True, min_periods=5).median()
        df  = df[(df['nT'] - med).abs() <= SPIKE_NT]
        parts.append(df[['utc_s', 'nT', 'source']])

    if not parts:
        raise FileNotFoundError(f"No Tagesgang files found under {raw_root}")

    base = pd.concat(parts, ignore_index=True).sort_values('utc_s', kind='stable')
    dup  = base.duplicated('utc_s', keep='first')
    for src, n in base[dup].groupby('source').size().items():
        notes.append(f"{src}: {n} readings are a copy of another file (same recording in two "
                     f"folders); kept once.")
    base = base[~dup].reset_index(drop=True)
    base.attrs['notes'] = notes
    return base


def flight_utc_s(df: pd.DataFrame) -> np.ndarray:
    """
    Absolute UTC time (seconds since 1970-01-01) of every row of a flight.

    MAG gives Date (YYYYMMDD) and Time. Time is missing in about 13 % of the rows and has
    glitches (0.0, 0.1 s...) in a few. A time is only trusted if it keeps a nearly constant
    difference with the M3clk clock of the flight (a glitch is off by hours); the other rows
    are filled by interpolating the trusted ones along M3clk.
    """
    clock = df['M3clk'].values.astype(float)
    nominal = (df['time_s'].notna() & (df['time_s'] > 0) & df['Date'].notna()).values
    days = pd.to_datetime(df.loc[nominal, 'Date'].astype(int).astype(str), format='%Y%m%d')
    absolute = days.values.astype('datetime64[D]').astype('int64') * 86400 + df.loc[nominal, 'time_s'].values

    order = np.argsort(clock[nominal])
    x, a  = clock[nominal][order], absolute[order]
    offset = a - x / 1000.0                                   # slowly drifting for a good clock
    median = pd.Series(offset).rolling(201, center=True, min_periods=20).median().values
    good   = np.abs(offset - median) <= 30.0
    return np.interp(clock, x[good], a[good])


def apply_diurnal(
    df: pd.DataFrame,
    base: pd.DataFrame,
    igrf_base_nT: float,
) -> pd.DataFrame:
    """
    Apply the diurnal correction to Mag1C and Mag2C using the base station table.

    Adds the following columns to the DataFrame:
        utc_s         : absolute UTC time of the sample (s since 1970-01-01)
        BaseMag       : base station field interpolated to the sample time (nT); NaN where
                        the base station has no reading within MAX_BASE_GAP_S
        Diurnal       : correction term = B_ref − BaseMag  (sign: Geosoft convention)
        Mag1_Diurnal  : Mag1C after diurnal removal (nT)
        Mag2_Diurnal  : Mag2C after diurnal removal (nT)

    Samples without base station coverage are left as NaN: they are not extrapolated.

    Parameters
    ----------
    df           : flight DataFrame with Date, time_s, M3clk, Mag1C, Mag2C
    base         : output of read_base_station
    igrf_base_nT : reference level (igrf_base_field_nT in project.yaml)
    """
    df = df.copy()
    t  = flight_utc_s(df)
    tb = base['utc_s'].values
    bb = base['nT'].values

    idx   = np.searchsorted(tb, t)                       # tb[idx-1] <= t < tb[idx]
    left  = np.clip(idx - 1, 0, len(tb) - 1)
    right = np.clip(idx, 0, len(tb) - 1)
    covered = (idx > 0) & (idx < len(tb)) & ((tb[right] - tb[left]) <= MAX_BASE_GAP_S)

    base_interp = np.full(len(df), np.nan)
    base_interp[covered] = np.interp(t[covered], tb, bb)

    delta = base_interp - igrf_base_nT                   # diurnal variation δ(t)

    df['utc_s']   = t
    df['BaseMag'] = base_interp
    df['Diurnal'] = -delta                               # Geosoft sign convention
    if 'Mag1C' in df.columns:
        df['Mag1_Diurnal'] = df['Mag1C'] - delta
    if 'Mag2C' in df.columns:
        df['Mag2_Diurnal'] = df['Mag2C'] - delta

    n_cov = int(covered.sum())
    if n_cov:
        print(f"  [DIURNAL] Base station covers {n_cov:,} of {len(df):,} samples  |  "
              f"δ range: [{np.nanmin(delta):+.2f}, {np.nanmax(delta):+.2f}] nT")
    else:
        print(f"  [DIURNAL] No base station data for this flight: samples left as NaN.")
    return df
