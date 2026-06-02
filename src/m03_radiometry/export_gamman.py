"""
Export smoothed SPC file for GammAn import (Etapa A).

GammAn's FSA requires the raw 512-channel spectrum (Sbin) in the original
SPC format. The only change before import is to smooth Sralt, Sbaro, and
Stemp to avoid migrating their high-frequency noise into the FSA corrections.

Strategy: rewrite the SPC file line by line, replacing only the three
environmental fields in-place. Every other character — including the Sbin
hex block and the ## terminator — is copied unchanged.

Replacement is character-position based: the new value is right-justified
in the same width as the original token, so the fixed-width column layout
is preserved exactly.
"""

from pathlib import Path

from src.m03_radiometry.read_spc import read_spc
from src.m03_radiometry.smooth_env import smooth_env


def _find_token_pos(line: str, n: int) -> tuple[int, int]:
    """
    Return (start, end) character positions of the nth whitespace-separated
    token in line. Returns (-1, -1) if there are fewer than n+1 tokens.
    """
    pos   = 0
    count = 0
    while pos < len(line):
        while pos < len(line) and line[pos] == ' ':
            pos += 1
        if pos >= len(line):
            break
        end = pos
        while end < len(line) and line[end] != ' ':
            end += 1
        if count == n:
            return pos, end
        count += 1
        pos = end
    return -1, -1


def _replace_token(line: str, token_idx: int, new_value: float) -> str:
    """
    Replace the token at token_idx with new_value, formatted with the same
    number of decimal places as the original and right-justified in the
    same column width.
    """
    start, end = _find_token_pos(line, token_idx)
    if start < 0:
        return line

    old_str  = line[start:end]
    decimals = len(old_str.split('.')[-1]) if '.' in old_str else 3
    new_str  = f'{new_value:.{decimals}f}'

    # Preserve column width: right-justify new value in the same number of chars.
    # If the new value is wider (rare for smoothed environmental data), allow it
    # to be slightly wider rather than truncating.
    width   = max(len(old_str), len(new_str))
    new_str = new_str.rjust(width)

    return line[:start] + new_str + line[end:]


def export_gamman(
    spc_path: Path | str,
    out_path: Path | str,
    window_sralt: int = 5,
    window_env:   int = 5,
) -> int:
    """
    Write a GammAn-ready SPC file with smoothed Sralt, Sbaro, and Stemp.

    Reads the original SPC file twice:
      1. Through read_spc + smooth_env to compute the smoothed values.
      2. Line by line to rewrite, replacing only the three environmental
         fields and copying everything else verbatim.

    Parameters
    ----------
    spc_path     : path to the original SPC*.txt file
    out_path     : path for the output file (GammAn input)
    window_sralt : smoothing window for Sralt (samples)
    window_env   : smoothing window for Sbaro and Stemp

    Returns
    -------
    Number of data rows written.
    """
    spc_path = Path(spc_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute smoothed values — one row per valid SPC data line
    df = read_spc(spc_path)
    if df.empty:
        print(f'  [export] {spc_path.name}: empty — skipping')
        return 0

    df = smooth_env(df, window_sralt, window_env)
    smooth_vals = df[['Sralt_smooth', 'Sbaro_smooth', 'Stemp_smooth']].values
    smooth_idx  = 0

    rows_written = 0
    with open(spc_path, encoding='latin-1') as f_in, \
         open(out_path, 'w',  encoding='latin-1') as f_out:

        # Header line — copy unchanged
        f_out.write(f_in.readline())

        for raw_line in f_in:
            if '##' not in raw_line:
                f_out.write(raw_line)
                continue

            parts = raw_line.split()
            n     = len(parts)

            if n not in (23, 24):
                # Unexpected format — copy unchanged
                f_out.write(raw_line)
                continue

            if smooth_idx >= len(smooth_vals):
                # More lines in file than rows parsed (shouldn't happen)
                f_out.write(raw_line)
                continue

            sralt_s, sbaro_s, stemp_s = smooth_vals[smooth_idx]
            smooth_idx += 1

            swayp_present = (n == 24)
            offset        = 1 if swayp_present else 0

            # Field indices in parts[] (with Swayp counted):
            #   Sralt = 7 + offset
            #   Sbaro = 11 + offset
            #   Stemp = 12 + offset
            line = raw_line.rstrip('\n')
            line = _replace_token(line, 7  + offset, sralt_s)
            line = _replace_token(line, 11 + offset, sbaro_s)
            line = _replace_token(line, 12 + offset, stemp_s)

            f_out.write(line + '\n')
            rows_written += 1

    return rows_written
