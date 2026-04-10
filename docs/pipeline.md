# Pipeline reference

## step1_status.py — Sensor health and data-quality check

### Input files

Each GeoDuster session produces four data files:

| File | Content | Typical rate |
|------|---------|-------------|
| `EVT000NN.txt` | Timestamped system event log from ICCS | event-driven |
| `MAG000NN.txt` | Main multi-sensor log (magnetometers, attitude, altimeter, GPS, VLF) | ~10 Hz |
| `GGA000NN.txt` | Differential GPS log (position, HDOP, satellite count) | ~10 Hz |
| `SPC000NN.txt` | Spectrometer channels and environmental sensors (baro, temp, humidity) | ~1 Hz |

The EVT log records which sensors are configured on which COM ports and their character
rates. A rate of 0 chars/s means the sensor is not transmitting — either physically
disconnected or switched off in software. The MAG, GGA, and SPC files use a
right-aligned fixed-width ASCII format; cells containing only `#` represent missing
values (NaN).

### Why a health check is needed before processing

GeoDuster systems poll up to eight sensors across a multiplexed COM bus. A sensor can
be configured in the software (appearing in EVT with a port assignment) yet produce no
data — because of a loose connector, wrong baud rate, or a port disabled in the XML
configuration. Silent missing data would corrupt every downstream step (compensation,
line editing, maps) without any obvious error. The health check catches these
mismatches before any processing begins.

### Time columns

Each file type has its own time column encoding UTC as a `HHMMSS.sss` float:

| Column | File | Source sensor |
|--------|------|--------------|
| `Time` | MAG | Mux1 system clock |
| `dTime` | GGA | Septentrio GPS receiver |
| `Stime` | SPC | Medusa spectrometer |

These three clocks are not necessarily synchronised sample-by-sample. The script
converts each to elapsed seconds from the first valid sample of that file; full
cross-file time alignment is handled in a later step.

### Terminal output and saved files

For each session the script prints a compact summary to the terminal:
- Session header (number, date, duration, row counts per file)
- Sensor status table: connection status derived from EVT char rates and NaN presence in data
- Data-quality table: mean, std, and threshold check for key variables
- Warning count line (critical errors and Mux TimeO events)

The full detailed report — EVT analysis, column NaN classification, GPS quality
indicators, full stability table, cross-check EVT vs MAG — is written to
`outputs/session_NNN/report_NNN.txt`. Eight diagnostic plots are saved to
`outputs/session_NNN/` as PNG files at 150 dpi.

If two or more sessions are passed (or auto-detected), a compact side-by-side
comparison table is printed after the individual summaries and saved to
`outputs/comparison_NNN_MMM.txt`.

---

## Future steps (stubs)

### step2_lines.py — Flight line editing and session merging

Will define flight line boundaries from GPS track and waypoint data, split or merge
sessions, flag turns and non-survey segments, and export a cleaned line index for use
in the correction and mapping steps.

### step3_mag.py — Magnetic corrections

Will apply diurnal correction (base station or IGRF), lag correction for towed-sensor
offset, and magnetic compensation using the CMP model files in the data folder.

### step3_rad.py — Radiometric corrections (future)

Will handle live-time correction, background subtraction, and stripping ratios for the
Medusa gamma-ray spectrometer channels (K, U, Th).

### step4_maps.py — Visualisation and export

Will grid corrected data onto flight lines, generate colour-shaded maps (total field,
compensated field, radiometric channels, altimetry), and export to standard geophysics
formats (XYZ, GeoTIFF).
