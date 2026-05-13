"""
Module 1 — QC visualisations.

summary_figure : map of all selected tracks (coloured pass/fail) + metric heatmap.
detail_figure  : interactive per-line view with threshold slider.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
from pathlib import Path


# Metrics shown in the heatmap and their short display labels
HEATMAP_COLS = [
    ('pass_altitude',    'Altitude'),
    ('pass_roll',        'Roll'),
    ('pass_pitch',       'Pitch'),
    ('pass_yaw',         'Yaw'),
    ('pass_cross_track', 'Cross-track'),
    ('pass_speed',       'Speed'),
    ('pass_spacing',     'Spacing'),
    ('pass_mag_noise',   'Mag noise'),
    ('pass_mag_spike',   'Mag spikes'),
    ('pass_diurnal',     'Diurnal'),
]

# Metric shown in each interactive panel and its axis label
DETAIL_VARS = {
    'Ralt':  ('ralt_pct_outside',   'Radar altitude (m)',     'ralt_max_m'),
    'Roll':  ('roll_pct_outside',   'Roll (°)',               None),
    'Pitch': ('pitch_pct_outside',  'Pitch (°)',              None),
    'Yaw':   ('yaw_std_deg',        'Yaw (°)',                None),
    'Mag1':  ('mag_noise_nT',       'Magnetometer 1 (nT)',    None),
    'Mag2':  ('mag_noise_nT',       'Magnetometer 2 (nT)',    None),
}

_CMAP = mcolors.ListedColormap(['#2ecc71', '#e74c3c', '#bdc3c7'])  # green/red/gray


def _along_track_km(df: pd.DataFrame) -> np.ndarray:
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6371.0 * np.sqrt(dlat ** 2 + (np.cos(lat_mid) * dlon) ** 2)
    return np.concatenate([[0.0], np.cumsum(d)])


# ---------------------------------------------------------------------------
# Summary figure
# ---------------------------------------------------------------------------

def summary_figure(
    qc_df: pd.DataFrame,
    gps_dict: dict,          # {(flight_id, line_id, date): DataFrame with Xgps, Ygps}
    out_path: Path,
) -> None:
    """
    Two-panel figure: map of all tracks (coloured by pass_all) + QC heatmap.

    Parameters
    ----------
    qc_df    : output of run_qc(), one row per segment
    gps_dict : GPS coordinates per segment, keyed by (flight_id, line_id, date)
    out_path : where to save the PNG
    """
    n_lines = len(qc_df)
    fig_h   = max(6, n_lines * 0.35 + 3)
    fig, (ax_map, ax_heat) = plt.subplots(
        1, 2, figsize=(18, fig_h),
        gridspec_kw={'width_ratios': [1, 2]},
    )
    fig.suptitle('Module 1 — QC Summary', fontsize=13, fontweight='bold')

    # ---- Map panel ---------------------------------------------------------
    for _, row in qc_df.iterrows():
        key = (str(row['flight_id']), int(row['line_id']), row['date'])
        gps = gps_dict.get(key)
        if gps is None or gps.empty:
            continue
        color = '#2ecc71' if row.get('pass_all') else '#e74c3c'
        ax_map.plot(gps['Xgps'].values, gps['Ygps'].values,
                    '-', color=color, linewidth=1.2, alpha=0.8)

    ax_map.set_xlabel('Longitude')
    ax_map.set_ylabel('Latitude')
    ax_map.set_title('Flight tracks')
    ax_map.set_aspect('equal')
    ax_map.grid(True, alpha=0.2)
    ax_map.add_patch(mpatches.Patch(color='#2ecc71', label='Pass'))
    ax_map.add_patch(mpatches.Patch(color='#e74c3c', label='Fail'))
    ax_map.legend(fontsize=8)

    # ---- Heatmap panel -----------------------------------------------------
    cols_present = [(c, lbl) for c, lbl in HEATMAP_COLS if c in qc_df.columns]
    col_keys  = [c   for c, _ in cols_present]
    col_lbls  = [lbl for _, lbl in cols_present]

    row_labels = [
        f"{r['flight_id']} · {int(r['line_id'])}"
        for _, r in qc_df.iterrows()
    ]

    # Build color matrix: 0=pass, 1=fail, 2=n/a
    mat = np.full((n_lines, len(col_keys)), 2.0)
    for i, (_, row) in enumerate(qc_df.iterrows()):
        for j, col in enumerate(col_keys):
            v = row.get(col)
            if v is True:
                mat[i, j] = 0.0
            elif v is False:
                mat[i, j] = 1.0

    norm = mcolors.BoundaryNorm([0, 0.5, 1.5, 2.5], _CMAP.N)
    im   = ax_heat.imshow(mat, cmap=_CMAP, norm=norm, aspect='auto')

    ax_heat.set_xticks(range(len(col_lbls)))
    ax_heat.set_xticklabels(col_lbls, rotation=40, ha='right', fontsize=8)
    ax_heat.set_yticks(range(n_lines))
    ax_heat.set_yticklabels(row_labels, fontsize=7)
    ax_heat.set_title('QC metrics  (green = pass, red = fail, gray = n/a)')

    # Annotate numeric values in cells
    value_cols = {
        'pass_altitude':    ('ralt_pct_outside',   '{:.0%}'),
        'pass_roll':        ('roll_pct_outside',    '{:.0%}'),
        'pass_pitch':       ('pitch_pct_outside',   '{:.0%}'),
        'pass_yaw':         ('yaw_std_deg',         '{:.1f}°'),
        'pass_cross_track': ('cross_track_max_m',   '{:.0f} m'),
        'pass_speed':       ('speed_pct_outside',   '{:.0%}'),
        'pass_spacing':     ('n_gaps',              '{:.0f} gaps'),
        'pass_mag_noise':   ('mag_noise_nT',        '{:.2f} nT'),
        'pass_mag_spike':   ('mag_spike_count',     '{:.0f}'),
        'pass_diurnal':     ('diurnal_range_nT',    '{:.0f} nT'),
    }
    for i, (_, row) in enumerate(qc_df.iterrows()):
        for j, col in enumerate(col_keys):
            val_col, fmt = value_cols.get(col, (None, ''))
            if val_col and val_col in qc_df.columns:
                v = row.get(val_col)
                if pd.notna(v):
                    txt = fmt.format(v)
                    ax_heat.text(j, i, txt, ha='center', va='center',
                                 fontsize=6, color='white' if mat[i, j] == 1 else 'black')

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    print(f"  Saved: {out_path}")
    plt.show()
    plt.close(fig)


# ---------------------------------------------------------------------------
# Detail interactive figure
# ---------------------------------------------------------------------------

def detail_figure(
    seg: pd.DataFrame,
    variable: str,
    thresholds: dict,
    survey_thresholds: dict,
    out_path: Path,
) -> None:
    """
    Interactive figure for one (flight_id, line_id) segment.

    Left panel : GPS track, points exceeding threshold in red.
    Right panel: variable profile vs along-track distance, slider controls threshold.

    Parameters
    ----------
    seg               : DataFrame for this segment (already filtered + sorted)
    variable          : column name to inspect (e.g. 'Ralt', 'Roll', 'Mag1')
    thresholds        : m1 section of project.yaml
    survey_thresholds : output of read_survey_thresholds()
    out_path          : where to save the PNG snapshot
    """
    from matplotlib.widgets import Slider

    seg = seg.sort_values('M3clk').dropna(subset=['Xgps', 'Ygps', variable])
    if seg.empty:
        print(f"  No valid data for variable '{variable}'.")
        return

    dist   = _along_track_km(seg)
    vals   = seg[variable].values
    lon    = seg['Xgps'].values
    lat    = seg['Ygps'].values
    flight = seg['flight_id'].iloc[0]
    lid    = int(seg['line_id'].iloc[0])
    label  = DETAIL_VARS.get(variable, (None, variable, None))[1]

    # Default threshold per variable
    _defaults = {
        'Ralt':  survey_thresholds.get('radar_max_m', 130.0),
        'Lalt':  survey_thresholds.get('radar_max_m', 130.0),
        'Roll':  thresholds.get('roll_max_deg', 5.0),
        'Pitch': thresholds.get('pitch_max_deg', 5.0),
        'Yaw':   thresholds.get('yaw_std_max_deg', 10.0),
    }
    init_thresh = _defaults.get(variable, float(np.nanmedian(vals)))
    above = vals > init_thresh

    fig, (ax_map, ax_prof) = plt.subplots(1, 2, figsize=(16, 7))
    plt.subplots_adjust(bottom=0.14, wspace=0.3)
    fig.suptitle(
        f"M1 QC — Flight {flight}  ·  Line {lid}  |  {label}",
        fontsize=12, fontweight='bold',
    )

    # Map
    colors = np.where(above, '#e74c3c', '#3498db')
    scat_map = ax_map.scatter(lon, lat, s=4, c=colors, linewidths=0)
    ax_map.set_xlabel('Longitude')
    ax_map.set_ylabel('Latitude')
    ax_map.set_title('GPS track  (red = exceeds threshold)')
    ax_map.set_aspect('equal')
    ax_map.grid(True, alpha=0.2)

    # Profile
    ax_prof.plot(dist, vals, color='#aac4dd', linewidth=0.7, zorder=1)
    bad_xy   = np.column_stack([dist[above], vals[above]]) if above.any() else np.empty((0, 2))
    scat_bad = ax_prof.scatter(
        bad_xy[:, 0] if bad_xy.size else [],
        bad_xy[:, 1] if bad_xy.size else [],
        s=10, c='#e74c3c', zorder=3,
    )
    thresh_line = ax_prof.axhline(
        init_thresh, color='#e74c3c', linestyle='--', linewidth=1.2,
    )
    # Reference lines for Ralt
    if variable in ('Ralt', 'Lalt'):
        rmin = survey_thresholds.get('radar_min_m')
        if rmin:
            ax_prof.axhline(rmin, color='darkorange', linestyle=':', linewidth=1,
                            label=f'RadarMin {rmin:.0f} m')
        ax_prof.legend(fontsize=8)

    n_bad = int(above.sum())
    ax_prof.set_xlabel('Along-track distance (km)')
    ax_prof.set_ylabel(label)
    ax_prof.set_title(f'{n_bad} / {len(vals)} points above {init_thresh:.1f}')
    ax_prof.grid(True, alpha=0.3)

    # Slider
    val_min = float(np.nanmin(vals))
    val_max = float(np.nanmax(vals))
    ax_sl   = plt.axes([0.15, 0.04, 0.7, 0.03])
    slider  = Slider(ax_sl, label, val_min, val_max, valinit=init_thresh)

    def _update(val):
        thresh    = slider.val
        above_new = vals > thresh
        scat_map.set_facecolors(np.where(above_new, '#e74c3c', '#3498db'))
        if above_new.any():
            scat_bad.set_offsets(np.column_stack([dist[above_new], vals[above_new]]))
            scat_bad.set_visible(True)
        else:
            scat_bad.set_offsets(np.empty((0, 2)))
            scat_bad.set_visible(False)
        thresh_line.set_ydata([thresh, thresh])
        ax_prof.set_title(f'{int(above_new.sum())} / {len(vals)} points above {thresh:.1f}')
        fig.canvas.draw_idle()

    slider.on_changed(_update)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    print(f"  Saved: {out_path}")
    plt.show()
    plt.close(fig)
