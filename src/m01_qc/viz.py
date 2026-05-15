"""
Module 1 — QC visualisations.

summary_figure : map of all selected tracks (coloured pass/fail) + metric heatmap.
detail_figure  : all QC variables for one segment in a single multi-panel figure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.gridspec as gridspec
from matplotlib.lines import Line2D
from pathlib import Path


# Only the three metrics with thresholds from TestSurveyNav get pass/fail columns.
# All other metrics are informative values shown in the report CSV but not here.
HEATMAP_COLS = [
    ('pass_altitude',    'Altitud'),
    ('pass_cross_track', 'Desvío transv.'),
    ('pass_speed',       'Velocidad'),
]

VALUE_COLS = {
    'pass_altitude':    ('ralt_mean_m',        '{:.0f}m'),
    'pass_cross_track': ('cross_track_max_m',  '{:.0f}m'),
    'pass_speed':       ('speed_mean_kmh',     '{:.0f}km/h'),
}

_CMAP = mcolors.ListedColormap(['#2ecc71', '#e74c3c', '#bdc3c7'])


def _along_track_km(df: pd.DataFrame) -> np.ndarray:
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6371.0 * np.sqrt(dlat ** 2 + (np.cos(lat_mid) * dlon) ** 2)
    return np.concatenate([[0.0], np.cumsum(d)])


# ---------------------------------------------------------------------------
# Summary figure: map + heatmap
# ---------------------------------------------------------------------------

def summary_figure(
    qc_df: pd.DataFrame,
    gps_dict: dict,
    out_path: Path,
) -> None:
    n_lines = len(qc_df)
    fig_h   = max(7, n_lines * 0.4 + 3)
    fig, (ax_map, ax_heat) = plt.subplots(
        1, 2, figsize=(18, fig_h),
        gridspec_kw={'width_ratios': [1, 2]},
    )
    fig.suptitle('Module 1 — QC Summary', fontsize=13, fontweight='bold')

    # ---- Map ---------------------------------------------------------------
    for _, row in qc_df.iterrows():
        key = (str(row['flight_id']), int(row['line_id']), row['date'])
        gps = gps_dict.get(key)
        if gps is None or gps.empty:
            continue
        color = '#2ecc71' if row.get('pass_all') else '#e74c3c'
        ax_map.plot(gps['Xgps'].values, gps['Ygps'].values,
                    '-', color=color, linewidth=1.4, alpha=0.85)

    ax_map.set_xlabel('Longitude')
    ax_map.set_ylabel('Latitude')
    ax_map.set_title('Flight tracks')
    ax_map.set_aspect('equal')
    ax_map.grid(True, alpha=0.2)
    ax_map.legend(handles=[
        Line2D([0], [0], color='#2ecc71', linewidth=3, label='Pass'),
        Line2D([0], [0], color='#e74c3c', linewidth=3, label='Fail'),
    ], fontsize=8)

    # ---- Heatmap -----------------------------------------------------------
    cols_present = [(c, lbl) for c, lbl in HEATMAP_COLS if c in qc_df.columns]
    col_keys = [c   for c, _ in cols_present]
    col_lbls = [lbl for _, lbl in cols_present]

    row_labels = [
        f"{r['flight_id']} · {int(r['line_id'])}"
        for _, r in qc_df.iterrows()
    ]

    mat = np.full((n_lines, len(col_keys)), 2.0)
    for i, (_, row) in enumerate(qc_df.iterrows()):
        for j, col in enumerate(col_keys):
            v = row.get(col)
            if v is True:
                mat[i, j] = 0.0
            elif v is False:
                mat[i, j] = 1.0

    norm = mcolors.BoundaryNorm([0, 0.5, 1.5, 2.5], _CMAP.N)
    ax_heat.imshow(mat, cmap=_CMAP, norm=norm, aspect='auto')

    ax_heat.set_xticks(range(len(col_lbls)))
    ax_heat.set_xticklabels(col_lbls, rotation=40, ha='right', fontsize=8)
    ax_heat.set_yticks(range(n_lines))
    ax_heat.set_yticklabels(row_labels, fontsize=8)
    ax_heat.set_title('QC metrics  (green = pass · red = fail · gray = n/a)')

    for i, (_, row) in enumerate(qc_df.iterrows()):
        for j, col in enumerate(col_keys):
            val_col, fmt = VALUE_COLS.get(col, (None, ''))
            if val_col and val_col in qc_df.columns:
                v = row.get(val_col)
                if pd.notna(v):
                    txt_color = 'white' if mat[i, j] == 1.0 else 'black'
                    ax_heat.text(j, i, fmt.format(v), ha='center', va='center',
                                 fontsize=6.5, color=txt_color)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"  Saved: {out_path}")
    plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Detail figure: all variables for one segment, simultaneously
# ---------------------------------------------------------------------------

def detail_figure(
    seg: pd.DataFrame,
    survey_thresholds: dict,
    out_path: Path,
) -> None:
    """
    Four-panel profile figure for one segment: altitude, attitude, heading,
    magnetics. Reference lines come exclusively from TestSurveyNav thresholds.
    """
    seg    = seg.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps'])
    dist   = _along_track_km(seg)
    flight = seg['flight_id'].iloc[0]
    lid    = int(seg['line_id'].iloc[0])

    fig = plt.figure(figsize=(16, 11))
    fig.suptitle(
        f"M1 QC Detail — Flight {flight}  ·  Line {lid}",
        fontsize=13, fontweight='bold',
    )

    gs = gridspec.GridSpec(
        4, 2,
        width_ratios=[1, 2.5],
        hspace=0.08,
        wspace=0.28,
        left=0.07, right=0.97, top=0.93, bottom=0.07,
    )

    ax_map  = fig.add_subplot(gs[:, 0])
    ax_ralt = fig.add_subplot(gs[0, 1])
    ax_att  = fig.add_subplot(gs[1, 1], sharex=ax_ralt)
    ax_yaw  = fig.add_subplot(gs[2, 1], sharex=ax_ralt)
    ax_mag  = fig.add_subplot(gs[3, 1], sharex=ax_ralt)

    plt.setp(ax_ralt.get_xticklabels(), visible=False)
    plt.setp(ax_att.get_xticklabels(),  visible=False)
    plt.setp(ax_yaw.get_xticklabels(),  visible=False)

    # ---- GPS map -----------------------------------------------------------
    ax_map.plot(seg['Xgps'].values, seg['Ygps'].values,
                '-', color='steelblue', linewidth=1.2)
    ax_map.set_xlabel('Longitude', fontsize=8)
    ax_map.set_ylabel('Latitude', fontsize=8)
    ax_map.set_title('GPS track', fontsize=9)
    ax_map.set_aspect('equal')
    ax_map.grid(True, alpha=0.2)
    ax_map.tick_params(labelsize=7)

    # ---- Radar altitude ----------------------------------------------------
    if 'Ralt' in seg.columns:
        ax_ralt.plot(dist, seg['Ralt'].values, color='steelblue',
                     linewidth=0.8, label='Ralt')
    if 'Lalt' in seg.columns:
        ax_ralt.plot(dist, seg['Lalt'].values, color='teal',
                     linewidth=0.8, label='Lalt', alpha=0.7)
    rmin = survey_thresholds.get('radar_min_m')
    rmax = survey_thresholds.get('radar_max_m')
    if rmin:
        ax_ralt.axhline(rmin, color='darkorange', linestyle='--',
                        linewidth=1, label=f'RadarMin {rmin:.0f} m')
    if rmax:
        ax_ralt.axhline(rmax, color='red', linestyle='--',
                        linewidth=1, label=f'RadarMax {rmax:.0f} m')
    ax_ralt.set_ylabel('Altitude (m)', fontsize=8)
    ax_ralt.legend(fontsize=7, loc='upper right', ncol=2)
    ax_ralt.grid(True, alpha=0.3)
    ax_ralt.tick_params(labelsize=7)

    # ---- Roll + Pitch (no threshold lines — informative only) -------------
    for col, color in [('Roll', 'seagreen'), ('Pitch', 'mediumpurple')]:
        if col in seg.columns:
            ax_att.plot(dist, seg[col].values, color=color,
                        linewidth=0.8, label=col)
    ax_att.axhline(0, color='gray', linewidth=0.5)
    ax_att.set_ylabel('Roll / Pitch (°)', fontsize=8)
    ax_att.legend(fontsize=7, loc='upper right', ncol=3)
    ax_att.grid(True, alpha=0.3)
    ax_att.tick_params(labelsize=7)

    # ---- Yaw ---------------------------------------------------------------
    if 'Yaw' in seg.columns:
        ax_yaw.plot(dist, seg['Yaw'].values, color='darkorange',
                    linewidth=0.8, label='Yaw')
    ax_yaw.set_ylabel('Yaw (°)', fontsize=8)
    ax_yaw.legend(fontsize=7, loc='upper right')
    ax_yaw.grid(True, alpha=0.3)
    ax_yaw.tick_params(labelsize=7)

    # ---- Mag1 + Mag2 -------------------------------------------------------
    for col, color in [('Mag1', 'navy'), ('Mag2', 'darkorange')]:
        if col in seg.columns:
            ax_mag.plot(dist, seg[col].values, color=color,
                        linewidth=0.8, label=col, alpha=0.85)
    ax_mag.set_ylabel('Magnetometer (nT)', fontsize=8)
    ax_mag.set_xlabel('Along-track distance (km)', fontsize=8)
    ax_mag.legend(fontsize=7, loc='upper right')
    ax_mag.grid(True, alpha=0.3)
    ax_mag.tick_params(labelsize=7)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"  Saved: {out_path}")
    plt.show()
    plt.close(fig)
