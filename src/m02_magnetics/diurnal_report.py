"""
Module 2 — Step 3: run the diurnal correction on the selected flights and write its outputs.

Outputs (all in one folder):
    diurnal_summary.txt        plain-language summary: what was done, what was not, what changed
    diurnal_base_station.csv   the base station readings used (UTC time, raw and filtered nT, file)
    diurnal_base_station.png   base station during each flight: raw curve, filtered curve and
                               readings from the supplement table (red)
    diurnal_correction.png     the correction added to the data during each flight

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


def run_diurnal_step(
    selected: pd.DataFrame,
    flights: pd.DataFrame,
    interim_root: Path,
    out_dir: Path,
    raw_root: Path,
    reference_nT: float,
    supplement: Path | None = None,
    base_use: str = 'raw',
    filter_window_s: float = 30.0,
) -> None:
    """
    Apply the diurnal correction to every selected flight and write the outputs.

    reference_nT    : diurnal_reference_nT in project.yaml
    supplement      : table of base readings for periods without a recording (base_station_supplement)
    base_use        : 'raw' or 'filtered', the base station curve the correction subtracts
    filter_window_s : moving-average window of the filtered curve
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    base = read_base_station(raw_root, supplement, filter_window_s)
    print(f"  Base station: {len(base):,} readings from {base['source'].nunique()} files "
          f"(correction uses the {base_use} curve)")
    for note in base.attrs['notes']:
        print(f"  [DIURNAL] {note}")

    stats, parts = [], []
    for _, fr in flights.iterrows():
        date, fid = fr['date'], fr['flight_id']
        pq = interim_root / 'm02' / date / f"flight_{fid}_m02.parquet"
        if not pq.exists():
            print(f"  Skipping {date}/flight_{fid}: m02 parquet not found — run steps 1,2 first")
            continue

        df = apply_diurnal(pd.read_parquet(pq), base, reference_nT, base_use)
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
        parts.append(s.loc[cov, ['utc_s', 'Diurnal']])

    if not stats:
        return
    stats = pd.DataFrame(stats).sort_values('t0').reset_index(drop=True)
    corrected = pd.concat(parts, ignore_index=True)

    _write_csv(base, stats, reference_nT, out_dir / 'diurnal_base_station.csv')
    _plot_base_station(base, stats, reference_nT, base_use, filter_window_s,
                       out_dir / 'diurnal_base_station.png')
    if corrected.empty:
        print("  No flight has base station data: nothing corrected.")
        return
    _plot_correction(corrected, stats, base_use, out_dir / 'diurnal_correction.png')
    _write_summary(base, stats, corrected, reference_nT, base_use, filter_window_s,
                   out_dir / 'diurnal_summary.txt')


def _utc(seconds) -> pd.Series:
    return pd.to_datetime(seconds, unit='s')


def _write_csv(base, stats, reference_nT, path: Path) -> None:
    keep = np.zeros(len(base), dtype=bool)
    for _, r in stats.iterrows():
        keep |= ((base['utc_s'] >= r['t0'] - CSV_MARGIN_S) & (base['utc_s'] <= r['t1'] + CSV_MARGIN_S)).values
    out = base[keep].copy()
    out['utc'] = _utc(out['utc_s']).dt.strftime('%Y-%m-%d %H:%M:%S')
    out['delta_raw_nT'] = (out['nT'] - reference_nT).round(2)
    out['delta_filtered_nT'] = (out['nT_filt'] - reference_nT).round(2)
    out = out.rename(columns={'nT': 'nT_raw', 'nT_filt': 'nT_filtered'})
    out[['utc', 'nT_raw', 'nT_filtered', 'delta_raw_nT', 'delta_filtered_nT',
         'source', 'supplement']].to_csv(path, index=False)
    print(f"  Base station table: {_rel(path)}")


