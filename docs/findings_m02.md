# M02 — Findings of the Mongolia 2022 campaign

Campaign-specific results and problems, by step. The READMEs stay general; what happened in
this data goes here. Newest entries first inside each step.

---

## Steps 1–2: GPS lag

- 5 lines were flown in both directions (4 with enough common track). Lags: +0.25, +0.20, +0.20
  and 0.00 s; median 0.20 s. Resolution 0.05 s, only 4 pairs.
- Tolerance (line spacing 250 m, average speed 38 m/s): 62.5 m, 1.64 s. 0.2 s is 7.6 m of position
  error, far below it.
- Decision `LAG_NEGLIGIBLE`: positions unchanged. If it were applied, the value at a point would
  change by a median of 0.07 nT, below 0.9 nT in 95 % of the points, 18 nT at most.

## Step 3: Diurnal correction (run `test_001`)

- 17 of 18 flights corrected. Variation between −10.3 and +8.6 nT; correction added has a
  median of 3.2 nT, under 7.9 nT in 95 % of the points, 10.3 nT at most.
- `24.04.2022/Tagesgang00428.txt` is a copy of `22.04.2022/Tagesgang00427.txt` (header `21 IV 22`).
  The real recording of 24 April (header `23 IV 22`) is stored in `26.04.2022/Tagesgang00434.txt`.
  Matching on absolute UTC time handles it; the duplicate readings are kept once.
- One base station for the whole campaign (47.808° N, 107.574° E, a reading every ~3 s).
- With the reference 59150 nT and the base station between 59140 and 59158 nT, the corrections are
  a few nT.
- The campaign is flown in the local morning (UTC+8), so every Tagesgang file crosses midnight UTC.
- MAG `Time` is missing in about 13 % of the rows. Base readings: normal scatter about 0.25 nT,
  about 1 % discarded as spikes or low quality.
- The survey area is about 25 km across, small enough for one base station.
- Raw against filtered (30 s) base station: the correction differs by 0.04 nT (std), 0.09 nT in
  95 % of the points, 0.70 nT at most. The raw curve is used.

### Reference level of the diurnal correction — noted 2026-11-10

- `diurnal_reference_nT = 59150` (named `igrf_base_field_nT` until 2026-11-10) is the value the specialist used (`data/reference/Readme_Especialista_02.txt`,
  "Mongolia 2022"; in their data `BaseMag + Diurnal` = 59150.00 in every row). `Readme_Especialista_01`
  (58690 nT) belongs to another survey.
- Tried IGRF-13 at the base site (59202 nT) instead: the variation became about −50 nT in every flight,
  because the base station reads ~59152 on average. The 52 nT is the local offset of the base site
  (crustal anomaly, sensor calibration, model error), not diurnal variation, so it must not be
  transferred to the airborne data. Discarded.

### Base station of flight 00434 (26.04.2022) — resolved 2026-11-10

- No Tagesgang recording of ours covers flight 00434: `26.04.2022/Tagesgang00434.txt` is the
  night of 23–24 April (22:21 to 03:37) and the selected lines fly 04:50 to 06:05 UTC.
- The specialist's data has `BaseMag` for that flight (`data/reference/magnetics_example.dat`,
  59140–59150 nT, diurnal −0.4 to +9.7 nT). It is rebuilt as `data/reference/base_station_supplement.csv`
  (`python -m src.m02_magnetics.base_supplement 434`) and used only where our base station has no reading.
- Result: the flight is 100 % corrected (variation −9.7 to +0.3 nT).
- Limit: it is the specialist's filtered base value, so that flight cannot be validated against his
  result. Replace it when the original Tagesgang file is found.
- Check of the method: in flights 427 and 456 our `Diurnal` equals the specialist's (std 0.07 nT,
  at most 0.36 nT).

## Step 4: IGRF — noted 2026-11-10

- Our first run differed from the specialist's `IGRF` by a constant of about −36 nT (−36.2 on
  22 April, −37.1 on 14 May; same spatial pattern, std ≤ 0.1 nT).
- Cause: `ppigrf.igrf` evaluates its latest model (IGRF-14) when no coefficient file is given, so
  the code was not using the `igrf_model: "IGRF-13"` of `project.yaml`, which it never read. For
  2022 the two versions differ by tens of nT. The model is now chosen from `project.yaml`.
- With IGRF-13 the difference to the specialist is −1.55 nT, constant over the 18 flights (std
  0.01–0.1 nT). It matches a height about 50 m lower than the GPS height at 31.7 nT/km, e.g. a
  different height reference; not confirmed.
- The specialist's `Mag1_IGRF` is not `Mag1_Diurnal − IGRF`: it is `Mag1_Diurnal − IGRF + 55.000 nT`
  (std 0.005 nT, all flights, both sensors). A fixed constant added after the IGRF removal, which
  centres the anomaly around zero. Our code does not add it, so our `Mag1_IGRF` is about 55 nT
  lower than his. Decision (2026-11-11): the constant is NOT added; it is documented in the
  `README.md` of `step_04_igrf/`. When comparing with his columns, subtract 55 nT from his.

## Step 5: Heading — noted 2026-11-10

- The code estimated one bias from Mag1 and applied it to both sensors. The specialist's report
  gives a different heading effect per sensor (Mag1 ±0.5 nT, Mag2 ±1.7 nT).
- Now each sensor has its own bias. Ours: Mag1 ±0.59 nT, Mag2 ±1.80 nT (42 east and 47 west lines).
  Against the specialist's correction at each sample: Mag1 differs by 0.10 nT on average (0.20 at
  most), Mag2 by 0.16 nT (0.48 at most). The remaining difference is about the rounding of his values.
- Tie lines (N–S) get no correction, as in the specialist's processing.
- The correction compared is `Mag_IGRF_head − Mag_IGRF`, which does not depend on the pending
  constant of step 4.

## Step 7: Levelling

- The eastern edge is limited by 5 missing tie lines (18 planned traverses and 5 tie lines could not be
  flown, per the specialist's report). The specialist built artificial tie lines from microlevelled
  grids; that is not implemented here.
