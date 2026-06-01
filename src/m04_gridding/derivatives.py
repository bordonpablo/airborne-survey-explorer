"""
Module 4 — Magnetic derivative products.

All transforms are computed in the wavenumber (FFT) domain, which is exact for
band-limited data and avoids edge artefacts better than spatial finite differences.

Products
--------
analytic_signal      A = sqrt((dB/dx)² + (dB/dy)² + (dB/dz)²)
                     Maximum over causative bodies regardless of magnetisation
                     direction. Used to map body edges and contacts.

horizontal_gradient  HGM = sqrt((dB/dx)² + (dB/dy)²)
                     Highlights contacts and faults. Peaks directly over
                     vertical contacts.

vertical_derivative  dB/dz
                     Enhances shallow sources and sharpens anomalies.

tilt_derivative      atan(dB/dz / HGM)
                     Ranges ±90°. Zero contour follows body edges. Useful for
                     mapping contacts independent of field amplitude.

rtp                  Reduction to Pole
                     Removes the effect of the inclined field and magnetisation,
                     repositioning anomalies directly over their causative bodies.
                     Requires inclination (I) and declination (D) of Earth's field.
                     Computed using the stabilised filter of Blakely (1995):
                         RTP(k) = F(k) · conj(θ²) / (|θ²|² + ε²)
                     where θ(k) = i·(l·kx + m·ky)/|k| + n
                     and (l, m, n) are the direction cosines of the main field.
"""

import numpy as np


def _wavenumbers(grid_z: np.ndarray, cell_size_m: float) -> tuple:
    """Return (KX, KY) wavenumber grids (rad/m) matching the grid shape."""
    ny, nx = grid_z.shape
    kx = np.fft.fftfreq(nx, d=cell_size_m) * 2 * np.pi
    ky = np.fft.fftfreq(ny, d=cell_size_m) * 2 * np.pi
    KX, KY = np.meshgrid(kx, ky)
    return KX, KY


def _fft_grid(grid_z: np.ndarray) -> np.ndarray:
    """FFT of grid after filling masked/NaN values with the field mean."""
    z = grid_z.copy()
    if np.ma.is_masked(z):
        z = np.where(z.mask, float(z.mean()), z.data)
    return np.fft.fft2(np.asarray(z, dtype=float))


def field_direction(
    lon: float,
    lat: float,
    alt_km: float,
    year: int,
    month: int,
    day: int,
) -> tuple[float, float]:
    """
    Compute inclination and declination of Earth's field at a given location
    and date using the IGRF-13 model (ppigrf).

    Parameters
    ----------
    lon, lat : geographic coordinates (degrees)
    alt_km   : altitude above ellipsoid (km)
    year, month, day : date of the survey

    Returns
    -------
    (inclination_deg, declination_deg)
        inclination : positive downward from horizontal (°)
        declination : positive east from geographic north (°)
    """
    from datetime import datetime
    import ppigrf

    date = datetime(year, month, day)
    Be, Bn, Bu = ppigrf.igrf(lon, lat, alt_km, date)
    Be, Bn, Bu = float(Be), float(Bn), float(Bu)

    F   = np.sqrt(Be**2 + Bn**2 + Bu**2)
    inc = float(np.degrees(np.arcsin(-Bu / F)))  # Bu upward → -Bu downward
    dec = float(np.degrees(np.arctan2(Be, Bn)))

    print(f"  [IGRF at survey centre]  I = {inc:.1f}°  D = {dec:.1f}°  F = {F:.1f} nT")
    return inc, dec


def compute_rtp(
    grid_z: np.ndarray,
    cell_size_m: float,
    inc_deg: float,
    dec_deg: float,
    epsilon: float = 0.05,
) -> np.ndarray:
    """
    Reduction to Pole (RTP).

    Transforms the total-field anomaly as if both the inducing field and the
    remanent magnetisation were vertical (at the pole). Repositions anomalies
    directly over their sources and converts dipolar shapes to monopolar shapes.

    Uses the stabilised division of Blakely (1995):
        RTP(k) = F(k) · conj(θ²) / (|θ²|² + ε²)
    where θ(k) = i·(l·kx + m·ky)/|k| + n

    Direction cosines:
        l = cos(I)·sin(D)   East component
        m = cos(I)·cos(D)   North component
        n = sin(I)          Down component

    Parameters
    ----------
    inc_deg  : inclination in degrees (positive downward)
    dec_deg  : declination in degrees (positive east)
    epsilon  : stabilisation factor (fraction of max |θ²|); default 0.05
    """
    I = np.radians(inc_deg)
    D = np.radians(dec_deg)

    l = np.cos(I) * np.sin(D)   # East
    m = np.cos(I) * np.cos(D)   # North
    n = np.sin(I)                # Down

    KX, KY = _wavenumbers(grid_z, cell_size_m)
    K      = np.sqrt(KX**2 + KY**2)
    F_fft  = _fft_grid(grid_z)

    with np.errstate(divide='ignore', invalid='ignore'):
        theta = np.where(
            K > 0,
            1j * (l * KX + m * KY) / K + n,
            complex(n, 0),          # DC: θ = sin(I)
        )

    theta_sq  = theta**2
    abs_sq    = np.abs(theta_sq)**2
    eps       = epsilon * np.sqrt(float(abs_sq.max()))
    rtp_fft   = F_fft * np.conj(theta_sq) / (abs_sq + eps**2)
    rtp       = np.real(np.fft.ifft2(rtp_fft))
    return rtp


def compute_derivatives(
    grid_z: np.ndarray,
    cell_size_m: float,
    inc_deg: float | None = None,
    dec_deg: float | None = None,
) -> dict[str, np.ndarray]:
    """
    Compute all derivative products from the gridded field.

    Parameters
    ----------
    grid_z      : 2D masked array from make_grid (rows = N, cols = E)
    cell_size_m : grid cell size in metres
    inc_deg     : field inclination (degrees). Required for RTP; skipped if None.
    dec_deg     : field declination (degrees). Required for RTP; skipped if None.

    Returns
    -------
    dict with keys: analytic_signal, horizontal_gradient, vertical_derivative,
                    tilt_derivative, and rtp (if inc/dec provided).
    All arrays are 2D, same shape as grid_z, masked where grid_z is masked.
    """
    KX, KY = _wavenumbers(grid_z, cell_size_m)
    K      = np.sqrt(KX**2 + KY**2)
    F      = _fft_grid(grid_z)

    dBdx = np.real(np.fft.ifft2(1j * KX * F))
    dBdy = np.real(np.fft.ifft2(1j * KY * F))
    dBdz = np.real(np.fft.ifft2(K * F))

    horiz = np.sqrt(dBdx**2 + dBdy**2)
    AS    = np.sqrt(dBdx**2 + dBdy**2 + dBdz**2)
    tilt  = np.degrees(np.arctan2(dBdz, horiz + 1e-10))

    mask = np.ma.getmaskarray(grid_z)

    results = {
        'analytic_signal':     np.ma.masked_where(mask, AS),
        'horizontal_gradient': np.ma.masked_where(mask, horiz),
        'vertical_derivative': np.ma.masked_where(mask, dBdz),
        'tilt_derivative':     np.ma.masked_where(mask, tilt),
    }

    if inc_deg is not None and dec_deg is not None:
        rtp = compute_rtp(grid_z, cell_size_m, inc_deg, dec_deg)
        results['rtp'] = np.ma.masked_where(mask, rtp)

    return results
