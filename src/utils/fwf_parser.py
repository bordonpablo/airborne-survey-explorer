"""
Shared utilities for parsing GeoDuster fixed-width ASCII files (MAG, GGA, SPC).

Column boundaries in these files align with the RIGHT edge of each header token.
The colspecs are therefore derived from m.end() positions, not m.start().
Cells containing only '#' characters encode NaN.
"""

import re
import pandas as pd
from pathlib import Path


def build_colspecs(header: str) -> tuple[list[tuple[int, int]], list[str]]:
    """
    Derive pd.read_fwf colspecs from a fixed-width header line.

    Each column's right boundary is the end position of its header token.
    The left boundary of column i is the right boundary of column i-1.
    """
    tokens = list(re.finditer(r'\S+', header))
    boundaries = [0] + [m.end() for m in tokens]
    colspecs = [(boundaries[i], boundaries[i + 1]) for i in range(len(tokens))]
    names = [m.group() for m in tokens]
    return colspecs, names


def load_fwf(path: Path | str, drop_cols: set[str] | None = None) -> pd.DataFrame:
    """
    Load a GeoDuster fixed-width file into a DataFrame.

    Reads all columns as strings first, replaces '#'-only cells with NaN,
    then converts numeric columns. Hex/binary columns listed in drop_cols
    are discarded before conversion.

    Parameters
    ----------
    path      : path to the data file
    drop_cols : column names to discard (typically hex/binary columns)
    """
    path = Path(path)
    drop_cols = drop_cols or set()

    with open(path, 'r') as f:
        header = f.readline()

    colspecs, names = build_colspecs(header)

    df = pd.read_fwf(
        path,
        colspecs=colspecs,
        names=names,
        skiprows=1,
        dtype=str,
    )

    df = df.drop(columns=[c for c in drop_cols if c in df.columns])
    df = df.replace(r'^#+$', float('nan'), regex=True)
    df = df.apply(pd.to_numeric, errors='coerce')

    return df


def hhmmss_to_seconds(series: pd.Series) -> pd.Series:
    """
    Convert a time column encoded as HHMMSS.sss float to seconds from midnight.

    Example: 232324.931 → 84204.931
    """
    t = series
    hh = (t // 10000).astype('float64')
    mm = ((t % 10000) // 100).astype('float64')
    ss = (t % 100).astype('float64')
    return hh * 3600 + mm * 60 + ss
