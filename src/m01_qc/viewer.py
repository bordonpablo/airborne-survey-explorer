"""
Module 1 — Interactive QC viewer.

All flight lines are plotted on a satellite basemap coloured by altitude
deviation from the survey target (green = on target, red = far from target).
Click a line — or use ← → keys — to update the four QC profile panels.

Usage
-----
    python -m src.m01_qc.viewer 24.04.2022 00428

Requirements
------------
    pip install contextily pyproj     (satellite basemap)
    contextily is optional; a plain lon/lat map is shown if unavailable.
"""

import sys
from pathlib import Path

# Backend must be set before any pyplot import.
import matplotlib as _mpl
for _b in ['TkAgg', 'Qt5Agg', 'Qt6Agg', 'WXAgg']:
    try:
        _mpl.use(_b)
        break
    except Exception:
        continue

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.colors as mcolors
from matplotlib.collections import LineCollection
from matplotlib.cm import ScalarMappable
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m00_preparation.read_survey_nav import read_survey_thresholds

try:
    import contextily as ctx
    from pyproj import Transformer as _Tr
    _HAS_CTX = True
except ImportError:
    _HAS_CTX = False
    print("contextily not installed — satellite basemap disabled.  pip install contextily")


# ---------------------------------------------------------------------------
# Small helpers
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
    s = pd.Series(mag)
    return np.abs(mag - s.rolling(window, center=True, min_periods=1).median().values) > threshold_nT


def _mag_noise_nT(mag: np.ndarray) -> float:
    if len(mag) < 3:
        return np.nan
    return float(np.std(np.diff(mag, n=2)) / np.sqrt(6))


def _dev_lc(x: np.ndarray, y: np.ndarray,
            deviation: np.ndarray,
            norm: mcolors.Normalize) -> LineCollection:
    """LineCollection coloured by altitude deviation (0 = green, high = red)."""
    pts  = np.column_stack([x, y])
    segs = np.stack([pts[:-1], pts[1:]], axis=1)
    lc   = LineCollection(segs, cmap='RdYlGn_r', norm=norm,
                           linewidth=2.0, zorder=2, alpha=0.9)
    lc.set_array(deviation[:-1])
    return lc


# ---------------------------------------------------------------------------
# Viewer
# ---------------------------------------------------------------------------

