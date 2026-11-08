# OmagMES Product Standards and Wet OEE — Excel Evidence Review

**Prepared:** 2026-11-04  
**Status:** Read-only discovery evidence for owner review. No Excel file, database, or application was changed.  
**Period:** Jan–Oct 2026 monthly source folders.

## 1. Scope and method

Inspected the monthly `OEE Report.xlsx` workbooks, the monthly `Production Report (Block)*.xlsm` workbook containing `Std Data`, and available `Mould drop_OMAG.xlsx` files. Workbooks were opened read-only, with formula text and cached values inspected separately; external links were retained but never refreshed, macros were not run, and no workbook was saved. Formula cells below are source text, not recalculated results. Cached values are historical saved results and may be stale when external workbooks are unavailable.

All ten months have an `OEE Report.xlsx`, `MC_CYCLE_TIME (Block)` and `(Fence)` sheets, and a production report with `Std Data`. `Mould drop_OMAG.xlsx` exists in Jan–Jul and Sep–Oct; it was not present in Aug26. The monthly folders also contain cumulative `Total…OEE_2024.xlsx` workbooks in Jan–Apr and `Total…OEE_2026.xlsx` in May–Jul and Sep–Oct. These are additional OEE summaries, not verified Product-standard masters. No workbook identified by filename as a separate capacity/speed standard was found in the targeted inventory.

## 2. Confirmed business requirements (future OmagMES rules)

- Standard production speed belongs to **Product**, not Mould.
- A Product may have several physical Moulds; each Mould has its own running number/MouldID and belongs to exactly one Product. Only one Mould is installed at a time; no many-to-many Product/Mould relationship is allowed.
- MouldID supports physical identity, usage, reconditioning, and Current/Lifetime Age measured in Press Drops.
- One press stroke is one **Drop**. Drops are not Pieces.
- Each Product needs both `StandardPiecesPerDrop` (positive integer Pieces/Drop) and `StandardCycleTimeSec` (positive decimal seconds per press Drop). These standards are Product-owned and independent; do not infer one from the other or assume identical values across Products.
- Wet Press and Wet Line are one coupled production unit with one Wet Run Log and one Wet OEE. Dry Line/Depallet is independent and its stops do not reduce Wet OEE.
- Intended Performance uses `ActualDrops × StandardCycleTimeSec / OperatingSeconds`; Quality uses IP Camera Wet good Pieces divided by expected Pieces (`ActualDrops × StandardPiecesPerDrop`); Availability comes from the Wet Run Log. Wet Good Pieces are IP Camera records where `line='wet'`.

These confirmed rules govern future design even where historical workbook formulas use a different aggregation or denominator.

## 3. Product standards found in `Std Data`

In each monthly production report, `Std Data` has exact Product Code in column A and report-side Product name in column B. `BC2` is `Cycle Time`, `BC3` is `Second`, and the cycle-time sheet `MC_CYCLE_TIME (Block)!D4` uses a VLOOKUP over columns A:BC with return index 55 (BC). This establishes a Product-specific report cycle-time value expressed in seconds and used as a standard lookup, not a historical actual measurement. The owner has confirmed the future OmagMES unit is seconds per press Drop; the workbook alone does not establish that its historical denominator is a press Drop or prove approval/effective date.

The potential Pieces/Drop value is in column BA, but its two header rows conflict: Thai `BA2` reads `ก้อน/Drop` (blocks per Drop), while `BA3` reads `pcs./pallet`. The row values therefore cannot be certified as Pieces/Drop without source-owner clarification. Example exact CSV code `ZCC010010060011` (CSV name `UNI PAVE 6 CM. - GREY`) appears in row 8 in all ten copies with `BA8=45` and `BC8=26`; the report-side English name matches this example. The `45` is an observed BA value only, not an approved Pieces/Drop. Codes `ZCC010010060011A` and `ZCC010010060011B` appear on rows 9 and 10 with the same BA and BC values, but remain distinct Product Codes.

Exact-code comparison against the 855-row CSV found 800 codes represented at least once in the ten `Std Data` sheets; 55 are absent from this workbook set. Of 118 CSV rows marked `ObservedInProduction=YES`, 110 appear in `Std Data` and 8 do not. Each of those 110 present YES codes has a nonblank saved BA and BC value in at least one monthly snapshot; this is a coverage observation only. Do not assign a missing value or import any observed value as an approved standard by inference. The CSV has 855 unique exact Product Codes (118 YES / 737 NO) and no confirmed Pieces/Drop or standard-speed field.

