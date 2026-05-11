"""
Parser for the TestSurveyNav.csv flight plan file.

The file uses a CSV format with descriptive header lines at the top.
Each 'Coord' record defines one survey line (or a special point like Apron/BeforePoint).
Coordinates are in UTM zone 48N (EPSG:32648), Easting/Northing in metres.

Coord record format:
    Coord, <flown>, <line_id>, <n_points>, <E1>, <N1>, <Z1>, <E2>, <N2>, <Z2>

where flown: 0=unflown, 1=flown, 2=currently flying.
"""

import pandas as pd
from pathlib import Path


def read_survey_nav(path: Path | str) -> pd.DataFrame:
    """
    Read the survey navigation plan and return one row per survey line.

    Parameters
    ----------
    path : path to TestSurveyNav.csv

    Returns
    -------
    DataFrame with columns:
        line_id (Int64), flown (int),
        E_start, N_start, E_end, N_end  — UTM zone 48N coordinates in metres

    Special points (Apron, BeforePoint) are excluded.
    """
    path = Path(path)
    rows = []

    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line.startswith('Coord'):
                continue
            parts = [p.strip() for p in line.split(',')]
            # Coord,<flown>,<label>,<n_pts>,<E1>,<N1>,<Z1>[,<E2>,<N2>,<Z2>]
            if len(parts) < 7:
                continue
            label = parts[2]
            # Skip non-numeric labels (Apron, BeforePoint, etc.)
            try:
                line_id = int(label)
            except ValueError:
                continue
            flown = int(parts[1])
            n_pts = int(parts[3])
            e1, n1 = float(parts[4]), float(parts[5])
            if n_pts >= 2 and len(parts) >= 10:
                e2, n2 = float(parts[7]), float(parts[8])
            else:
                e2, n2 = e1, n1
            rows.append([line_id, flown, e1, n1, e2, n2])

    df = pd.DataFrame(rows, columns=['line_id', 'flown', 'E_start', 'N_start', 'E_end', 'N_end'])
    df['line_id'] = df['line_id'].astype('Int64')
    return df.sort_values('line_id').reset_index(drop=True)
