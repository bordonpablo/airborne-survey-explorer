"""
Module 2 — Magnéticos: entrada principal.

Aplica la cadena de correcciones magnéticas a todas las líneas seleccionadas:
    0. Inspección raw     (inspect_raw.py)
    1. Estimación de lag  (lag.py)
    2. Corrección de lag  (lag.py)         — solo si LAG_SIGNIFICANT
    3. Corrección diurna  (diurnal.py)     [pendiente]
    4. Remoción IGRF      (igrf.py)        [pendiente]
    5. Corrección heading (heading.py)     [pendiente]
    6. Promedio sensores  (average_sensors.py) [pendiente]
    7. Nivelación tie     (levelling.py)   [pendiente]
    8. Micronivelación    (microlevelling.py) [pendiente]

Uso:
    python -m src.m02_magnetics.run
    python -m src.m02_magnetics.run 22.04.2022
    python -m src.m02_magnetics.run 22.04.2022 00447
"""

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def load_config() -> dict:
    with open(PROJECT_ROOT / 'config' / 'project.yaml') as f:
        return yaml.safe_load(f)


def main() -> None:
    print("[M2] Módulo 2 — Correcciones magnéticas")
    print("[M2] run.py pendiente de implementación completa.")
    print("[M2] Usar directamente:")
    print("[M2]   python -m src.m02_magnetics.inspect_raw <fecha> <flight_id> [line_id]")
    print("[M2]   python -m src.m02_magnetics.lag         <fecha> <flight_id>")


if __name__ == '__main__':
    main()
