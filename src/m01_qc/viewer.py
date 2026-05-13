"""
Module 1 — Interactive QC viewer.

Click a flight line on the satellite map to load its QC profile panels
(altitude, Roll/Pitch, Yaw, magnetics with spike markers).

Usage
-----
    python -m src.m01_qc.viewer 24.04.2022 00428

Requirements
------------
    pip install matplotlib contextily
    (contextily is optional; plain WGS84 map is shown if missing)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m00_preparation.read_survey_nav import read_survey_thresholds

try:
    import contextily as ctx
    from pyproj import Transformer as _ProjTransformer
    _HAS_CTX = True
except ImportError:
    _HAS_CTX = False
    print("contextily not installed — satellite basemap disabled. Run: pip install contextily")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def _along_track_km(df: pd.DataFrame) -> np.ndarray:
    lon = np.radians(df['Xgps'].values)
    lat = np.radians(df['Ygps'].values)
    dlat = np.diff(lat)
    dlon = np.diff(lon)
    lat_mid = (lat[:-1] + lat[1:]) / 2
    d = 6371.0 * np.sqrt(dlat ** 2 + (np.cos(lat_mid) * dlon) ** 2)
    return np.concatenate([[0.0], np.cumsum(d)])


def _spike_mask(mag: np.ndarray, threshold_nT: float, window: int = 21) -> np.ndarray:
    """Boolean mask of isolated spikes relative to a rolling median."""
    s = pd.Series(mag)
    smoothed = s.rolling(window, center=True, min_periods=1).median().values
    return np.abs(mag - smoothed) > threshold_nT


# ---------------------------------------------------------------------------
# Viewer class
# ---------------------------------------------------------------------------

class InteractiveViewer:
    """
    Interactive QC viewer for one flight.

    Map panel (left): one pickable Line2D per survey line, satellite basemap.
    Profile panels (right): four stacked panels updated on each line click.
    """

    _COL_DEFAULT  = '#5b9bd5'
    _COL_SELECTED = '#e74c3c'
    _LW_DEFAULT   = 1.4
    _LW_SELECTED  = 2.8

    def __init__(
        self,
        df: pd.DataFrame,
        thresholds: dict,
        survey_thresholds: dict,
        flight_id: str,
        date: str,
    ) -> None:
        self.df               = df
        self.thresholds       = thresholds
        self.survey_thresholds = survey_thresholds
        self.flight_id        = flight_id
        self.date             = date

        on_line = (
            df[df['line_id'].notna() & df['line_valid']]
            .copy()
        )
        self.line_ids = sorted(on_line['line_id'].unique())
        self.segments = {
            lid: on_line[on_line['line_id'] == lid]
                 .sort_values('M3clk')
                 .dropna(subset=['Xgps', 'Ygps'])
            for lid in self.line_ids
        }

        if _HAS_CTX:
            self._wm = _ProjTransformer.from_crs('EPSG:4326', 'EPSG:3857', always_xy=True)

        self._selected = self.line_ids[0] if self.line_ids else None
        self._artists  = {}   # lid → Line2D on map

        self._build_figure()

    # ------------------------------------------------------------------
    # Figure construction
    # ------------------------------------------------------------------

    def _build_figure(self) -> None:
        fig = plt.figure(figsize=(19, 11))
        fig.suptitle(
            f"M1 Interactive QC — Flight {self.flight_id}  ·  {self.date}  "
            f"({len(self.line_ids)} lines)",
            fontsize=13, fontweight='bold',
        )

        gs = gridspec.GridSpec(
            4, 2,
            width_ratios=[1, 2.2],
            hspace=0.06,
            wspace=0.28,
            left=0.05, right=0.97, top=0.93, bottom=0.06,
        )

        self.ax_map  = fig.add_subplot(gs[:, 0])
        self.ax_ralt = fig.add_subplot(gs[0, 1])
        self.ax_att  = fig.add_subplot(gs[1, 1], sharex=self.ax_ralt)
        self.ax_yaw  = fig.add_subplot(gs[2, 1], sharex=self.ax_ralt)
        self.ax_mag  = fig.add_subplot(gs[3, 1], sharex=self.ax_ralt)

        plt.setp(self.ax_ralt.get_xticklabels(), visible=False)
        plt.setp(self.ax_att.get_xticklabels(),  visible=False)
        plt.setp(self.ax_yaw.get_xticklabels(),  visible=False)

        self.fig = fig
        self._draw_map()
        if self._selected is not None:
            self._update_profiles(self._selected)

        fig.canvas.mpl_connect('pick_event', self._on_pick)
        plt.show()

    def _draw_map(self) -> None:
        ax = self.ax_map

        for lid in self.line_ids:
            seg = self.segments[lid]
            if seg.empty:
                continue

            if _HAS_CTX:
                x, y = self._wm.transform(seg['Xgps'].values, seg['Ygps'].values)
            else:
                x, y = seg['Xgps'].values, seg['Ygps'].values

            selected = (lid == self._selected)
            (artist,) = ax.plot(
                x, y, '-',
                color=self._COL_SELECTED if selected else self._COL_DEFAULT,
                linewidth=self._LW_SELECTED if selected else self._LW_DEFAULT,
                alpha=0.9, picker=6,
            )
            self._artists[lid] = artist

        # Satellite basemap
        if _HAS_CTX:
            try:
                ctx.add_basemap(
                    ax,
                    crs='EPSG:3857',
                    source=ctx.providers.Esri.WorldImagery,
                    zoom='auto',
                    attribution=False,
                )
            except Exception as e:
                print(f"  Warning: basemap failed: {e}")
        else:
            ax.set_aspect('equal')
            ax.grid(True, alpha=0.2)
            ax.set_xlabel('Longitude', fontsize=8)
            ax.set_ylabel('Latitude',  fontsize=8)

        ax.tick_params(labelsize=7)
        ax.set_title('Click a line to inspect', fontsize=9)

        self._status = ax.text(
            0.02, 0.02,
            f"Line: {int(self._selected) if self._selected else '—'}",
            transform=ax.transAxes, fontsize=9, color='white',
            bbox=dict(facecolor='black', alpha=0.55, pad=3),
        )

    # ------------------------------------------------------------------
    # Pick event
    # ------------------------------------------------------------------

    def _on_pick(self, event) -> None:
        for lid, artist in self._artists.items():
            if artist is event.artist:
                self._select(lid)
                return

    def _select(self, lid) -> None:
        if self._selected is not None:
            old = self._artists.get(self._selected)
            if old:
                old.set_color(self._COL_DEFAULT)
                old.set_linewidth(self._LW_DEFAULT)

        self._selected = lid
        new = self._artists[lid]
        new.set_color(self._COL_SELECTED)
        new.set_linewidth(self._LW_SELECTED)
        self._status.set_text(f"Line: {int(lid)}")
        self.fig.canvas.draw_idle()

        self._update_profiles(lid)

    # ------------------------------------------------------------------
    # Profile panels
    # ------------------------------------------------------------------

    def _clear_profiles(self) -> None:
        for ax in (self.ax_ralt, self.ax_att, self.ax_yaw, self.ax_mag):
            ax.cla()
        plt.setp(self.ax_ralt.get_xticklabels(), visible=False)
        plt.setp(self.ax_att.get_xticklabels(),  visible=False)
        plt.setp(self.ax_yaw.get_xticklabels(),  visible=False)

    def _update_profiles(self, lid) -> None:
        self._clear_profiles()

        seg  = self.segments.get(lid)
        if seg is None or seg.empty:
            self.fig.canvas.draw_idle()
            return

        dist = _along_track_km(seg)
        thr  = self.thresholds
        sth  = self.survey_thresholds

        # ---- Radar altitude ------------------------------------------------
        ax = self.ax_ralt
        if 'Ralt' in seg.columns:
            ax.plot(dist, seg['Ralt'].values,
                    color='steelblue', linewidth=0.8, label='Ralt')
        if 'Lalt' in seg.columns:
            ax.plot(dist, seg['Lalt'].values,
                    color='teal', linewidth=0.8, label='Lalt', alpha=0.7)
        rmin = sth.get('radar_min_m')
        rmax = sth.get('radar_max_m')
        if rmin:
            ax.axhline(rmin, color='darkorange', linestyle='--', linewidth=1,
                       label=f'Min {rmin:.0f} m')
        if rmax:
            ax.axhline(rmax, color='red', linestyle='--', linewidth=1,
                       label=f'Max {rmax:.0f} m')
        ax.set_ylabel('Altitude (m)', fontsize=8)
        ax.legend(fontsize=7, loc='upper right', ncol=2)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)
        ax.set_title(f"Line {int(lid)}", fontsize=8, loc='right', pad=2)

        # ---- Roll + Pitch --------------------------------------------------
        ax = self.ax_att
        roll_lim  = thr.get('roll_max_deg',  5.0)
        pitch_lim = thr.get('pitch_max_deg', 5.0)
        for col, color in [('Roll', 'seagreen'), ('Pitch', 'mediumpurple')]:
            if col in seg.columns:
                ax.plot(dist, seg[col].values, color=color,
                        linewidth=0.8, label=col)
        ax.axhline( roll_lim, color='red', linestyle='--',
                    linewidth=0.8, label=f'±{roll_lim}°')
        ax.axhline(-roll_lim, color='red', linestyle='--', linewidth=0.8)
        ax.axhline(0, color='gray', linewidth=0.5)
        ax.set_ylabel('Roll / Pitch (°)', fontsize=8)
        ax.legend(fontsize=7, loc='upper right', ncol=3)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

        # ---- Yaw -----------------------------------------------------------
        ax = self.ax_yaw
        if 'Yaw' in seg.columns:
            ax.plot(dist, seg['Yaw'].values,
                    color='darkorange', linewidth=0.8, label='Yaw')
        ax.set_ylabel('Yaw (°)', fontsize=8)
        ax.legend(fontsize=7, loc='upper right')
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

        # ---- Mag1 + Mag2 + spikes ------------------------------------------
        ax = self.ax_mag
        spike_thresh = thr.get('mag_spike_max_nT', 100.0)
        for col, color in [('Mag1', 'navy'), ('Mag2', '#e67e22')]:
            if col in seg.columns:
                vals = seg[col].values
                ax.plot(dist, vals, color=color, linewidth=0.8,
                        label=col, alpha=0.85)
                if col == 'Mag1':
                    mask = _spike_mask(vals, spike_thresh)
                    if mask.any():
                        ax.scatter(
                            dist[mask], vals[mask],
                            color='red', s=20, zorder=5,
                            label=f'Spikes ({mask.sum()})',
                        )
        ax.set_ylabel('Magnetometer (nT)', fontsize=8)
        ax.set_xlabel('Along-track distance (km)', fontsize=8)
        ax.legend(fontsize=7, loc='upper right')
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

        self.fig.canvas.draw_idle()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def view(date: str, flight_id: str) -> None:
    cfg      = _load_config()
    campaign = cfg['campaign']['name']
    run_name = cfg['campaign']['run_name']
    nav_path = PROJECT_ROOT / cfg['campaign']['survey_nav_path']

    thresholds        = cfg.get('m1', {})
    survey_thresholds = read_survey_thresholds(nav_path)

    pq_path = (
        PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
        / date / f'flight_{flight_id}_prepared.parquet'
    )
    if not pq_path.exists():
        raise FileNotFoundError(
            f"Parquet not found: {pq_path}\nRun prepare.py first."
        )

    df = pd.read_parquet(pq_path)
    on_line = df[df['line_id'].notna() & df['line_valid']]
    if on_line.empty:
        print("No valid line data found in this parquet.")
        return

    n_lines = on_line['line_id'].nunique()
    print(f"Flight {flight_id}  ({date})  —  {n_lines} lines loaded.")
    print("Click a line on the map to inspect its QC profiles.")

    InteractiveViewer(df, thresholds, survey_thresholds, flight_id, date)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python -m src.m01_qc.viewer <date> <flight_id>")
        sys.exit(1)
    view(sys.argv[1], sys.argv[2].zfill(5))
