# M02 — Findings of the Mongolia 2022 campaign

Campaign-specific results and problems, by step. The READMEs stay general; what happened in
this data goes here. Newest entries first inside each step.

---

## Steps 1–2: GPS lag

- Measured lag about 0.2 s; at the average speed (38 m/s) that is 7.6 m. Tolerance
  `lag_tolerable_s` about 1.6 s (62 m, a quarter of the 250 m line spacing).
- Decision `LAG_NEGLIGIBLE`: positions unchanged. The magnetic value would change by less than
  1 nT in 95 % of the points.

## Step 3: Diurnal correction (run `test_001`)

- 17 of 18 flights corrected. Variation between −10.3 and +8.6 nT; correction added has a
  median of 3.2 nT, under 7.9 nT in 95 % of the points, 10.3 nT at most.
- `24.04.2022/Tagesgang00428.txt` is a copy of `22.04.2022/Tagesgang00427.txt` (header `21 IV 22`).
  The real recording of 24 April (header `23 IV 22`) is stored in `26.04.2022/Tagesgang00434.txt`.
  Matching on absolute UTC time handles it; the duplicate readings are kept once.
- One base station for the whole campaign (47.808° N, 107.574° E, a reading every ~3 s).

### Reference level of the diurnal correction — noted 2026-11-10

- `igrf_base_field_nT = 59150` is the value the specialist used (`data/reference/Readme_Especialista_02.txt`,
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
  (`python -m src.m02_magnetics.base_supplement`) and used only where our base station has no reading.
- Result: the flight is 100 % corrected (variation −9.7 to +0.3 nT).
- Limit: it is the specialist's filtered base value, so that flight cannot be validated against his
  result. Replace it when the original Tagesgang file is found.
- Check of the method: in flights 427 and 456 our `Diurnal` equals the specialist's (std 0.07 nT,
  at most 0.36 nT).

## Step 7: Levelling

- The eastern edge is limited by 5 missing tie lines.