class QCViewer:

    _C_SEL  = '#ffffff'    # white highlight for selected line
    _C_GOOD = '#27ae60'    # green: within threshold
    _C_BAD  = '#e74c3c'    # red:   exceeds threshold
    _C_NEUT = '#888888'    # grey:  no data

    def __init__(
        self,
        df: pd.DataFrame,
        thresholds: dict,
        survey_thresholds: dict,
        nominal_alt: float,
        flight_id: str,
        date: str,
        qc_report: 'pd.DataFrame | None',
    ) -> None:
        self.df              = df
        self.thr             = thresholds
        self.sth             = survey_thresholds
        self.nominal_alt     = nominal_alt
        self.flight_id       = flight_id
        self.date            = date
        self.qc_report       = qc_report

        on_line = df[df['line_id'].notna() & df['line_valid']].copy()
        self.line_ids = sorted(on_line['line_id'].unique())
        self.segments = {
            lid: on_line[on_line['line_id'] == lid]
                 .sort_values('M3clk')
                 .dropna(subset=['Xgps', 'Ygps'])
            for lid in self.line_ids
        }

        # Deviation norm: 0 = on target (green), ≥ 95th-percentile deviation = full red
        all_devs = []
        for lid in self.line_ids:
            seg = self.segments[lid]
            if 'Ralt' in seg.columns:
                all_devs.extend(
                    np.abs(seg['Ralt'].dropna().values - nominal_alt).tolist()
                )
        max_dev = float(max(np.percentile(all_devs, 95), 20.0)) if all_devs else 30.0
        self._dev_norm = mcolors.Normalize(vmin=0, vmax=max_dev)

        if _HAS_CTX:
            self._wm = _Tr.from_crs('EPSG:4326', 'EPSG:3857', always_xy=True)

        self._selected    = self.line_ids[0] if self.line_ids else None
        self._pick_arts: dict = {}
        self._sel_art         = None

        self._build_figure()

    # ------------------------------------------------------------------
    # Figure construction
    # ------------------------------------------------------------------

    def _build_figure(self) -> None:
        self.fig = plt.figure(figsize=(22, 11))

        gs = gridspec.GridSpec(
            4, 2,
            width_ratios=[1.0, 1.55],
            hspace=0.05, wspace=0.30,
            left=0.03, right=0.99, top=0.93, bottom=0.07,
        )

        self.ax_map  = self.fig.add_subplot(gs[:, 0])
        self.ax_ralt = self.fig.add_subplot(gs[0, 1])
        self.ax_att  = self.fig.add_subplot(gs[1, 1], sharex=self.ax_ralt)
        self.ax_yaw  = self.fig.add_subplot(gs[2, 1], sharex=self.ax_ralt)
        self.ax_mag  = self.fig.add_subplot(gs[3, 1], sharex=self.ax_ralt)

        plt.setp(self.ax_ralt.get_xticklabels(), visible=False)
        plt.setp(self.ax_att.get_xticklabels(),  visible=False)
        plt.setp(self.ax_yaw.get_xticklabels(),  visible=False)

        self._draw_map()
        self._refresh_title()

        if self._selected is not None:
            self._update_profiles(self._selected)

        self.fig.canvas.mpl_connect('pick_event',      self._on_pick)
        self.fig.canvas.mpl_connect('key_press_event', self._on_key)
        plt.show(block=True)

    # ------------------------------------------------------------------
    # Map panel
    # ------------------------------------------------------------------

    def _draw_map(self) -> None:
        ax = self.ax_map

        # 1. Draw altitude-deviation heatmap lines + invisible pick lines
        for lid in self.line_ids:
            seg = self.segments[lid]
            if seg.empty:
                continue

            if _HAS_CTX:
                x, y = self._wm.transform(seg['Xgps'].values, seg['Ygps'].values)
            else:
                x, y = seg['Xgps'].values, seg['Ygps'].values

            if 'Ralt' in seg.columns:
                dev = np.abs(
                    seg['Ralt'].fillna(self.nominal_alt).values - self.nominal_alt
                )
                ax.add_collection(_dev_lc(x, y, dev, self._dev_norm))
            else:
                ax.plot(x, y, '-', color='#aaaaaa', linewidth=1.5, zorder=2)

            # Invisible line for pick events (must be a real Line2D, not Collection)
            (art,) = ax.plot(
                x, y, '-',
                color='white', linewidth=7, alpha=0.0,
                picker=8, zorder=5,
            )
            self._pick_arts[lid] = art

        # 2. Trigger autoscale so axis limits reflect the data before fetching tiles
        ax.autoscale_view()

        # 3. Satellite basemap (rendered at zorder=0, behind the lines)
        if _HAS_CTX:
            try:
                ctx.add_basemap(
                    ax,
                    crs='EPSG:3857',
                    source=ctx.providers.Esri.WorldImagery,
                    zoom='auto',
                    attribution=False,
                    zorder=0,
                )
            except Exception as e:
                print(f"  Basemap warning: {e}")
                ax.set_facecolor('#1a2a3a')
        else:
            ax.set_facecolor('#1a2a3a')
            ax.set_aspect('equal')

        # 4. Selected line highlight on top
        self._draw_sel_highlight()

        # 5. Colorbar below the map
        sm = ScalarMappable(cmap='RdYlGn_r', norm=self._dev_norm)
        sm.set_array([])
        cbar = self.fig.colorbar(
            sm, ax=ax,
            orientation='horizontal',
            fraction=0.035, pad=0.01, aspect=28,
        )
        nom  = self.nominal_alt
        rmin = self.sth.get('radar_min_m')
        rmax = self.sth.get('radar_max_m')
        cbar.set_label(
            f"Altitud: desviación del target {nom:.0f} m  (m)",
            fontsize=8,
        )
        cbar.ax.tick_params(labelsize=7)
        # Mark tolerance thresholds on colorbar
        for ref in [rmin, rmax]:
            if ref is not None:
                dev_at_threshold = abs(ref - nom)
                if 0 < dev_at_threshold <= self._dev_norm.vmax:
                    cbar.ax.axvline(dev_at_threshold,
                                    color='darkorange', lw=1.5, linestyle='--')

        ax.tick_params(left=False, bottom=False,
                       labelleft=False, labelbottom=False)
        ax.set_title(
            'Heatmap altitud  (verde = target · rojo = lejos del target)\n'
            'Click en una línea para ver los perfiles',
            fontsize=8, pad=4,
        )

    def _draw_sel_highlight(self) -> None:
        """Draw / redraw the white outline for the currently selected line."""
        if self._sel_art is not None:
            try:
                self._sel_art.remove()
            except Exception:
                pass
            self._sel_art = None

        if self._selected is None:
            return

        seg = self.segments.get(self._selected)
        if seg is None or seg.empty:
            return

        if _HAS_CTX:
            xs, ys = self._wm.transform(seg['Xgps'].values, seg['Ygps'].values)
        else:
            xs, ys = seg['Xgps'].values, seg['Ygps'].values

        (self._sel_art,) = self.ax_map.plot(
            xs, ys, '-',
            color=self._C_SEL, linewidth=3.5,
            alpha=0.95, zorder=4,
        )

    # ------------------------------------------------------------------
    # Title
    # ------------------------------------------------------------------

    def _refresh_title(self) -> None:
        sel_str = f"  ·  Línea {int(self._selected)}" if self._selected is not None else ''
        self.fig.suptitle(
            f"M1 QC  —  Vuelo {self.flight_id}  ·  {self.date}"
            f"  ({len(self.line_ids)} líneas){sel_str}"
            f"     ←  →  para navegar",
            fontsize=11, fontweight='bold',
        )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_pick(self, event) -> None:
        for lid, art in self._pick_arts.items():
            if art is event.artist:
                self._select(lid)
                return

    def _on_key(self, event) -> None:
        if not self.line_ids or self._selected is None:
            return
        try:
            idx = self.line_ids.index(self._selected)
        except ValueError:
            idx = 0
        if event.key == 'right':
            idx = (idx + 1) % len(self.line_ids)
        elif event.key == 'left':
            idx = (idx - 1) % len(self.line_ids)
        else:
            return
        self._select(self.line_ids[idx])

    def _select(self, lid) -> None:
        self._selected = lid
        self._draw_sel_highlight()
        self._refresh_title()
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

    def _qr(self, lid) -> 'pd.Series | None':
        if self.qc_report is None or self.qc_report.empty:
            return None
        rows = self.qc_report[self.qc_report['line_id'] == int(lid)]
        return rows.iloc[0] if not rows.empty else None

    @staticmethod
    def _val_color(value, threshold: float, higher_is_bad: bool = True) -> str:
        """Green if value is within threshold, red if it exceeds it."""
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return QCViewer._C_NEUT
        exceeded = value > threshold if higher_is_bad else value < threshold
        return QCViewer._C_BAD if exceeded else QCViewer._C_GOOD

    def _panel_metric(self, ax, text: str, color: str,
                      x: float = 1.0, y: float = 1.01,
                      ha: str = 'right') -> None:
        """Place a metric annotation just above the top-right of a panel."""
        ax.text(x, y, text,
                transform=ax.transAxes, fontsize=7.5,
                ha=ha, va='bottom', color=color,
                bbox=dict(facecolor='white', edgecolor='none',
                          alpha=0.75, pad=1.5, boxstyle='round'))

    def _update_profiles(self, lid) -> None:
        self._clear_profiles()
        seg = self.segments.get(lid)
        if seg is None or seg.empty:
            self.fig.canvas.draw_idle()
            return

        dist    = _along_track_km(seg)
        thr     = self.thr
        sth     = self.sth
        qr      = self._qr(lid)
        nom     = self.nominal_alt
        pct_max = thr.get('pct_outside_max', 0.20)

        # ==== Panel 1 — Radar altitude =====================================
        ax = self.ax_ralt
        rmin = sth.get('radar_min_m', nom - 30)
        rmax = sth.get('radar_max_m', nom + 30)

        if 'Ralt' in seg.columns:
            ralt = seg['Ralt'].values
            # Green acceptance band
            ax.axhspan(rmin, rmax, alpha=0.10, color='#27ae60', zorder=0)
            # Red fill where out of range
            ax.fill_between(dist, ralt, rmin,
                             where=ralt < rmin, alpha=0.35,
                             color='#e74c3c', interpolate=True, zorder=1)
            ax.fill_between(dist, ralt, rmax,
                             where=ralt > rmax, alpha=0.35,
                             color='#e74c3c', interpolate=True, zorder=1)
            ax.plot(dist, ralt, color='#2980b9', lw=0.9, label='Ralt', zorder=2)

        if 'Lalt' in seg.columns:
            ax.plot(dist, seg['Lalt'].values, color='#16a085',
                    lw=0.9, label='Lalt', alpha=0.85, zorder=2)

        ax.axhline(nom,  color='#27ae60', ls='-',  lw=1.3,
                   label=f'Target {nom:.0f} m', zorder=3)
        ax.axhline(rmin, color='#e67e22', ls='--', lw=1.0,
                   label=f'Min {rmin:.0f} m', zorder=3)
        ax.axhline(rmax, color='#e67e22', ls='--', lw=1.0,
                   label=f'Max {rmax:.0f} m', zorder=3)

        if qr is not None:
            mean = qr.get('ralt_mean_m')
            pct  = qr.get('ralt_pct_outside', 0.0)
            if mean is not None and not (isinstance(mean, float) and np.isnan(mean)):
                c = self._C_BAD if pct > pct_max else self._C_GOOD
                self._panel_metric(ax,
                    f"media={mean:.0f} m  |  fuera de banda={pct:.0%}", c)

        ax.set_ylabel('Altitud (m)', fontsize=8)
        ax.legend(fontsize=7, loc='upper left', ncol=3,
                  framealpha=0.6, labelspacing=0.15, borderpad=0.4)
        ax.grid(True, alpha=0.25, linewidth=0.5)
        ax.tick_params(labelsize=7)

        # ==== Panel 2 — Roll + Pitch ========================================
        ax = self.ax_att
        roll_lim  = thr.get('roll_max_deg',  5.0)
        pitch_lim = thr.get('pitch_max_deg', 5.0)

        ax.axhspan(-roll_lim, roll_lim, alpha=0.08, color='#27ae60', zorder=0)
        ax.axhline(0, color='#aaa', lw=0.5, zorder=1)

        for col, color in [('Roll', '#27ae60'), ('Pitch', '#8e44ad')]:
            if col in seg.columns:
                ax.plot(dist, seg[col].values, color=color, lw=0.9,
                        label=col, zorder=2)

        for lim, color, ls in [
            (+roll_lim,  '#e74c3c', '--'),
            (-roll_lim,  '#e74c3c', '--'),
            (+pitch_lim, '#8e44ad', ':'),
            (-pitch_lim, '#8e44ad', ':'),
        ]:
            ax.axhline(lim, color=color, ls=ls, lw=0.9, alpha=0.8, zorder=3)

        if qr is not None:
            parts = []
            for key, lbl, lim in [
                ('roll_pct_outside',  f'Roll>{roll_lim}°',   roll_lim),
                ('pitch_pct_outside', f'Pitch>{pitch_lim}°', pitch_lim),
            ]:
                v = qr.get(key)
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    c = self._C_BAD if v > pct_max else self._C_GOOD
                    parts.append((f"{lbl}: {v:.0%}", c))
            if parts:
                x_off = 1.0
                for text, color in reversed(parts):
                    self._panel_metric(ax, text, color, x=x_off)
                    x_off -= 0.38

        ax.set_ylabel('Roll / Pitch (°)', fontsize=8)
        ax.legend(fontsize=7, loc='upper left', ncol=2,
                  framealpha=0.6, labelspacing=0.15, borderpad=0.4)
        ax.grid(True, alpha=0.25, linewidth=0.5)
        ax.tick_params(labelsize=7)

        # ==== Panel 3 — Yaw =================================================
        ax = self.ax_yaw
        if 'Yaw' in seg.columns:
            ax.plot(dist, seg['Yaw'].values, color='#e67e22',
                    lw=0.9, label='Yaw', zorder=2)
        ax.axhline(0, color='#aaa', lw=0.5)

        if qr is not None:
            std = qr.get('yaw_std_deg')
            lim = thr.get('yaw_std_max_deg', 10.0)
            if std is not None and not (isinstance(std, float) and np.isnan(std)):
                c = self._C_BAD if std > lim else self._C_GOOD
                self._panel_metric(ax, f"std={std:.1f}°  (límite={lim:.0f}°)", c)

        ax.set_ylabel('Yaw (°)', fontsize=8)
        ax.legend(fontsize=7, loc='upper left', framealpha=0.6)
        ax.grid(True, alpha=0.25, linewidth=0.5)
        ax.tick_params(labelsize=7)

        # ==== Panel 4 — Magnéticos ==========================================
        ax = self.ax_mag
        spike_thresh = thr.get('mag_spike_max_nT', 100.0)
        noise_thresh = thr.get('mag_noise_max_nT',   5.0)

        for col, color in [('Mag1', '#2980b9'), ('Mag2', '#c0392b')]:
            if col in seg.columns:
                vals = seg[col].values
                ax.plot(dist, vals, color=color, lw=0.9,
                        label=col, alpha=0.85, zorder=2)

                if col == 'Mag1':
                    mask     = _spike_mask(vals, spike_thresh)
                    n_spikes = int(mask.sum())
                    if n_spikes > 0:
                        ax.scatter(dist[mask], vals[mask],
                                   color='#f39c12', s=40, zorder=5,
                                   label=f'Picos >{spike_thresh:.0f} nT ({n_spikes})')

                    noise = _mag_noise_nT(vals)
                    ann_items = []
                    if not np.isnan(noise):
                        c = self._C_BAD if noise > noise_thresh else self._C_GOOD
                        ann_items.append(
                            (f"ruido={noise:.2f} nT (lím={noise_thresh})", c))
                    c_sp = self._C_BAD if n_spikes > 0 else self._C_GOOD
                    ann_items.append((f"picos={n_spikes}", c_sp))

                    x_off = 1.0
                    for text, color in reversed(ann_items):
                        self._panel_metric(ax, text, color, x=x_off)
                        x_off -= 0.38

        # Cross-track + gaps from QC report (bottom-left of panel)
        if qr is not None:
            extra = []
            ct  = qr.get('cross_track_max_m')
            lct = thr.get('line_tolerance_m', 300.0)
            if ct is not None and not (isinstance(ct, float) and np.isnan(ct)):
                c = self._C_BAD if ct > lct else self._C_GOOD
                extra.append((f"desvío_transversal max={ct:.0f} m", c))
            ng = qr.get('n_gaps')
            if ng is not None and not (isinstance(ng, float) and np.isnan(ng)):
                c = self._C_BAD if int(ng) > 0 else self._C_GOOD
                extra.append((f"gaps={int(ng)}", c))
            for i, (text, color) in enumerate(extra):
                ax.text(0.01, 0.97 - i * 0.10, text,
                        transform=ax.transAxes, fontsize=7.5,
                        va='top', color=color)

        ax.set_ylabel('Magnetómetro (nT)', fontsize=8)
        ax.set_xlabel('Distancia a lo largo de la traza (km)', fontsize=8)
        ax.legend(fontsize=7, loc='upper right', framealpha=0.6)
        ax.grid(True, alpha=0.25, linewidth=0.5)
        ax.tick_params(labelsize=7)

        self.fig.canvas.draw_idle()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _find_qc_report(out_qc: Path, date: str, flight_id: str) -> 'Path | None':
    candidates = [
        out_qc / f"{date}_{flight_id}_qc_report.csv",
        out_qc / f"{date}_qc_report.csv",
        out_qc / "qc_report.csv",
    ]
    for p in candidates:
        if p.exists():
            return p
    if out_qc.exists():
        for p in sorted(out_qc.glob(f"{date}*qc_report.csv")):
            return p
    return None