`MC_CYCLE_TIME (Block)!D4` uses `=VLOOKUP(A4,'[5]Std Data'!$A$1:$BC$65538,55,0)` (monthly link index varies) to retrieve the 55th column, `BC`, by exact Product Code. The Fence sheet uses the corresponding `[3]Std Data` reference. This links the cycle-time graph's `STD` column to a production report copy of `Std Data`. The adjacent daily `ACT` cells are separate lookups from daily sheets, e.g. `E4=VLOOKUP($A4,'[5]1'!$B$34:$T$39,18,0)`.

The production reports' `Std Data` has 833–911 populated exact Product Code rows by month, including repeated exact codes; rows are not equivalent to unique Products. Cycle Time values vary across Products (most observed values are 23–70 seconds; additional values include 3, 100, 150, and 190). Whether unusual values are valid standards, outliers, a different unit, or errors is unresolved.

A duplicate-aware scan found same-month conflicting values for exact CSV-matched codes: BA has 12 codes with conflicts across 98 code/month cases; BC has 10 codes with conflicts across 69 code/month cases. Across the inspected rows/snapshots, 13 codes show more than one BA value and 14 show more than one BC value. Examples include `ZCC0102A5560011` with BC values 40 and 35 in January and 41 and 35 in February, and `ZCC025200000014` with BC values 150 and 30 in each inspected month. Thus a lookup by Product Code alone can return the first duplicate and conceal conflicting values; no row is selected as the Product standard.

For codes without such duplicate conflicts, examples of observed BC snapshot differences include `ZCC010163330011R` (Jan 37; Feb–Oct 36), `ZCC010163330081R` (Jan 37; Feb–Oct 36), `ZCC010415560002K` (Jan 40; Feb–Oct 41), and `ZCC010582260168` (Jan 3; Feb–Oct 30). These values still lack approval and effective-date evidence. BA has within-month and cross-month conflicts; its values are not interpreted as Pieces/Drop until the conflicting stacked headers are resolved.

These are source observations, not approved effective-date changes. Other columns in the wide `Std Data` sheet contain many material/color attributes. In particular, `BA2` reads Thai `ก้อน/Drop` while `BA3` reads `pcs./pallet`; the data values cannot be certified as Standard Pieces per Drop without source-owner confirmation. `AZ` is labeled weight and is not the Pieces/Drop field. Do not equate any ambiguous column to Pieces/Drop or overwrite history/select a standard silently.

## 4. Historical OEE Performance formula and lineage

The `OEE_Monitor` sheets across all ten monthly OEE workbooks have the same formula chain in the inspected day column C (the formulas are copied across days):

| Cell | Formula | Meaning supported by labels/formula |
|---|---|---|
| `C19` | `=IF(C49>0,C20*C21*C22,0)` | OEE is zero when the scheduled/available-time base is not positive; otherwise A×P×Q. |
| `C20` | `=C52` | Availability component. |
| `C21` | `=C88` | Performance component. |
| `C22` | `=C113` | Quality component. |
| `C88` | `=C89*C93` | Performance is the product of two rates. |
| `C89` | `=IF(C90>0,C90/C91,0)` | `C90` Standard Cycle Time divided by `C91` Actual Cycle Time. |
| `C93` | `=IF(C86>0,C91/C86,0)` | Actual Cycle Time divided by `C86` Operating Time. |
| `C90` / `C91` | Sum corresponding Block and Fence monitor cells. | Combined cycle-time minutes. |

Thus the exact spreadsheet Performance is:

`Performance = (Standard Cycle Time / Actual Cycle Time) × (Actual Cycle Time / Operating Time)`

with the guards in the source formulas; algebraically the positive-denominator terms cancel to Standard Cycle Time / Operating Time. It does **not** explicitly reference a `Press Drops` count or the Wet curing-entry IP Camera Good Pieces in this chain. The legacy spreadsheet aggregates separate Block and Fence sheets, unlike the owner-confirmed coupled Wet unit. Therefore it is evidence of the historic report's calculation, **not** the approved Wet OEE definition; the confirmed Product-specific formula above is the design baseline, subject to explicit timing/data-quality policy.

