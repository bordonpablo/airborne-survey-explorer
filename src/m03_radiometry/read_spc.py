"""
Read and parse Medusa SPC files.

Each SPC file contains ~1 Hz gamma-ray spectrometry data: scalar sensor
readings plus a raw 512-channel spectrum (Sbin) for every second of flight.

Parsing note: the last numeric column (Sa2) and Sbin share a token with no
separator between them. The Sa2 float value occupies the first characters of
the token; the remaining hex encodes the binary spectrum ending with the
five-byte terminator ffffffffff and the line marker ##.

The optional Swayp field (survey line ID) is detected by token count:
  23 tokens → Swayp absent (transit or ferry)
  24 tokens → Swayp present at position 4
"""

import re
import struct

import pandas as pd
from pathlib import Path


def _decode_sbin(token: str) -> tuple[float, list[int] | None]:
    """
    Extract Sa2 and decode 256 uint16 LE spectrum channels from the
    concatenated Sa2+Sbin token (the last token on each SPC data line).

    The Sa2 float and the binary Sbin data share this token with no separator.
    Sbin ends with a 5-byte 0xFF terminator (ffffffffff) followed by ##.
    The 256 uint16 LE channel counts immediately precede that terminator.

    Sa2 parsing: the value is a decimal float at the start of the token.
    Any trailing zeros added by the fixed-width DAS format are absorbed by
    float() without loss of precision (they fall beyond double precision).

    Returns
    -------
    (sa2, channels) — channels is a list of 256 ints, or None if decode fails.
    """
    sa2 = float('nan')
    m = re.match(r'^(-?\d+\.\d+)', token)
    if m:
        try:
            sa2 = float(m.group(1))
        except ValueError:
            pass

    # 256 uint16 LE = 512 bytes = 1024 hex chars, ending at the ffffffffff marker
    s   = token.lower().rstrip().rstrip('#')
    pos = s.rfind('ffffffffff')
    if pos < 1024:
        return sa2, None

    try:
        channels = list(struct.unpack('<256H', bytes.fromhex(s[pos - 1024 : pos])))
        return sa2, channels
    except Exception:
        return sa2, None


def read_spc(
    path: Path | str,
    decode_spectrum: bool = False,
) -> pd.DataFrame:
    """
    Parse one SPC file and return a DataFrame of scalar channels.

    Parameters
    ----------
    path             : path to SPC*.txt
    decode_spectrum  : if True, also decode Sbin into 256 uint16 columns
                       ch000 … ch255 and include Sa2.

    Returns
    -------
    DataFrame with columns:
        flight_id, M2clk, Sdate, Stime, Swayp,
        Sxgps, Sygps, Szgps, Sralt,
        Sbaro, Stemp, Shumd,
        Sreal, Slive, Srate,
        Sk, Su, Sth, Sa0, Sa1,
        [Sa2, ch000 … ch255  ← only when decode_spectrum=True]
        livetime_frac
    """
    path = Path(path)
    rows = []

    with open(path, encoding='latin-1') as f:
        f.readline()  # skip header
        for line in f:
            if '##' not in line:
                continue
            parts = line.split()
            n     = len(parts)

            # Token count distinguishes whether Swayp is present:
            #   23 → no Swayp  (fields 0-21 = M2st..Sa1, field 22 = Sa2+Sbin)
            #   24 → Swayp at parts[4]
            if n == 23:
                swayp = ''
                p = parts
            elif n == 24:
                swayp = parts[4]
                p = parts[:4] + parts[5:]
            else:
                continue

            try:
                row = {
                    'M2clk': float(p[1]),
                    'Sdate': p[2],
                    'Stime': float(p[3]),
                    'Sxgps': float(p[4]),
                    'Sygps': float(p[5]),
                    'Szgps': float(p[6]),
                    'Sralt': float(p[7]),
                    # p[8]=BaroV, p[9]=TempV, p[10]=HumdV — raw ADC voltages, skipped
                    'Sbaro': float(p[11]),
                    'Stemp': float(p[12]),
                    'Shumd': float(p[13]),
                    'Sreal': float(p[14]),
                    'Slive': float(p[15]),
                    'Srate': float(p[16]),
                    'Sk':    float(p[17]),
                    'Su':    float(p[18]),
                    'Sth':   float(p[19]),
                    'Sa0':   float(p[20]),
                    'Sa1':   float(p[21]),
                    # p[22] = Sa2+Sbin concatenated
                    'Swayp': swayp,
                }

                if decode_spectrum:
                    sa2, channels = _decode_sbin(p[22])
                    row['Sa2'] = sa2
                    if channels is not None:
                        for i, v in enumerate(channels):
                            row[f'ch{i:03d}'] = v
                    else:
                        for i in range(256):
                            row[f'ch{i:03d}'] = None

                rows.append(row)
            except (ValueError, IndexError):
                continue

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    stem      = path.stem
    flight_id = stem[3:] if stem.upper().startswith('SPC') else stem
    df.insert(0, 'flight_id', flight_id)

    sreal = df['Sreal'].replace(0.0, float('nan'))
    df['livetime_frac'] = df['Slive'] / sreal

    return df