def _plot_base_station(base, stats, reference_nT, base_use, filter_window_s, path: Path) -> None:
    n = len(stats)
    ncols = 4
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, 3.1 * nrows), squeeze=False)
    for ax, (_, r) in zip(axes.flat, stats.iterrows()):
        lo, hi = r['t0'] - 1200, r['t1'] + 1200
        w = base[(base['utc_s'] >= lo) & (base['utc_s'] <= hi)]
        ax.axvspan(_utc(r['t0']), _utc(r['t1']), color='orange', alpha=0.25, label='flight')
        ax.axhline(reference_nT, color='gray', linestyle='--', linewidth=0.8, label='reference')
        own, ext = w[~w['supplement']], w[w['supplement']]
        if len(own):
            ax.plot(_utc(own['utc_s']), own['nT'], color='lightsteelblue', linewidth=0.7, label='raw')
            ax.plot(_utc(own['utc_s']), own['nT_filt'], color='navy', linewidth=1.0,
                    label=f'filtered ({filter_window_s:.0f} s)')
        if len(ext):
            ax.plot(_utc(ext['utc_s']), ext['nT'], color='crimson', linewidth=1.2,
                    label='supplement (already filtered)')
            ax.text(0.03, 0.95, 'supplement: filtered base station\nfrom another source (not our recording)',
                    transform=ax.transAxes, va='top', fontsize=7, color='crimson')
        if r['n_cov'] == 0:
            ax.text(0.5, 0.5, 'no base station data', transform=ax.transAxes, ha='center',
                    va='center', color='red', fontsize=11, fontweight='bold')
            ax.set_ylim(reference_nT - 10, reference_nT + 10)
        ax.ticklabel_format(axis='y', useOffset=False)
        ax.set_xlim(_utc(lo), _utc(hi))
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.set_title(f"{r['date']} · flight {r['flight_id']}", fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    handles = {}
    for ax in axes.flat:
        for h, lab in zip(*ax.get_legend_handles_labels()):
            handles.setdefault(lab, h)
    axes[0, 0].legend(handles.values(), handles.keys(), fontsize=7, loc='best')
    fig.supxlabel('UTC time (hh:mm)', fontsize=9)
    fig.supylabel('Base station field (nT)', fontsize=9)
    fig.suptitle(f"Base station during each selected flight  |  the correction uses the {base_use} curve",
                 fontsize=12)
    plt.tight_layout(rect=[0.015, 0.02, 1, 0.97])
    fig.savefig(path, dpi=130, bbox_inches='tight')
    plt.close(fig)
    print(f"  Base station plot: {_rel(path)}")


def _plot_correction(corrected, stats, base_use, path: Path) -> None:
    """Correction added to the data (nT) against UTC time, one panel per flight."""
    n = len(stats)
    ncols = 4
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(18, 2.6 * nrows), squeeze=False)
    for ax, (_, r) in zip(axes.flat, stats.iterrows()):
        s = corrected[(corrected['utc_s'] >= r['t0']) & (corrected['utc_s'] <= r['t1'])].sort_values('utc_s')
        ax.axhline(0, color='gray', linewidth=0.8)
        if len(s):
            ax.plot(_utc(s['utc_s']), s['Diurnal'], color='darkgreen', linewidth=0.8)
            ax.set_title(f"{r['date']} · flight {r['flight_id']}  ({s['Diurnal'].min():+.1f} .. "
                         f"{s['Diurnal'].max():+.1f} nT)", fontsize=9)
        else:
            ax.set_title(f"{r['date']} · flight {r['flight_id']}  (not corrected)", fontsize=9)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
    for ax in list(axes.flat)[n:]:
        ax.set_visible(False)
    fig.supxlabel('UTC time (hh:mm)', fontsize=9)
    fig.supylabel('Correction added to the data (nT)', fontsize=9)
    fig.suptitle(f"Diurnal correction added during each flight (base station: {base_use})", fontsize=12)
    plt.tight_layout(rect=[0.015, 0.02, 1, 0.97])
    fig.savefig(path, dpi=130, bbox_inches='tight')
    plt.close(fig)
    print(f"  Correction plot: {_rel(path)}")


def _write_summary(base, stats, corrected, reference_nT, base_use, filter_window_s, path: Path) -> None:
    L = ["Diurnal correction - summary", "=" * 28, "",
         f"Reference level : {reference_nT:.0f} nT (diurnal_reference_nT in project.yaml)",
         f"Base station    : {base['source'].nunique()} sources, {len(base):,} readings "
         f"(one every ~3 s, same site all days)",
         f"Curve used      : {base_use} (base_station_use in project.yaml). The other one is "
         f"{'the raw curve' if base_use == 'filtered' else f'a {filter_window_s:.0f} s moving average'}, "
         f"drawn in diurnal_base_station.png", "",
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
        own_files = [f for f in r['files'] if '/' in f]      # Tagesgang files; the supplement has no folder
        folders = {f.split('/')[0] for f in own_files}
        if r['n_cov'] and own_files and r['date'] not in folders:
            problems.append(f"Flight {r['flight_id']} ({r['date']}) was corrected with "
                            f"{', '.join(own_files)}: the recording belongs to that flight (by the date "
                            f"in its header) although it is stored in another folder.")
    L += ["", "Things to know"] + [f"  - {p}" for p in (problems or ["Nothing unusual."])]

    a = corrected['Diurnal'].abs()
    L += ["", "How much it changed the data",
          f"  Median {a.median():.1f} nT, 95 % of the points under {a.quantile(0.95):.1f} nT, "
          f"maximum {a.max():.1f} nT."]
    path.write_text("\n".join(L) + "\n", encoding='utf-8')
    print("\n" + "\n".join(L) + "\n")