In October, `OEE_Monitor (Block)!C90` and `C91` link to external workbook `[3]Sum!C$28` and `C$29`; Fence equivalents are zero in the saved workbook. The production report's `Sum!C28` / `C29` point to daily sheet `1` `AR52` / `AS52`; the daily `AR52` / `AS52` cells sum rows 34–51, whose row formulas derive cycle-time minutes. The exact owner interpretation of these cells and their relationship to Drop counts was not established. The OEE workbook has saved external links to Loss Time Report, Minor Stoppage Losses, and Production Report (Block), and some months also carry legacy path references. Do not refresh links to validate them.

October's saved cache illustrates the calculation only: `C90=835.6333`, `C91=875.7667`, `C86=900`, `C89=0.95417`, `C93=0.97307`, `C88=0.92848`, `C19=0.74994`. These are cached, externally dependent report values, not verified live calculations or accepted benchmarks.

## 5. Mould-drop register interpretation

Available monthly `Mould drop_OMAG.xlsx` sheets identify mould inventory/assignments and contain day-indexed ACT values. In October sheet `2553`, cells `H4` and `K4` respectively show assignment `LBFL27002` and `=SUMIF(O4:DC4,">0",O4:DC4)`; the monthly file also includes formula-driven day cells such as `O4=VLOOKUP($H4,'[1]1'!$P$34:$Q$39,2,FALSE)`. This is a Mould-associated usage/drop-history source with external daily production references. It is not proof of a Product-owned standard speed, a complete Mould assignment history, an authoritative current MouldID master, or a confirmed per-stroke accumulator. It should inform Mould usage/reconditioning discovery only after its headers, counts, and assignment semantics are confirmed by the owner.

## 6. Findings, conflicts, and owner questions

1. **Standard authority:** Which approved engineering/master source establishes Product Pieces/Drop and speed/cycle time? Is `Std Data!BC` an approved Standard Cycle Time or only a report lookup value?
2. **Units and basis:** Confirm whether cycle-time seconds mean seconds per press stroke/Drop, another machine cycle, or another basis. Confirm the valid units and canonical conversion policy for Standard Speed (e.g. Drops/minute vs Drops/hour) and ensure Drops never mean Pieces.
3. **Pieces per Drop:** Resolve the conflicting `Std Data!BA2` (`ก้อน/Drop`) and `BA3` (`pcs./pallet`) headers. Confirm whether BA data rows represent Pieces/Drop, pieces per pallet, or another quantity, and identify the authoritative field/unit and values. Confirm how duplicate exact Product Code rows are disambiguated. Do not infer from a header fragment, pallet quantity, or output reports.
4. **Effective dates/history:** Are the observed cycle-time snapshot changes intentional? Provide approval/effective dates and treatment of historical OEE when Product standards change.
5. **Performance definition:** Confirm the intended Wet Performance formula and time grain using Product-specific standard and actual Press Drops. Explain how planned time, operating time, mixed Products during one period, zero drops, and Product changes are handled. The legacy OEE formula is cycle-time/time based and aggregates Block/Fence; it is not itself proof of the confirmed Wet formula.
6. **Counters/actuals:** Confirm the source and ownership of actual Press Drops used for Wet Performance, and explicitly keep it separate from Wet Good Pieces from the IP Camera. Confirm whether the approximately five-minute shared counter accumulator serves both Mould age and OEE actual Drops.
7. **Wet boundary:** Confirm the Wet Run Log grain, coupled Press/Wet Line stop classification, and rule excluding independent Dry Line/Depallet stoppages from Wet OEE. Confirm IP Camera event/time grain and corrections for Wet Good Pieces.
8. **Mould history:** Confirm the Mould-drop workbook's assignment keys, ACT meaning/unit, day-total semantics, and how reconditioned Mould age is reset versus Lifetime Age.

Until resolved, retain the confirmed owner rules as the future design baseline; mark Excel values `OBSERVED`, not authoritative master records. The dedicated [Product Production Standard Master design](OmagMES_Product_Production_Standard_Master_Design.md) describes the proposed Product-owned revision model, snapshots, and Wet OEE source map. No schema, table, migration, legacy database, application feature, source workbook, commit, or push was created or changed by this analysis.