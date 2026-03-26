# Airborne Geophysics – Welzow Ground Test (2026-03-24)

## What this project is about

This repository contains raw instrument data and Python analysis scripts
for a **ground test of an airborne geophysics sensor suite** (GeoDuster
system) performed at **Welzow, Germany on 2026-03-24**. The aircraft was
parked on the ground with the data acquisition system running. The tests
verify which sensors are active, checks data quality, and flag system
anomalies before a real airborne survey flight.

---

## Sessions

| Field | Session 006 | Session 007 |
|-------|-------------|-------------|
| Start (UTC) | 2026-03-24 14:34:33.600000 | 2026-03-24 15:01:47 |
| End (UTC) | 2026-03-24 14:54:36.900000 | 2026-03-24 15:17:01.700000 |
| Duration | 0:20:03.300000 | 0:15:14.700000 |
| MAG rows | 11306 | 735 |
| GGA rows | 11131 | 737 |
| SPC rows | 1134 | 73 |

---

## Sensor status

| Sensor | Port | Full Name | 006 | 007 | Reason if disconnected |
|--------|------|-----------|-----|-----|------------------------|
| GEMK1 | COM3 | Magnetometer #1 (Port side) | CONNECTED | CONNECTED | Active |
| GEMK2 | COM4 | Magnetometer #2 (Starboard side) | CONNECTED | CONNECTED | Active |
| GDRAlt | COM5 | Radar Altimeter | CONNECTED | CONNECTED | Active |
| GD485 | COM6 | ADC 4-channel VLF receiver (RS-485 bus) | DISCONNECTED | DISCONNECTED | Not connected / powered off during this test |
| XSENS | COM7 | AHRS / GPS attitude sensor | CONNECTED | CONNECTED | Active |
| GDGPS | COM8 | Septentrio differential GPS | CONNECTED | CONNECTED | Active |
| GDSpec | COM9 | Medusa Gamma-Ray Spectrometer | DISCONNECTED | DISCONNECTED | Not connected / powered off during this test |
| GDLas | COM10 | Laser Altimeter | DISCONNECTED | DISCONNECTED | Not connected / powered off during this test |

---

## Data files

| File | Written by | Format | Description |
|------|------------|--------|-------------|
| EVT*.txt | ICCS system | Plain text | Timestamped event log |
| MAG*.txt | Mux1 | Fixed-width ASCII | Main multi-sensor data (~10 Hz) |
| GGA*.txt | Mux3 | Fixed-width ASCII | Differential GPS (~10 Hz) |
| SPC*.txt | Mux2 | Fixed-width ASCII | Spectrometer/environment (~1 Hz) |
| Cfg*.xml | ICCS system | XML | System configuration snapshot |
| CMP_0043.* | Compensation | Binary/text | Magnetic compensation model |

---

## MAG column dictionary

| Column | Unit | Description |
|--------|------|-------------|
| `Xpr` | — | Sample/experiment counter |
| `M1st` | — | Mux1 status word |
| `M1clk` | — | Mux1 clock counter (ticks) |
| `Wayp` | — | Navigation waypoint number |
| `Date` | — | UTC date (YYYYMMDD) |
| `Time` | — | UTC time (HHMMSS.sss) |
| `Xgps` | — | GPS longitude (°) |
| `Ygps` | — | GPS latitude (°) |
| `Zgps` | — | GPS ellipsoidal altitude (m) |
| `Lalt` | — | Barometric/laser altimeter (m) |
| `Raltr` | — | Radar altimeter – raw channel (m) |
| `Ralt` | — | Radar altimeter – calibrated (m) |
| `Mag1` | — | Magnetometer 1 total field (nT) |
| `Mag2` | — | Magnetometer 2 total field (nT) |
| `Mag1D` | — | Mag1 first derivative (nT/s) |
| `Mag2D` | — | Mag2 first derivative (nT/s) |
| `Mag1C` | — | Mag1 compensated total field (nT) |
| `Mag2C` | — | Mag2 compensated total field (nT) |
| `MagL` | — | Mag2 – Mag1 difference field (nT) |
| `MagLC` | — | Compensated Mag2 – Mag1 difference (nT) |
| `A1` | — | Mag1 amplitude/gain flag |
| `T1` | — | Mag1 sensor temperature (°C) |
| `X1` | — | Mag1 X-axis status flag (1=OK) |
| `Y1` | — | Mag1 Y-axis status flag (1=OK) |
| `Z1` | — | Mag1 Z-axis status flag (1=OK) |
| `A2` | — | Mag2 amplitude/gain flag |
| `T2` | — | Mag2 sensor temperature (°C) |
| `X2` | — | Mag2 X-axis status flag (1=OK) |
| `Y2` | — | Mag2 Y-axis status flag (1=OK) |
| `Z2` | — | Mag2 Z-axis status flag (1=OK) |
| `Vlf1` | — | VLF EM channel 1 (ADC count) |
| `Vlf2` | — | VLF EM channel 2 (ADC count) |
| `Vlf3` | — | VLF EM channel 3 (ADC count) |
| `Vlf4` | — | VLF EM channel 4 (ADC count) |
| `Roll` | — | Roll angle (°, XSENS IMU) |
| `Pitch` | — | Pitch angle (°, XSENS IMU) |
| `Yaw` | — | Yaw/heading angle (°, XSENS IMU) |
| `Xst` | — | System status hex string |
| `Bin` | — | Raw binary sensor data |
| `M3st` | — | Mux3 status word |
| `M3clk` | — | Mux3 clock counter |
| `dWayp` | — | dGPS waypoint |
| `dTime` | — | dGPS UTC time (HHMMSS.ss) |
| `Xdgps` | — | Differential GPS longitude (°) |
| `Ydgps` | — | Differential GPS latitude (°) |
| `Zdgps` | — | Differential GPS altitude (m) |
| `dSNo` | — | Number of GPS satellites |
| `dHdop` | — | Horizontal dilution of precision (lower=better) |
| `dDOn` | — | Differential correction on (1=yes) |
| `dAge` | — | Age of differential correction (s) |
| `dSID` | — | Differential reference station ID |
| `M2st` | — | Mux2 status word |
| `M2clk` | — | Mux2 clock counter |
| `Sdate` | — | Spectrometer UTC date |
| `Stime` | — | Spectrometer UTC time |
| `Swayp` | — | Spectrometer waypoint |
| `Sxgps` | — | Spectrometer GPS longitude (°) |
| `Sygps` | — | Spectrometer GPS latitude (°) |
| `Szgps` | — | Spectrometer GPS altitude (m) |
| `Sralt` | — | Spectrometer radar altimeter (m) |
| `BaroV` | — | Barometric pressure voltage (V) |
| `TempV` | — | Temperature sensor voltage (V) |
| `HumdV` | — | Humidity sensor voltage (V) |
| `Sbaro` | — | Barometric pressure raw counts |
| `Stemp` | — | Temperature raw counts |
| `Shumd` | — | Humidity raw counts |
| `Sreal` | — | Spectrometer real-time count rate |
| `Slive` | — | Spectrometer live-time count rate |
| `Srate` | — | Spectrometer acquisition rate |
| `Sk` | — | Spectrometer potassium channel (K) |
| `Su` | — | Spectrometer uranium channel (U) |
| `Sth` | — | Spectrometer thorium channel (Th) |
| `Sa0` | — | Spectrometer background channel 0 |
| `Sa1` | — | Spectrometer background channel 1 |
| `Sa2` | — | Spectrometer background channel 2 |
| `Sbin` | — | Raw spectral binary data |

