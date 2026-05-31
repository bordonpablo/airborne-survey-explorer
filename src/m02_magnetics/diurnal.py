"""
Module 2 — Step 3: Diurnal correction.

The Earth's magnetic field varies continuously due to external sources
(ionospheric currents, magnetospheric fluctuations, solar wind). This
variation — called the diurnal variation — can reach 10–100 nT on a quiet day
and several hundred nT during a magnetic storm. It must be removed from the
airborne data so that only the crustal/geological signal remains.

The correction is measured at a fixed ground base station (Tagesgang file)
throughout the day and interpolated to each airborne sample timestamp.

Formula
-------
    δ(t) = B_base(t) − B_ref
    Mag1_Diurnal(t) = Mag1C(t) − δ(t)

where:
    B_base(t)  : base station reading interpolated to flight time (nT)
    B_ref      : quiet-time reference level = igrf_base_field_nT from project.yaml
    δ(t)       : diurnal variation (nT); positive when field is above reference
    Mag1C      : compensated total field from the aircraft (nT)
    Mag1_Diurnal: total field after diurnal removal (nT)

Sign convention
---------------
    Diurnal column = −δ(t) = B_ref − B_base(t)
    This matches the Geosoft/Oasis Montaj convention in the specialist data:
    Mag1_Diurnal = Mag1C + Diurnal  (same as Mag1C − δ)

In Oasis Montaj this step is done with the DIURNAL menu under
Process → Diurnal → Apply Base Station Correction.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from src.m00_preparation.read_tagesgang import read_tagesgang


def find_tagesgang(raw_root: Path, date: str) -> Path:
    """
    Return the path to the Tagesgang file for a given flight date.

    One Tagesgang file per day covers all flights of that day.
    Filename pattern: Tagesgang<flight1>_<flight2> (no extension).

    Parameters
    ----------
    raw_root : root raw data folder (e.g. data/raw/Mongolia_2022/Daten_Nisleg_2022)
    date     : date folder name (DD.MM.YYYY)
    """
    day_dir = raw_root / date
    candidates = [
        p for p in day_dir.iterdir()
        if p.name.startswith('Tagesgang') and p.is_file()
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No Tagesgang file found in {day_dir}\n"
            "Expected a file starting with 'Tagesgang'."
        )
    if len(candidates) > 1:
        print(f"  [DIURNAL] Warning: multiple Tagesgang files in {date} — using {candidates[0].name}")
    return candidates[0]


def apply_diurnal(
    df: pd.DataFrame,
    tagesgang_df: pd.DataFrame,
    igrf_base_nT: float,
) -> pd.DataFrame:
    """
    Apply diurnal correction to Mag1C and Mag2C using the base station record.

    Adds the following columns to the DataFrame:
        BaseMag       : base station field interpolated to flight time (nT)
        Diurnal       : correction term = B_ref − BaseMag  (sign: Geosoft convention)
        Mag1_Diurnal  : Mag1C after diurnal removal (nT)
        Mag2_Diurnal  : Mag2C after diurnal removal (nT)

    Parameters
    ----------
    df           : flight DataFrame with columns Mag1C, Mag2C, time_s
    tagesgang_df : base station DataFrame with columns time_s, nT
                   (output of read_tagesgang)
    igrf_base_nT : IGRF reference field at the survey area (from project.yaml)
    """
    df = df.copy()

    tag = tagesgang_df.dropna(subset=['time_s', 'nT']).sort_values('time_s')

    t_base = tag['time_s'].values
    b_base = tag['nT'].values
    t_flight = df['time_s'].values

    # Check temporal coverage
    t_min, t_max = df['time_s'].dropna().agg(['min', 'max'])
    if t_min < t_base[0] or t_max > t_base[-1]:
        print(f"  [DIURNAL] Warning: flight time [{t_min:.0f}–{t_max:.0f} s] "
              f"extends outside base station record [{t_base[0]:.0f}–{t_base[-1]:.0f} s]. "
              f"Edges will be extrapolated (constant).")

    # Interpolate base station to flight timestamps (clamp at edges)
    base_interp = np.interp(t_flight, t_base, b_base,
                            left=b_base[0], right=b_base[-1])

    delta = base_interp - igrf_base_nT          # diurnal variation δ(t)

    df['BaseMag']  = base_interp
    df['Diurnal']  = -delta                     # Geosoft sign convention

    if 'Mag1C' in df.columns:
        df['Mag1_Diurnal'] = df['Mag1C'] - delta
    if 'Mag2C' in df.columns:
        df['Mag2_Diurnal'] = df['Mag2C'] - delta

    n_valid = int(pd.notna(base_interp).sum())
    print(f"  [DIURNAL] Interpolated {n_valid:,} samples  |  "
          f"δ range: [{delta.min():+.2f}, {delta.max():+.2f}] nT  |  "
          f"mean |δ| = {np.abs(delta).mean():.2f} nT")

    return df