def view(date: str, flight_id: str) -> None:
    cfg         = _load_config()
    campaign    = cfg['campaign']['name']
    run_name    = cfg['campaign']['run_name']
    nav_path    = PROJECT_ROOT / cfg['campaign']['survey_nav_path']
    nominal_alt = cfg['survey_design']['nominal_altitude_m']

    thresholds        = cfg.get('m1', {})
    survey_thresholds = read_survey_thresholds(nav_path)

    pq_path = (
        PROJECT_ROOT / 'data' / 'interim' / campaign / run_name
        / date / f'flight_{flight_id}_prepared.parquet'
    )
    if not pq_path.exists():
        raise FileNotFoundError(
            f"Parquet no encontrado: {pq_path}\n"
            "Ejecutá primero:  python -m src.m00_preparation.prepare"
        )

    df = pd.read_parquet(pq_path)
    if df[df['line_id'].notna() & df['line_valid']].empty:
        print("No hay datos válidos de líneas en este parquet.")
        return

    # QC report para anotaciones (opcional)
    qc_report = None
    out_qc    = PROJECT_ROOT / 'outputs' / campaign / run_name / 'qc'
    rpt_path  = _find_qc_report(out_qc, date, flight_id)
    if rpt_path:
        try:
            qc_report = pd.read_csv(rpt_path, dtype={'flight_id': str, 'line_id': int})
            qc_report = qc_report[qc_report['flight_id'] == flight_id].reset_index(drop=True)
            print(f"  Reporte QC: {rpt_path.name}  ({len(qc_report)} líneas)")
        except Exception as e:
            print(f"  Advertencia: no se pudo cargar el reporte QC: {e}")
    else:
        print(
            "  No se encontró reporte QC — ejecutá "
            "python -m src.m01_qc.run primero para ver anotaciones de métricas."
        )

    n_lines = df[df['line_id'].notna() & df['line_valid']]['line_id'].nunique()
    print(f"Vuelo {flight_id}  ({date})  —  {n_lines} líneas.  "
          "Click en una línea para inspeccionar.")

    QCViewer(df, thresholds, survey_thresholds, nominal_alt,
             flight_id, date, qc_report)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Uso: python -m src.m01_qc.viewer <fecha> <flight_id>")
        sys.exit(1)
    view(sys.argv[1], sys.argv[2].zfill(5))
