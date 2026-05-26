"""
Module 2 — Promedio de sensores magnéticos.

Combina Mag1C y Mag2C en una sola serie. Si ambos sensores tienen ruido similar
se promedia; si uno tiene ruido > 2× el del otro, se descarta el ruidoso.
El criterio de ruido es el std del cuarto diferencial (mag_noise de M1).

[PENDIENTE — no implementado en esta sesión]
"""
