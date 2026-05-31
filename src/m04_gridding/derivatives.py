"""
Module 4 — Magnetic derivative products.

Computes standard potential-field derivatives from the gridded RMA (Mag_Final).
All derivatives are computed in the wavenumber domain via FFT, which is exact
for band-limited data and avoids edge artefacts better than spatial finite differences.

Products
--------
analytic_signal : A(x,y) = sqrt( (dB/dx)² + (dB/dy)² + (dB/dz)² )
    Amplitude of the analytic signal. Maximum over causative bodies regardless
    of magnetisation direction. Used to map body edges and contacts.

vertical_derivative : dB/dz
    First vertical derivative. Enhances shallow sources and sharpens anomalies.

tilt_derivative : atan( dB/dz / sqrt((dB/dx)² + (dB/dy)²) )
    Tilt angle. Ranges ±90°. Zero contour follows body edges. Useful for
    mapping geological contacts independent of field amplitude.
"""

import numpy as np


def _wavenumbers(grid_z: np.ndarray, cell_size_m: float) -> tuple:
    """Return (kx, ky) wavenumber grids (rad/m) for FFT-domain operations."""
    ny, nx = grid_z.shape
    kx = np.fft.fftfreq(nx, d=cell_size_m) * 2 * np.pi
    ky = np.fft.fftfreq(ny, d=cell_size_m) * 2 * np.pi
    KX, KY = np.meshgrid(kx, ky)
    return KX, KY


def _fft_grid(grid_z: np.ndarray) -> np.ndarray:
    """FFT of grid, replacing masked/NaN values with the field mean."""
    z = grid_z.copy()
    if np.ma.is_masked(z):
        z = np.where(z.mask, z.mean(), z.data)
    return np.fft.fft2(z)


def compute_derivatives(
    grid_z: np.ndarray,
    cell_size_m: float,
) -> dict[str, np.ndarray]:
    """
    Compute analytic signal, vertical derivative, and tilt derivative.

    Parameters
    ----------
    grid_z      : 2D masked array from make_grid (rows = N, cols = E)
    cell_size_m : grid cell size in metres

    Returns
    -------
    dict with keys: 'analytic_signal', 'vertical_derivative', 'tilt_derivative'
    All arrays are 2D, same shape as grid_z, masked where grid_z is masked.
    """
    KX, KY = _wavenumbers(grid_z, cell_size_m)
    K      = np.sqrt(KX**2 + KY**2)
    F      = _fft_grid(grid_z)

    # Horizontal derivatives in x (E) and y (N)
    dBdx = np.real(np.fft.ifft2(1j * KX * F))
    dBdy = np.real(np.fft.ifft2(1j * KY * F))

    # Vertical (upward = positive z) derivative: multiply by |k| in freq domain
    dBdz = np.real(np.fft.ifft2(K * F))

    # Analytic signal
    AS = np.sqrt(dBdx**2 + dBdy**2 + dBdz**2)

    # Tilt derivative
    horiz = np.sqrt(dBdx**2 + dBdy**2)
    tilt  = np.degrees(np.arctan2(dBdz, horiz + 1e-10))

    # Apply original mask
    mask = np.ma.getmaskarray(grid_z)
    results = {
        'analytic_signal':    np.ma.masked_where(mask, AS),
        'vertical_derivative': np.ma.masked_where(mask, dBdz),
        'tilt_derivative':    np.ma.masked_where(mask, tilt),
    }
    return results