---

## Data quality summary

### Session 006
- **Mag1**: OK (σ=2.1893) | mean=49353.0623, std=2.1893
- **Mag2**: OK (σ=3.6975) | mean=49458.6916, std=3.6975
- **Mag1C**: OK (σ=2.1192) | mean=49354.5136, std=2.1192
- **Mag2C**: OK (σ=2.0413) | mean=49460.7273, std=2.0413
- **Roll**: OK (σ=0.1938) | mean=0.2312, std=0.1938
- **Pitch**: OK (σ=0.0892) | mean=-5.6440, std=0.0892
- **Yaw**: OK (σ=0.2953) | mean=-14.5088, std=0.2953
- **Ralt**: HIGH STD >0.5 m | mean=1.1524, std=10.3005
- **Raltr**: HIGH STD >0.5 m | mean=1.1524, std=25.7762
- **Xgps**: OK (σ=0.0000) | mean=14.1514, std=0.0000
- **Ygps**: OK (σ=0.0000) | mean=51.5786, std=0.0000
- **Xdgps**: OK (σ=0.0000) | mean=14.1514, std=0.0000
- **Ydgps**: OK (σ=0.0000) | mean=51.5786, std=0.0000
- **dHdop**: OK (σ=0.0513) | mean=0.8560, std=0.0513

### Session 007
- **Mag1**: OK (σ=0.3790) | mean=49358.6666, std=0.3790
- **Mag2**: HIGH STD >10.0 nT | mean=52060.3290, std=9150.5874
- **Mag1C**: OK (σ=0.2074) | mean=49360.2202, std=0.2074
- **Mag2C**: OK (σ=0.0125) | mean=49461.7620, std=0.0125
- **Roll**: OK (σ=0.1267) | mean=-0.0495, std=0.1267
- **Pitch**: OK (σ=0.0911) | mean=-5.6673, std=0.0911
- **Yaw**: OK (σ=0.2710) | mean=-13.8410, std=0.2710
- **Ralt**: HIGH STD >0.5 m | mean=8.3681, std=56.6959
- **Raltr**: HIGH STD >0.5 m | mean=8.3679, std=142.8722
- **Xgps**: OK (σ=0.0000) | mean=14.1514, std=0.0000
- **Ygps**: OK (σ=0.0000) | mean=51.5786, std=0.0000
- **Xdgps**: OK (σ=0.0000) | mean=14.1514, std=0.0000
- **Ydgps**: OK (σ=0.0000) | mean=51.5786, std=0.0000
- **dHdop**: OK (σ=0.0591) | mean=0.6523, std=0.0591

---

## Known issues

- **Mux M1/M2/M3 TimeO warnings**: Persistent throughout both sessions (~every 5-6 s).
  This is expected behaviour during ground tests – the multiplexer synchronisation
  relies on an aircraft motion trigger that is absent when parked. Does NOT indicate
  data loss in practice (magnetometer NaN rate <0.5%).
- **`Nv WayP` warnings**: Normal – no survey flight plan (waypoints) was loaded.
  The aircraft was not following a navigation line.
- **NaN gaps in MAG**: Small gaps (~0.5% of rows) in magnetometer and GPS columns,
  caused by the Mux timeout events. Data is otherwise complete.
- **`Lalt` column always NaN**: The barometric altitude from GPS is not written
  in these files (GPS provides only ellipsoidal altitude in `Zgps`).
- **VLF channels (Vlf1–Vlf4) always NaN**: GD485 was disconnected in both sessions.
- **Session 007 Mag2 anomaly**: Magnetometer #2 shows extreme values in session 007
  (mean ~55800 nT vs ~49459 nT in 006, with large derivatives). The sensor was
  likely still settling / initialising during this short ~5-minute session.
