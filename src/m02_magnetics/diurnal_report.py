"""
Module 2 — Step 3: run the diurnal correction on the selected flights and write its outputs.

Outputs (all in one folder):
    diurnal_summary.txt        plain-language summary: what was done, what was not, what changed
    diurnal_base_station.csv   the base station readings used (UTC time, nT, variation, file)
    diurnal_base_station.png   base station during each flight
    diurnal_before_after.png   maps: before, after, and the correction itself

The correction is in diurnal.py. The corrected columns are saved in the m02 parquet of each
flight (BaseMag, Diurnal, Mag1_Diurnal, Mag2_Diurnal, utc_s).
"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from src.m02_magnetics.diurnal import read_base_station, apply_diurnal

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _rel(path: Path) -> str:
    """Path relative to the project, or as is when it lies elsewhere."""
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


CSV_MARGIN_S = 600          # base readings kept in the csv: flight window ± 10 min
MAP_COLS = ['Xgps', 'Ygps', 'Mag1C', 'Mag2C', 'Mag1_Diurnal', 'Mag2_Diurnal', 'Diurnal']


def run_diurnal_step(
    selected: pd.DataFrame,
    flights: pd.DataFrame,
    interim_root: Path,
    out_dir: Path,
    raw_root: Path,
    igrf_base_nT: float,
    supplement: Path | None = None,
) -> None:
    """Apply the diurnal correction to every selected flight and write the outputs."""
    out_dir.mkdir(parents=True, exist_ok=True)

    base = read_base_station(raw_root, supplement)
    print(f"  Base station: {len(base):,} readings from {base['source'].nunique()} files")
    for note in base.attrs['notes']:
        print(f"  [DIURNAL] {note}")

    stats, parts = [], []
    for _, fr in flights.iterrows():
        date, fid = fr['date'], fr['flight_id']
        pq = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"
        if not pq.exists():
            print(f"  Skipping {date}/flight_{fid}: m02 parquet not found — run steps 1,2 first")
            continue

        df = apply_diurnal(pd.read_parquet(pq), base, igrf_base_nT)
        df.to_parquet(pq, index=False)
        print(f"  Updated: {_rel(pq)}")

        lines = selected.loc[(selected['date'] == date) & (selected['flight_id'] == fid), 'line_id']
        s = df[df['line_id'].isin(lines) & df['line_valid']]
        cov = s['BaseMag'].notna()
        window = base[(base['utc_s'] >= s['utc_s'].min() - 60) & (base['utc_s'] <= s['utc_s'].max() + 60)]
        stats.append({
            'date': date, 'flight_id': fid, 'n': len(s), 'n_cov': int(cov.sum()),
            't0': s['utc_s'].min(), 't1': s['utc_s'].max(),
            'dmin': float((-s.loc[cov, 'Diurnal']).min()) if cov.any() else np.nan,
            'dmax': float((-s.loc[cov, 'Diurnal']).max()) if cov.any() else np.nan,
            'files': sorted(window['source'].unique()),
        })
        parts.append(s[MAP_COLS][cov])

    if not stats:
        return
    stats = pd.DataFrame(stats).sort_values('t0').reset_index(drop=True)
    corrected = pd.concat(parts, ignore_index=True)

    _write_csv(base, stats, igrf_base_nT, out_dir / 'diurnal_base_station.csv')
    _plot_base_station(base, stats, igrf_base_nT, out_dir / 'diurnal_base_station.png')
    if corrected.empty:
        print("  No flight has base station data: no maps, nothing corrected.")
        return
    _plot_before_after(corrected, stats, out_dir / 'diurnal_before_after.png')
    _write_summary(base, stats, corrected, igrf_base_nT, out_dir / 'diurnal_summary.txt')


def _utc(seconds) -> pd.Series:
    return pd.to_datetime(seconds, unit='s')


def _write_csv(base, stats, igrf, path: Path) -> None:
    keep = np.zeros(len(base), dtype=bool)
    for _, r in stats.iterrows():
        keep |= ((base['utc_s'] >= r['t0'] - CSV_MARGIN_S) & (base['utc_s'] <= r['t1'] + CSV_MARGIN_S)).values
    out = base[keep].copy()
    out['utc'] = _utc(out['utc_s']).dt.strftime('%Y-%m-%d %H:%M:%S')
    out['delta_nT'] = (out['nT'] - igrf).round(2)
    out[['utc', 'nT', 'delta_nT', 'source']].to_csv(path, index=False)
    print(f"  Base station table: {_rel(path)}")


def _plot_base_station(base, stats, igrf, path: Path) -> None:
    n = len(stats)
    ncols = 4
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, 3.1 * nrows), squeeze=False)
    for ax, (_, r) in zip(axes.flat, stats.iterrows()):
        lo, hi = r['t0'] - 1200, r['t1'] + 1200
        w = base[(base['utc_s'] >= lo) & (base['utc_s'] <= hi)]
        ax.axvspan(_utc(r['t0']), _utc(r['t1']), color='orange', alpha=0.25, label='flight')
        ax.axhline(igrf, color='gray', linestyle='--', linewidth=0.8, label='reference')
        if len(w):
            ax.plot(_utc(w['utc_s']), w['nT'], color='steelblue', linewidth=0.8, label='base station')
        if r['n_cov'] == 0:
            ax.text(0.5, 0.5, 'no base station data', transform=ax.transAxes, ha='center',
                    va='center', color='red', fontsize=11, fontweight='bold')
            ax.set_ylim(igrf - 10, igrf + 10)
        ax.ticklabel_format(axis='y', useOffset=False)
        ax.set_xlim(_utc(lo), _utc(hi))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.set_title(f"{r['date']} · flight {r['flight_id']}", fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    axes[0, 0].legend(fontsize=7, loc='best')
    fig.supxlabel('UTC time (hh:mm)', fontsize=9)
    fig.supylabel('Base station field (nT)', fontsize=9)
    fig.suptitle('Base station during each selected flight', fontsize=12)
    plt.tight_layout(rect=[0.015, 0.02, 1, 0.97])
    fig.savefig(path, dpi=130, bbox_inches='tight')
    plt.close(fig)
    print(f"  Base station plot: {_rel(path)}")


def _plot_before_after(corrected, stats, path: Path) -> None:
    before = (corrected['Mag1C'] + corrected['Mag2C']) / 2
    after  = (corrected['Mag1_Diurnal'] + corrected['Mag2_Diurnal']) / 2
    corr   = corrected['Diurnal']
    p2, p98 = np.nanpercentile(np.concatenate([before.dropna(), after.dropna()]), [2, 98])
    vmax = float(corr.abs().quantile(0.99))
    aspect = 1.0 / np.cos(np.radians(corrected['Ygps'].mean()))

    panels = [
        (before, 'Before: mean of Mag1C and Mag2C (nT)', 'RdYlBu_r', p2, p98),
        (after,  'After: mean of Mag1_Diurnal and Mag2_Diurnal (nT)', 'RdYlBu_r', p2, p98),
        (corr,   f"Correction added at each point (nT)\nmedian |{corr.abs().median():.1f}|, "
                 f"max |{corr.abs().max():.1f}|", 'RdBu_r', -vmax, vmax),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(22, 7))
    for ax, (values, title, cmap, lo, hi) in zip(axes, panels):
        order = np.argsort(np.abs(values.values - np.nanmedian(values.values)))   # extremes on top
        sc = ax.scatter(corrected['Xgps'].values[order], corrected['Ygps'].values[order],
                        c=values.values[order], s=0.5, cmap=cmap, vmin=lo, vmax=hi, rasterized=True)
        plt.colorbar(sc, ax=ax, shrink=0.8)
        ax.set_aspect(aspect)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel('Longitude (°)', fontsize=8)
        ax.set_ylabel('Latitude (°)', fontsize=8)
        ax.grid(alpha=0.3)
    missing = stats.loc[stats['n_cov'] < 0.5 * stats['n'], 'flight_id'].tolist()
    note = f"  |  not shown (no base station data): flights {', '.join(missing)}" if missing else ''
    fig.suptitle(f"Diurnal correction{note}", fontsize=11)
    plt.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig(path, dpi=140, bbox_inches='tight')
    plt.close(fig)
    print(f"  Before/after maps: {_rel(path)}")


def _write_summary(base, stats, corrected, igrf, path: Path) -> None:
    L = ["Diurnal correction - summary", "=" * 28, "",
         f"Reference level : {igrf:.0f} nT (igrf_base_field_nT in project.yaml)",
         f"Base station    : {base['source'].nunique()} files, {len(base):,} readings "
         f"(one every ~3 s, same site all days)", "",
         "What this correction is",
         "  The Earth's field changes during the day because of external currents. A base station",
         "  fixed on the ground records that change. For every airborne reading, the base value",
         "  at the same UTC time is taken and its difference with the reference is subtracted:",
         "      Mag1_Diurnal = Mag1C - (base - reference)",
         "  Only the magnetic values change; the coordinates and the time are not touched.", "",
         "Flights (selected lines only)",
         "  date        flight  UTC window (month-day hh:mm)   corrected   variation (nT)"]
    for _, r in stats.iterrows():
        pct = 100.0 * r['n_cov'] / r['n']
        var = f"{r['dmin']:+.1f} .. {r['dmax']:+.1f}" if r['n_cov'] else "-"
        L.append(f"  {r['date']}  {r['flight_id']}   {_utc(r['t0']):%m-%d %H:%M} - {_utc(r['t1']):%H:%M}"
                 f"           {pct:6.1f} %    {var}")

    problems = list(base.attrs['notes'])
    for _, r in stats.iterrows():
        if r['n_cov'] < 0.5 * r['n']:
            problems.append(f"Flight {r['flight_id']} ({r['date']}): no base station data for its time "
                            f"window. Its magnetic values are left empty (NaN) from this step on.")
        folders = {f.split('/')[0] for f in r['files']}
        if r['n_cov'] and r['date'] not in folders:
            problems.append(f"Flight {r['flight_id']} ({r['date']}) was corrected with "
                            f"{', '.join(r['files'])}: the recording belongs to that flight (by the date "
                            f"in its header) although it is stored in another folder.")
    L += ["", "Things to know"] + [f"  - {p}" for p in (problems or ["Nothing unusual."])]

    a = corrected['Diurnal'].abs()
    L += ["", "How much it changed the data",
          f"  Median {a.median():.1f} nT, 95 % of the points under {a.quantile(0.95):.1f} nT, "
          f"maximum {a.max():.1f} nT."]
    path.write_text("\n".join(L) + "\n", encoding='utf-8')
    print("\n" + "\n".join(L) + "\n")
