"""
Module 3 — SPC inspection: QC visualization before GammAn import.

Generates one multi-panel figure per flight with five panels:

  ① Altimetría (Sralt) — perfil de altura del vuelo y calidad del suavizado.
     Marca el umbral máximo de radiometría; los tramos por encima producirán
     concentraciones degradadas después de FSA.

  ② Presión y temperatura (Sbaro, Stemp) — suavizado pre-GammAn.
     GammAn usa estos valores para la corrección de altura (HSTP).
     Un suavizado insuficiente migra ruido a las concentraciones finales.

  ③ Fracción de live time (Slive / Sreal) — indicador de dead-time del detector.
     Valores < 0.99 significan que el detector perdió pulsos por alta tasa de
     conteo. GammAn no puede recuperar pulsos perdidos → concentraciones
     subestimadas en esas zonas.

  ④ Estabilidad de ganancia (Sa0, Sa1) — parámetros de calibración espectral.
     Una deriva sostenida indica inestabilidad de ganancia del cristal CsI
     (típicamente por cambios de temperatura). GammAn compensa esto durante
     la estabilización espectral, pero una deriva grande dificulta el proceso.

  ⑤ Cuentas brutas por ventana IAEA (Sk, Su, Sth) — primera vista geológica.
     No son concentraciones FSA: son cuentas de ventana simples aplicadas en
     tiempo real, ruidosas y sin corrección de altura ni radón. Sirven para
     verificar que el detector registró señal y para una inspección visual
     de la variabilidad geológica antes de entrar a GammAn.

También genera un mapa de campaña con la tasa de conteo total (Srate).

Usage
-----
    python -m src.m03_radiometry.inspect_spc                  # toda la campaña
    python -m src.m03_radiometry.inspect_spc 02.05.2022       # un día
    python -m src.m03_radiometry.inspect_spc 02.05.2022 00447 # un vuelo
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import yaml

matplotlib.rcParams['figure.max_open_warning'] = 0

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.m03_radiometry.read_spc import read_spc
from src.m03_radiometry.smooth_env import smooth_env


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def _minutes(m2clk: pd.Series) -> pd.Series:
    """M2clk (ms) → minutes elapsed since first sample."""
    return (m2clk - m2clk.iloc[0]) / 60_000.0


def _on_line_mask(swayp: pd.Series) -> pd.Series:
    """True when Swayp is non-blank (aircraft is on a named survey line)."""
    return swayp.astype(str).str.strip() != ''


def _shade_on_line(ax, t: pd.Series, on_line: pd.Series) -> None:
    """
    Shade x-axis spans where the aircraft is on a survey line.
    Green tint makes it easy to separate production data from transits.
    """
    t   = t.reset_index(drop=True)
    on  = on_line.astype(int).reset_index(drop=True)
    chg = on.diff().fillna(on.iloc[0])

    starts = t[chg == 1].values
    ends   = t[chg == -1].values

    if on.iloc[0] == 1:
        starts = np.concatenate([[t.iloc[0]], starts])
    if on.iloc[-1] == 1:
        ends = np.concatenate([ends, [t.iloc[-1]]])

    for s, e in zip(starts, ends):
        ax.axvspan(s, e, alpha=0.10, color='tab:green', lw=0)


def plot_flight(
    df: pd.DataFrame,
    flight_id: str,
    date: str,
    out_path: Path,
    window_sralt: int,
    window_env: int,
    max_alt_m: float,
) -> None:
    """
    Five-panel QC figure for one flight.

    Parameters
    ----------
    df          : DataFrame from read_spc
    flight_id   : e.g. '00447'
    date        : e.g. '02.05.2022'
    out_path    : output PNG path
    window_sralt: smoothing window for Sralt (samples)
    window_env  : smoothing window for Sbaro / Stemp
    max_alt_m   : maximum usable altitude for radiometry — drawn as reference line
    """
    df  = smooth_env(df, window_sralt, window_env)
    t   = _minutes(df['M2clk'])
    on  = _on_line_mask(df['Swayp'])
    t_max = t.max()

    fig = plt.figure(figsize=(16, 17))
    gs  = fig.add_gridspec(
        3, 2,
        height_ratios=[1.0, 1.0, 1.2],
        hspace=0.52, wspace=0.32,
        left=0.07, right=0.97, top=0.91, bottom=0.05,
    )
    ax_alt = fig.add_subplot(gs[0, 0])
    ax_env = fig.add_subplot(gs[0, 1])
    ax_lt  = fig.add_subplot(gs[1, 0])
    ax_sa0 = fig.add_subplot(gs[1, 1])
    ax_win = fig.add_subplot(gs[2, :])

    # ── ① Altimetría ──────────────────────────────────────────────────────────
    ax_alt.plot(t, df['Sralt'],        color='0.50', lw=1.0, label='Sralt crudo')
    ax_alt.plot(t, df['Sralt_smooth'], color='tab:blue', lw=1.3,
                label=f'Sralt suavizado  (ventana {window_sralt} s)')
    ax_alt.axhline(max_alt_m, color='tab:red', ls='--', lw=1.1,
                   label=f'Umbral máximo radiometría  ({max_alt_m:.0f} m)')
    above = df['Sralt_smooth'] > max_alt_m
    ax_alt.fill_between(t, df['Sralt_smooth'], max_alt_m,
                        where=above, color='tab:red', alpha=0.18, lw=0,
                        label=f'{above.mean()*100:.1f}% por encima del umbral')
    _shade_on_line(ax_alt, t, on)
    ax_alt.set_xlim(0, t_max)
    ax_alt.set_xlabel('Tiempo desde inicio (min)', fontsize=8)
    ax_alt.set_ylabel('Altura AGL  (m)', fontsize=8)
    ax_alt.set_title(
        '① Altimetría — Sralt crudo vs. suavizado\n'
        'Rojo = tramos sobre umbral → FSA menos confiable en esas zonas.',
        fontsize=8, loc='left',
    )
    ax_alt.legend(fontsize=6.5, loc='upper right')
    ax_alt.grid(alpha=0.3)
    ax_alt.tick_params(labelsize=7)

    # ── ② Presión y temperatura ───────────────────────────────────────────────
    ax2b = ax_env.twinx()
    ax_env.plot(t, df['Sbaro'],        color='tab:blue', alpha=0.60, lw=1.0, label='Sbaro crudo')
    ax_env.plot(t, df['Sbaro_smooth'], color='tab:blue', lw=2.2,
                label=f'Sbaro suavizado  ({window_env} s)')
    ax2b.plot(t, df['Stemp'],          color='tab:orange', alpha=0.60, lw=1.0, label='Stemp crudo')
    ax2b.plot(t, df['Stemp_smooth'],   color='tab:orange', lw=2.2,
              label=f'Stemp suavizado  ({window_env} s)')
    _shade_on_line(ax_env, t, on)
    ax_env.set_xlim(0, t_max)
    ax_env.set_xlabel('Tiempo desde inicio (min)', fontsize=8)
    ax_env.set_ylabel('Presión  (mBar)', fontsize=8, color='tab:blue')
    ax2b.set_ylabel('Temperatura  (°C)', fontsize=8, color='tab:orange')
    ax_env.tick_params(axis='y', labelcolor='tab:blue', labelsize=7)
    ax2b.tick_params(axis='y', labelcolor='tab:orange', labelsize=7)
    ax_env.tick_params(axis='x', labelsize=7)
    ax_env.set_title(
        '② Presión (Sbaro) y temperatura (Stemp) — suavizado pre-GammAn\n'
        'GammAn los usa para la corrección de altura y HSTP.',
        fontsize=8, loc='left',
    )
    # combined legend
    lines_a, labs_a = ax_env.get_legend_handles_labels()
    lines_b, labs_b = ax2b.get_legend_handles_labels()
    ax_env.legend(lines_a + lines_b, labs_a + labs_b, fontsize=6.5, loc='lower right')
    ax_env.grid(alpha=0.3)

    # ── ③ Fracción de live time ───────────────────────────────────────────────
    lt = df['livetime_frac'].clip(0, 1)
    ax_lt.plot(t, lt, color='tab:green', lw=0.8)
    ax_lt.axhline(0.99, color='tab:red', ls='--', lw=1.1,
                  label='Umbral mínimo  (0.99)')
    ax_lt.fill_between(t, lt, 0.99, where=(lt < 0.99),
                       color='tab:red', alpha=0.30, lw=0,
                       label='Dead-time elevado')
    _shade_on_line(ax_lt, t, on)
    lo = max(0.90, lt.min() - 0.005)
    ax_lt.set_ylim(lo, 1.005)
    ax_lt.set_xlim(0, t_max)
    ax_lt.set_xlabel('Tiempo desde inicio (min)', fontsize=8)
    ax_lt.set_ylabel('Slive / Sreal', fontsize=8)
    ax_lt.set_title(
        '③ Fracción de live time  (Slive / Sreal)\n'
        'Caídas bajo 0.99 = pulsos perdidos → concentraciones subestimadas.',
        fontsize=8, loc='left',
    )
    ax_lt.legend(fontsize=6.5)
    ax_lt.grid(alpha=0.3)
    ax_lt.tick_params(labelsize=7)

    # ── ④ Estabilidad de ganancia ─────────────────────────────────────────────
    ax_sa0.plot(t, df['Sa0'], color='tab:purple', lw=0.8, label='Sa0 (ganancia)')
    ax_sa0.plot(t, df['Sa1'], color='tab:cyan',   lw=0.8, alpha=0.8, label='Sa1 (offset)')
    mean0, std0 = df['Sa0'].mean(), df['Sa0'].std()
    ax_sa0.axhline(mean0, color='tab:purple', ls='--', lw=0.8, alpha=0.5)
    ax_sa0.fill_between(t,
                        mean0 - 2 * std0, mean0 + 2 * std0,
                        alpha=0.12, color='tab:purple', label='±2σ  Sa0')
    _shade_on_line(ax_sa0, t, on)
    ax_sa0.set_xlim(0, t_max)
    ax_sa0.set_xlabel('Tiempo desde inicio (min)', fontsize=8)
    ax_sa0.set_ylabel('Coef. estabilización espectral', fontsize=8)
    ax_sa0.set_title(
        '④ Estabilidad de ganancia  (Sa0, Sa1)\n'
        'Deriva indica cambio de ganancia del CsI; GammAn deberá compensarla.',
        fontsize=8, loc='left',
    )
    ax_sa0.legend(fontsize=6.5)
    ax_sa0.grid(alpha=0.3)
    ax_sa0.tick_params(labelsize=7)

    # ── ⑤ Cuentas brutas por ventana IAEA ─────────────────────────────────────
    ax_win.plot(t, df['Sk'],  color='tab:blue',   lw=0.9, label='K   (Sk, cps)')
    ax_win.plot(t, df['Su'],  color='tab:orange',  lw=0.9, label='U   (Su, cps)')
    ax_win.plot(t, df['Sth'], color='tab:green',   lw=0.9, label='Th  (Sth, cps)')
    _shade_on_line(ax_win, t, on)
    ax_win.set_xlim(0, t_max)
    ax_win.set_xlabel('Tiempo desde inicio (min)', fontsize=8)
    ax_win.set_ylabel('Cuentas por ventana IAEA  (cps)', fontsize=8)
    ax_win.set_title(
        '⑤ Cuentas brutas — Sk (K), Su (U), Sth (Th)\n'
        'NO son concentraciones FSA. Primera vista del señal geológico, sin corrección de altura ni radón.\n'
        'Verde sombreado = tramos en línea de producción.',
        fontsize=8, loc='left',
    )
    ax_win.legend(fontsize=8)
    ax_win.grid(alpha=0.3)
    ax_win.tick_params(labelsize=7)

    # ── Suptitle con estadísticas del vuelo ───────────────────────────────────
    pct_above = (df['Sralt_smooth'] > max_alt_m).mean() * 100
    lt_min    = lt.min()
    fig.suptitle(
        f'SPC — Vuelo {flight_id}  |  {date}\n'
        f'{len(df):,} muestras  ·  {t_max:.1f} min  ·  '
        f'Srate media: {df["Srate"].mean():.0f} cps  ·  '
        f'{pct_above:.1f}% sobre umbral altimétrico ({max_alt_m:.0f} m)  ·  '
        f'Live time mín: {lt_min:.4f}',
        fontsize=9.5, weight='bold',
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'    → {out_path.relative_to(PROJECT_ROOT)}')


def plot_campaign_map(
    all_data: list[tuple[str, pd.DataFrame]],
    out_path: Path,
) -> None:
    """
    Scatter map of total count rate (Srate) for the full campaign.

    Provides a spatial overview: survey coverage and detector activity.
    High Srate over a geological body hints at elevated radioactivity even
    before FSA processing.
    """
    combined = pd.concat([df for _, df in all_data], ignore_index=True)
    valid    = combined.dropna(subset=['Sxgps', 'Sygps', 'Srate'])

    if valid.empty:
        return

    fig, ax = plt.subplots(figsize=(10, 8))
    p2, p98 = np.nanpercentile(valid['Srate'], [2, 98])
    sc = ax.scatter(
        valid['Sxgps'], valid['Sygps'],
        c=valid['Srate'],
        s=0.5, cmap='plasma',
        vmin=p2, vmax=p98,
        rasterized=True,
    )
    cb = plt.colorbar(sc, ax=ax, shrink=0.8)
    cb.set_label('Srate  (cps)', fontsize=9)

    lat_mean = valid['Sygps'].mean()
    ax.set_aspect(1.0 / np.cos(np.radians(lat_mean)))
    ax.set_xlabel('Longitud  (°)', fontsize=9)
    ax.set_ylabel('Latitud  (°)', fontsize=9)
    ax.set_title(
        f'Mapa de campaña — Tasa de conteo total  Srate  (cps)\n'
        f'{len(all_data)} vuelos  ·  {len(valid):,} muestras  ·  '
        f'rango P2–P98: {p2:.0f}–{p98:.0f} cps\n'
        'Primera vista espacial: cobertura y actividad del detector antes de FSA.',
        fontsize=9,
    )
    ax.grid(alpha=0.3)
    ax.tick_params(labelsize=8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'    → {out_path.relative_to(PROJECT_ROOT)}')


def plot_smoothing_qc(
    df: pd.DataFrame,
    flight_id: str,
    date: str,
    out_path: Path,
    window_sralt: int,
    window_env: int,
) -> None:
    """
    Dedicated 3-panel figure: raw vs. smoothed for Sralt, Sbaro, Stemp.

    X-axis is trimmed to the survey period (first to last on-line sample
    ± 10 min buffer) so the scale is not dominated by ground initialization.
    Y-axis uses P2–P98 limits to prevent outliers from compressing the signal.

    This is the figure to use for deciding whether the smoothing window is
    appropriate — not too short (leaves noise) and not too long (distorts trends).
    """
    df  = smooth_env(df, window_sralt, window_env)
    t   = _minutes(df['M2clk'])
    on  = _on_line_mask(df['Swayp'])

    # Trim x-axis to survey period ± 10 min
    on_idx = np.where(on.values)[0]
    if len(on_idx) > 0:
        x_lo = max(0.0,    t.values[on_idx[0]]  - 10.0)
        x_hi = min(t.max(), t.values[on_idx[-1]] + 10.0)
    else:
        x_lo, x_hi = 0.0, t.max()

    mask  = (t >= x_lo) & (t <= x_hi)
    t_win = t[mask].reset_index(drop=True)
    on_win = on[mask].reset_index(drop=True)

    VARS = [
        ('Sralt', 'Sralt_smooth', 'Altímetro de radar  (Sralt)',
         'm  — altura sobre terreno', 'tab:blue',   window_sralt),
        ('Sbaro', 'Sbaro_smooth', 'Presión barométrica  (Sbaro)',
         'mBar', 'tab:cyan',    window_env),
        ('Stemp', 'Stemp_smooth', 'Temperatura del aire  (Stemp)',
         '°C',   'tab:orange',  window_env),
    ]

    fig, axes = plt.subplots(
        3, 1, figsize=(14, 10), sharex=True,
    )
    fig.subplots_adjust(hspace=0.38, left=0.08, right=0.97, top=0.90, bottom=0.07)

    for ax, (raw_col, sm_col, title, ylabel, color, win) in zip(axes, VARS):
        raw = df[raw_col][mask].reset_index(drop=True)
        sm  = df[sm_col][mask].reset_index(drop=True)

        # Y limits: P2–P98 of the raw signal in the display window
        y_lo  = np.nanpercentile(raw.values, 2)
        y_hi  = np.nanpercentile(raw.values, 98)
        margin = max((y_hi - y_lo) * 0.20, 0.5)
        ax.set_ylim(y_lo - margin, y_hi + margin)

        ax.plot(t_win, raw, color='0.55', lw=1.0, alpha=1.0,
                label='crudo', zorder=1)
        ax.plot(t_win, sm,  color=color,  lw=2.5, alpha=1.0,
                label=f'suavizado  (ventana {win} s)', zorder=2)

        _shade_on_line(ax, t_win, on_win)

        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=9, loc='left', weight='bold')
        ax.legend(fontsize=8, loc='upper right')
        ax.grid(alpha=0.3)
        ax.tick_params(labelsize=8)

    axes[-1].set_xlabel('Tiempo desde inicio del vuelo  (min)', fontsize=9)
    axes[-1].set_xlim(x_lo, x_hi)

    fig.suptitle(
        f'QC suavizado pre-GammAn — Vuelo {flight_id}  |  {date}\n'
        f'Ventanas: Sralt={window_sralt} s  ·  Sbaro/Stemp={window_env} s  ·  '
        f'Región: {x_lo:.0f}–{x_hi:.0f} min  ·  '
        f'Verde = tramos en línea de producción',
        fontsize=10, weight='bold',
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'    → {out_path.relative_to(PROJECT_ROOT)}')


def save_spc_csvs(
    df_raw: pd.DataFrame,
    flight_id: str,
    date: str,
    interim_root: Path,
    window_sralt: int,
    window_env: int,
) -> None:
    """
    Save raw and smoothed SPC scalar data as CSV files.

    Two files per flight:
      _spc_raw.csv    : columnas escalares tal como salen de read_spc
      _spc_smooth.csv : ídem más Sralt_smooth, Sbaro_smooth, Stemp_smooth

    Permiten comparar visualmente qué entra a GammAn antes y después del
    suavizado, y verificar que la ventana elegida es apropiada.
    Nota: no son los archivos de input de GammAn (ese requiere también el
    espectro Sbin — lo hará export_gamman.py).
    """
    out_dir = interim_root / 'm03_gamman' / 'input' / date
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_path = out_dir / f'flight_{flight_id}_spc_raw.csv'
    df_raw.to_csv(raw_path, index=False)

    df_smooth = smooth_env(df_raw, window_sralt, window_env)
    sm_path   = out_dir / f'flight_{flight_id}_spc_smooth.csv'
    df_smooth.to_csv(sm_path, index=False)

    print(f'    CSV raw    → {raw_path.relative_to(PROJECT_ROOT)}')
    print(f'    CSV smooth → {sm_path.relative_to(PROJECT_ROOT)}')


def main(
    target_date: str | None = None,
    target_flight: str | None = None,
) -> None:
    cfg      = load_config()
    campaign = cfg['campaign']['name']
    run_name = cfg['campaign']['run_name']
    raw_root = PROJECT_ROOT / cfg['campaign']['raw_data_path']
    out_root = PROJECT_ROOT / 'outputs' / campaign / run_name / 'm03' / 'inspection'

    rad_cfg      = cfg.get('radiometry', {})
    window_sralt = int(rad_cfg.get('smooth_window_sralt', 5))
    window_env   = int(rad_cfg.get('smooth_window_env', 5))
    max_alt_m    = float(rad_cfg.get('max_usable_altitude_m', 120.0))
    interim_root = PROJECT_ROOT / 'data' / 'interim' / campaign / run_name

    print(f'Campaign : {campaign}')
    print(f'Run      : {run_name}')
    print(f'Smooth   : Sralt={window_sralt} s  Env={window_env} s  MaxAlt={max_alt_m} m')

    date_dirs = sorted(d for d in raw_root.iterdir() if d.is_dir())
    if target_date:
        date_dirs = [d for d in date_dirs if d.name == target_date]
    if not date_dirs:
        print('No date folders found.')
        return

    all_data = []

    for date_dir in date_dirs:
        date      = date_dir.name
        spc_files = sorted(date_dir.glob('SPC*.txt'))
        if target_flight:
            spc_files = [f for f in spc_files if target_flight in f.stem]
        if not spc_files:
            continue

        print(f'\n{date}  ({len(spc_files)} SPC file(s))')

        for spc_path in spc_files:
            stem      = spc_path.stem
            flight_id = stem[3:] if stem.upper().startswith('SPC') else stem
            print(f'  {spc_path.name}', end='  ')

            df = read_spc(spc_path)
            if df.empty:
                print('[empty — skipping]')
                continue

            t_min = (df['M2clk'].max() - df['M2clk'].min()) / 60_000
            print(
                f'{len(df):,} rows  ·  {t_min:.1f} min  ·  '
                f'Sralt: {df["Sralt"].min():.1f}–{df["Sralt"].max():.1f} m  ·  '
                f'Srate: {df["Srate"].mean():.0f} cps'
            )

            # Figura 1 — overview completo del vuelo (5 paneles)
            out_path = out_root / date / f'flight_{flight_id}_spc.png'
            plot_flight(df, flight_id, date, out_path,
                        window_sralt, window_env, max_alt_m)

            # Figura 2 — QC del suavizado (Sralt, Sbaro, Stemp)
            smooth_path = out_root / date / f'flight_{flight_id}_smooth_qc.png'
            plot_smoothing_qc(df, flight_id, date, smooth_path,
                              window_sralt, window_env)

            # CSVs — crudo y suavizado para comparación
            save_spc_csvs(df, flight_id, date, interim_root,
                          window_sralt, window_env)

            all_data.append((flight_id, df))

    if not target_flight and len(all_data) > 1:
        print(f'\n  Campaign map...')
        plot_campaign_map(all_data, out_root / 'campaign_spc_map.png')

    print(f'\nDone.  outputs/{campaign}/{run_name}/m03/inspection/')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='M3 SPC inspection')
    parser.add_argument('date',   nargs='?', default=None,
                        help='One day only  (DD.MM.YYYY)')
    parser.add_argument('flight', nargs='?', default=None,
                        help='One flight only  (e.g. 00447)')
    args = parser.parse_args()
    main(target_date=args.date, target_flight=args.flight)
