# OmagMES Initial Discovery Report

**Prepared:** 2026-11-02  
**Scope:** Read-only discovery of the database design standard and Excel workbooks under `doc/Oct26`.  
**Status:** Discovery only. No schema, SQL, migration, architecture, or application implementation is proposed. Approval is required before proceeding beyond discovery.

## 1. Database skill compliance summary

The complete mandatory standard was read and verified at [`skill/DATABASE_ID_FIRST_DESIGN_SKILL.md`](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md) (absolute path: `D:\AI\OmagMES\skill\DATABASE_ID_FIRST_DESIGN_SKILL.md`). It governs any future database design discussion for OmagMES. This report does not design tables or propose SQL.

Mandatory rules summarized:

- Every new table uses `id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY` and `Rectime datetime NOT NULL DEFAULT (GETDATE())`, unless an explicitly reviewed exception is approved. `Rectime` represents creation time; application code need not supply it.
- Use authoritative surrogate IDs for relational references and foreign keys when available. Names, descriptions, display labels, and mutable business codes are not relational identity. IDs are opaque and must not encode business meaning.
- New master data follows the same base-column rule; business codes remain separate unique attributes.
- Before adding a foreign key or master, inspect and reuse existing authoritative masters/IDs. Report legacy string-key gaps; do not silently redesign or duplicate legacy masters.
- Text is allowed for explicit business codes, display labels, external identifiers, or historical snapshots; snapshots are not current join/validation identity.
- Configurable business mappings belong in database master/configuration data, not duplicated hardcoded application mappings. Server-side validation must re-read authoritative configuration when saving.
- Seed references must resolve by authoritative unique business key, verify exactly one row, and fail safely otherwise; do not hardcode opaque numeric IDs.
- Do not edit an applied historical migration. Audit existing keys/references before changes; use a new migration and matching rollback if later approved.
- Tests and design review must cover base columns, ID-based relationships, unique business codes, safe seeds, configurable rules, server validation, snapshot use, and legacy compatibility.

## 2. Excel workbook inventory

Inspected all 15 non-lock Excel workbook files in [`doc/Oct26`](../doc/Oct26/). The folder also contains two Excel lock/owner files beginning `~$`; these temporary files were excluded as not independent reports. No `.xls`, `.xlsb`, or other workbook formats were found. All listed sheets were present in workbook metadata; the inspection found no hidden sheets among the workbooks summarized below.

| Workbook (source) | Worksheets | Observed purpose |
|---|---|---|
| [`1.เปรียบเทียบยอดวัตถุดิบใน Silo.xlsx`](../doc/Oct26/1.%E0%B9%80%E0%B8%9B%E0%B8%A3%E0%B8%B5%E0%B8%A2%E0%B8%9A%E0%B9%80%E0%B8%97%E0%B8%B5%E0%B8%A2%E0%B8%9A%E0%B8%A2%E0%B8%AD%E0%B8%94%E0%B8%A7%E0%B8%B1%E0%B8%95%E0%B8%96%E0%B8%B8%E0%B8%94%E0%B8%B4%E0%B8%9A%E0%B9%83%E0%B8%99%20Silo.xlsx) | `July24`, `Aug24`, `SEP24` | Daily Silo quantity reconciliation by material. |
| [`Aggregate Data Logger.xlsx`](../doc/Oct26/Aggregate%20Data%20Logger.xlsx) | `database`, `Pivot`, `Production Report` | Logger feed, material-use pivots/charts, and comparison with production. |
| [`Loss Time Report.xlsx`](../doc/Oct26/Loss%20Time%20Report.xlsx) | `MC Code`, `Data`, `Sum`, `1`–`31` | Equipment loss events, reason/equipment lookups, and monthly summary. |
| [`Minor Stoppage Losses.xlsx`](../doc/Oct26/Minor%20Stoppage%20Losses.xlsx) | `Print`, `1`–`31`, `TOTAL` | Shift-level minor stoppage event durations and monthly totals. |
| [`Mould drop_OMAG.xlsx`](../doc/Oct26/Mould%20drop_OMAG.xlsx) | `Cobble stone`, `2553`, `2554`, `2555`, `2567`, `2569` | Mould availability and production/drop counts by product and period. |
| [`OEE Report.xlsx`](../doc/Oct26/OEE%20Report.xlsx) | `OEE_Monitor`, `OEE_Monitor (Fence)`, `OEE_Monitor (Block)`, `OEE_Report&Analysis`, `MC_CYCLE_TIME (Block)`, `MC_CYCLE_TIME (Fence)`, `PieceWork` | OEE dashboards and standard/actual cycle-time analysis for Fence and Block. |
| [`Production Report (Block).xlsm`](../doc/Oct26/Production%20Report%20%28Block%29.xlsm) | `Std Data`, `สรุปแผนผล`, `Sum`, `PLAN-ACTUAL`, `No.Mould`, `1`–`31` | Daily shift production, standards, plan/actual, material usage and mould reporting. |
| [`Raw Material (Block).xlsx`](../doc/Oct26/Raw%20Material%20%28Block%29.xlsx) | `Sum`, `1`–`31` | Daily raw-material reporting and monthly consolidation. |
| [`Totalสรุปรายละเอียด OEE_2026.xlsx`](../doc/Oct26/Totalสรุปรายละเอียด%20OEE_2026.xlsx) | `วันทำงาน`, `RawOEE` | Working-day counts and monthly/cumulative OEE aggregation. |
| [`Yield วัตถุดิบ.xlsx`](../doc/Oct26/Yield%20%E0%B8%A7%E0%B8%B1%E0%B8%95%E0%B8%96%E0%B8%B8%E0%B8%94%E0%B8%B4%E0%B8%9A.xlsx) | `Yield (Fence)`, `หิน-ทราย (Fence)`, `Yield (Block)`, `หิน-ทราย (Block)` | Material yield and stone/sand usage comparisons for both product lines. |
| [`บันทึกความหนาผิวหน้า-ความสูง-น้ำหนักบล็อก 2026.xlsx`](../doc/Oct26/%E0%B8%9A%E0%B8%B1%E0%B8%99%E0%B8%97%E0%B8%B6%E0%B8%81%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%AB%E0%B8%99%E0%B8%B2%E0%B8%9C%E0%B8%B4%E0%B8%A7%E0%B8%AB%E0%B8%99%E0%B9%89%E0%B8%B2-%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%AA%E0%B8%B9%E0%B8%87-%E0%B8%99%E0%B9%89%E0%B8%B3%E0%B8%AB%E0%B8%99%E0%B8%B1%E0%B8%81%E0%B8%9A%E0%B8%A5%E0%B9%87%E0%B8%AD%E0%B8%81%202026.xlsx) | `Std Data`, `1`–`31`, `Constants`, `Database`, `ความสูง`, `น้ำหนัก`, `ความหนาชั้นผิวหน้า`, `ความชื้น`, `เฉดสี`, `Abnormal`, `Pivot` | Block dimensional, weight, moisture/color inspection and abnormality reporting. |
| [`บันทึกตรวจรับหินทรา.xlsx`](../doc/Oct26/บันทึกตรวจรับหินทรา.xlsx) | `ผลรวม`, `หินเกล็ด`, `หินฝุ่น`, `ทรายละเอียด`, `ปูนเทา`, `Fly ash`, `ปูนขาว`, `ยอดเบิกสี`, `ทรายหยาบ`, `ยอดเคาะ`, `คำนวณอื่นๆ` | Receipt, material weights/moisture and daily totals across materials. |
| [`สรุป.xlsx`](../doc/Oct26/%E0%B8%AA%E0%B8%A3%E0%B8%B8%E0%B8%9B.xlsx) | `Charts`, `Summary` | Plan/actual and daily production summary outputs. |
| [`เทียบยอดของแห้ง (ใหม่1.xlsx`](../doc/Oct26/%E0%B9%80%E0%B8%97%E0%B8%B5%E0%B8%A2%E0%B8%9A%E0%B8%A2%E0%B8%AD%E0%B8%94%E0%B8%82%E0%B8%AD%E0%B8%87%E0%B9%81%E0%B8%AB%E0%B9%89%E0%B8%87%20(%E0%B9%83%E0%B8%AB%E0%B8%A1%E0%B9%881.xlsx) | `ฟอร์ม`, `เทียบยอดการผลิต`, `เก็บข้อมูลใช้เศษคอนกรีต (2)` | Wet/dry production comparison and recycled concrete usage. |
| [`ใบเบิกไม้พาเลทวันเวย์.xlsx`](../doc/Oct26/ใบเบิกไม้พาเลทวันเวย์.xlsx) | `Std Data`, `FORM`, `1`–`31` | Product packaging standards and pallet issue/calculation forms. |

## 3. Worksheet and field inventory

The worksheets use a mix of repeated daily forms (usually numbered `1`–`31`), summary/output layouts, lookup/standard sheets, and logger or inspection data. Field names below are taken from visible worksheet labels. Thai labels are retained as in the source; a translated paraphrase is only used where noted. Numeric/date/text types are inferred from populated Excel cells and formulas, not formal column schemas. Explicit units are reported only where the sheet labels them.

### Production, plan, product and material fields

- [`Production Report (Block).xlsm`](../doc/Oct26/Production%20Report%20%28Block%29.xlsm), worksheets `1`–`31`: reporting date, plant, shift, product code/name, block/body/face designation, product standards, mix/batch counts, material setup per mixer (kg), production counts, waste, and actual material consumption. The daily forms label cement, fly ash, ground tile, additives, sand, aggregate, Calcite, colors, and other materials; headings include standard weight and material setup by mixer (kg), mixer count, total material consumed (kg), block/face ratio, and variance against standard. `Std Data` provides product codes/names and material standards; `PLAN-ACTUAL` has date, shift, lot number, product code/name, planned and actual quantities in blocks/tons/square metres, difference and dry-production fields; `Sum` consolidates monthly material use. `No.Mould` includes mould name/code, units per pallet/area, weight, start/end use, and actual drops. `สรุปแผนผล` consolidates weekly plan versus actual.
- [`Raw Material (Block).xlsx`](../doc/Oct26/Raw%20Material%20%28Block%29.xlsx), worksheets `1`–`31` and `Sum`: daily raw-material usage with monthly summary; formulas link daily records into `Sum`.
- [`Aggregate Data Logger.xlsx`](../doc/Oct26/Aggregate%20Data%20Logger.xlsx), `database`: plant, mixer, month/year/day, report date, shift, logger date/time, sand/stone/cement/fly-ash channels (`SEND(M)`, `DUST(M)`, `STON(M)`, `CEMEN(M)`, `FLY-ASH`, `SEND(F)`, `CEME(F)`), `MIX_NO`, and `CODE_NO`. Logger readings are numeric; time/date and derived labels are formula-based. `Pivot` groups quantities by day/material and block-versus-face classification; `Production Report` compares production-reported values against logger averages.
- [`Yield วัตถุดิบ.xlsx`](../doc/Oct26/Yield%20%E0%B8%A7%E0%B8%B1%E0%B8%95%E0%B8%96%E0%B8%B8%E0%B8%94%E0%B8%B4%E0%B8%9A.xlsx), `Yield (Block)`/`Yield (Fence)` and the corresponding `หิน-ทราย (...)`: output labels show material usage, wet block production and yield percentage; companion sheets include daily date/shift/product/batch with stone and sand quantities. The exact yield numerator/denominator and moisture basis require confirmation.
- [`บันทึกตรวจรับหินทรา.xlsx`](../doc/Oct26/บันทึกตรวจรับหินทรา.xlsx), material tabs and `ผลรวม`: daily receipts/weights for graded stone, dust, fine/coarse sand, grey cement, fly ash, lime and color issue; the summary separates receipts before/after moisture adjustment. Some detailed weighing and adjustment logic is in `คำนวณอื่นๆ`, `ยอดเคาะ` and material-specific tabs.
- [`1.เปรียบเทียบยอดวัตถุดิบใน Silo.xlsx`](../doc/Oct26/1.%E0%B9%80%E0%B8%9B%E0%B8%A3%E0%B8%B5%E0%B8%A2%E0%B8%9A%E0%B9%80%E0%B8%97%E0%B8%B5%E0%B8%A2%E0%B8%9A%E0%B8%A2%E0%B8%AD%E0%B8%94%E0%B8%A7%E0%B8%B1%E0%B8%95%E0%B8%96%E0%B8%B8%E0%B8%94%E0%B8%B4%E0%B8%9A%E0%B9%83%E0%B8%99%20Silo.xlsx), `July24`, `Aug24`, `SEP24`: Calcite, PFA and White Cement sections include date/day, quantity blown in, post-blow quantity, load-cell amount, actual/knocked amount, reported amount, difference and recorder. No measurement unit is clearly indicated in the observed headers.
- [`สรุป.xlsx`](../doc/Oct26/%E0%B8%AA%E0%B8%A3%E0%B8%B8%E0%B8%9B.xlsx), `Summary`: daily plan/actual blocks, tons and area, dry production and related production summary fields. [`เทียบยอดของแห้ง (ใหม่1.xlsx`](../doc/Oct26/%E0%B9%80%E0%B8%97%E0%B8%B5%E0%B8%A2%E0%B8%9A%E0%B8%A2%E0%B8%AD%E0%B8%94%E0%B8%82%E0%B8%AD%E0%B8%87%E0%B9%81%E0%B8%AB%E0%B9%89%E0%B8%87%20(%E0%B9%83%E0%B8%AB%E0%B8%A1%E0%B9%881.xlsx), `ฟอร์ม` and `เทียบยอดการผลิต`: product, color, shift, lot, pallets, drops, blocks, weight and wet/dry comparison. `เก็บข้อมูลใช้เศษคอนกรีต (2)` records concrete-reuse inputs and claimed reductions.
- [`ใบเบิกไม้พาเลทวันเวย์.xlsx`](../doc/Oct26/ใบเบิกไม้พาเลทวันเวย์.xlsx), `Std Data`, `FORM`, `1`–`31`: product code/name and packaging/pallet standards; daily product/quantity fields are used to look up units per pallet and calculate pallet issue requirements.

### Equipment, downtime and OEE fields

- [`Loss Time Report.xlsx`](../doc/Oct26/Loss%20Time%20Report.xlsx), `MC Code`: `M/C code`, `Machine_Group`, `PLANT`; `Data`: reason `Code`, `Meaning`, `Time (min)`; daily sheets `1`–`31`: machine, date/shift and loss events; `Sum`: monthly/day `Std.`, `Act.`, `Diff.` under `Time Data [minute]`, grouped by categories including total time, plan halt time and listed scheduled stops. Machine codes are grouped by plant. A few reason examples visible are cleaning (60 min), color change (30), setup (30), and mould changes (with listed standard times).
- [`Minor Stoppage Losses.xlsx`](../doc/Oct26/Minor%20Stoppage%20Losses.xlsx), `Print`, daily `1`–`31`, `TOTAL`: date, factory, shift, recorder, stoppage reason code/description and up to ten duration entries per form; the duration-entry heading specifies seconds and the total column specifies minutes. `Print` has two repeated side-by-side forms. Example classification is `MS1` / Machine Manual. Numbered entries roll up into `TOTAL`.
- [`OEE Report.xlsx`](../doc/Oct26/OEE%20Report.xlsx), monitor and analysis sheets: factory, date/month range, equipment/production grouping and OEE report outputs; `MC_CYCLE_TIME (Block)` and `(Fence)` compare standard/actual cycle times by product/date/shift; `PieceWork` derives time-related inputs from monitor data. The monitor contains an OEE formula based on a product of three component measures when production is non-zero. Exact component labels and formal definitions were not established from the observed output cells.
- [`Totalสรุปรายละเอียด OEE_2026.xlsx`](../doc/Oct26/Totalสรุปรายละเอียด%20OEE_2026.xlsx), `วันทำงาน`, `RawOEE`: working-day counts and monthly/cumulative OEE totals. The source of all summarized values is not locally self-contained.

### Quality and inspection fields

- [`บันทึกความหนาผิวหน้า-ความสูง-น้ำหนักบล็อก 2026.xlsx`](../doc/Oct26/%E0%B8%9A%E0%B8%B1%E0%B8%99%E0%B8%97%E0%B8%B6%E0%B8%81%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%AB%E0%B8%99%E0%B8%B2%E0%B8%9C%E0%B8%B4%E0%B8%A7%E0%B8%AB%E0%B8%99%E0%B9%89%E0%B8%B2-%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%AA%E0%B8%B9%E0%B8%87-%E0%B8%99%E0%B9%89%E0%B8%B3%E0%B8%AB%E0%B8%99%E0%B8%B1%E0%B8%81%E0%B8%9A%E0%B8%A5%E0%B9%87%E0%B8%AD%E0%B8%81%202026.xlsx), daily sheets and `ความสูง`, `น้ำหนัก`, `ความหนาชั้นผิวหน้า`, `ความชื้น`, `เฉดสี`, `Abnormal`: product, date/shift and inspection readings for dimensions, skin thickness, weight, moisture and color; spec limits, capability statistics (Cp/Cpk), and normal/abnormal classification are present. `Std Data`, `Constants`, `Database` and `Pivot` support standards and summaries.

## 4. Manufacturing process overview

### Confirmed by workbook content

- The reporting context explicitly includes OMAG and product families labeled **Block** and **Fence** (for example, [`Production Report (Block).xlsm`](../doc/Oct26/Production%20Report%20%28Block%29.xlsm), daily worksheets and [`OEE Report.xlsx`](../doc/Oct26/OEE%20Report.xlsx), product-line monitor/cycle-time worksheets).
- Daily production reports are organized by date and shifts and include product codes/names, planned/actual counts, lot numbers, material setups/consumption, waste, and output quantities in blocks, tons and area units (where labeled).
- Logger fields represent a mixer and component channels for body and face material streams. The pivot formula classifies mix number above 200 as face and otherwise as block; that is a workbook formula rule, not yet validated as a complete business rule.
- The equipment master-like list includes codes, machine groups and plant assignments; observed groups include general systems, mixing/material plant and downstream/conveying or production equipment. It does not by itself define an authoritative process route or exact workstation sequence.
- Loss-time reporting has machine identifiers, scheduled/unscheduled reason-code vocabulary and standard minutes. Minor-stoppage forms classify brief stoppages and record durations in seconds before summing in minutes.
- Quality inspection records cover height, skin-layer thickness, weight, moisture and shade/color with standard limits and abnormal summaries. Reject quantity/reason definitions and disposition workflow are not clearly established by the reviewed workbooks.
- Material receiving/adjustment and Silo reconciliation reports compare received/blown-in/load-cell/reported quantities; they are not enough to establish full inventory balance, lot traceability or issue/return rules.

### Not confirmed

A complete manufacturing route (batching, mixing, forming/pressing, curing, finishing, packing, etc.), machine-to-operation mapping, shift boundaries, production order lifecycle and material issue/return policy cannot be stated reliably from these reports alone. These require business-owner/process-engineer confirmation; no such process steps are assumed here.

## 5. Report-to-report relationships

| Observed relationship | Evidence and qualification |
|---|---|
| Daily Block production → plan/actual, material summary, mould use, pallet requirement, daily summary | Formula references from [`Production Report (Block).xlsm`](../doc/Oct26/Production%20Report%20%28Block%29.xlsm) `Sum`, `PLAN-ACTUAL`, `No.Mould`, and daily sheets; linked by workbook sheet/cell references, product codes, date/shift/lot in visible reports. [`ใบเบิกไม้พาเลทวันเวย์.xlsx`](../doc/Oct26/ใบเบิกไม้พาเลทวันเวย์.xlsx) and [`สรุป.xlsx`](../doc/Oct26/%E0%B8%AA%E0%B8%A3%E0%B8%B8%E0%B8%9B.xlsx) also contain production workbook references. |
| Production records ↔ logger data | [`Aggregate Data Logger.xlsx`](../doc/Oct26/Aggregate%20Data%20Logger.xlsx) `Production Report` uses date/shift and mix criteria to average logger channels and compare against production reporting; its workbook also has external links and a pivot cache. |
| Production and stoppage/loss data → OEE/cycle time | [`OEE Report.xlsx`](../doc/Oct26/OEE%20Report.xlsx) has saved external references to loss-time, minor-stoppage and Block production files. This is evidence of formula dependency, not proof of correct/refreshable results. |
| Production → yield and quality | [`Yield วัตถุดิบ.xlsx`](../doc/Oct26/Yield%20%E0%B8%A7%E0%B8%B1%E0%B8%95%E0%B8%96%E0%B8%B8%E0%B8%94%E0%B8%B4%E0%B8%9A.xlsx) links Block/Fence production reports. Quality workbook formulas and an external reference point to a historical production workbook. |
| Equipment and reason lists → loss reporting | [`Loss Time Report.xlsx`](../doc/Oct26/Loss%20Time%20Report.xlsx) contains `MC Code` and `Data` reference sheets used alongside numbered daily forms and the `Sum` output. |
| Material receipt/adjustment ↔ daily use/variance | Receiving, logger, daily production and Silo reports share material labels and quantities, but no verified single transaction key or reconciliation definition was found. |

The reports are workbook-formula-linked, often through dated sheets/cells and historic external paths. Product code, date, shift and lot number appear in multiple reports, but no single shared record identifier was verified. Link freshness and current source versions are unknown.

## 6. KPI and formula definitions

Only formula behavior present in the workbook was verified. This is not a statement that each formula is an approved business definition.

| KPI / calculation | Observed calculation or fields | Source and status |
|---|---|---|
| OEE | Monitor formulas combine three component measures multiplicatively when production is nonzero. The exact displayed component labels, time basis, treatment of planned stops and weighting/aggregation method remain unconfirmed. | [`OEE Report.xlsx`](../doc/Oct26/OEE%20Report.xlsx), `OEE_Monitor`, `OEE_Monitor (Block)`, `OEE_Monitor (Fence)`, `OEE_Report&Analysis`; confirm with OEE owner before adopting. |
| Downtime standard/actual/difference | `Sum` has per-day and monthly `Std.`, `Act.`, `Diff.` minute fields; event duration and reason/minute values feed summaries; some time values are converted to hours. The precise inclusion rules for planned versus unplanned loss require confirmation. | [`Loss Time Report.xlsx`](../doc/Oct26/Loss%20Time%20Report.xlsx), `Data`, daily sheets, `Sum`. |
| Minor stoppage | Repeated durations are captured in seconds, summed and presented as minutes, then rolled up from daily forms. Threshold separating “minor” from ordinary downtime is not evident. | [`Minor Stoppage Losses.xlsx`](../doc/Oct26/Minor%20Stoppage%20Losses.xlsx), `Print`, daily sheets, `TOTAL`. |
| Plan variance | `PLAN-ACTUAL` shows plan and actual blocks/tons/area, differences and percentage differences; sheet formulas calculate percentage difference relative to plan, with divide-by-zero errors where a denominator is zero. | [`Production Report (Block).xlsm`](../doc/Oct26/Production%20Report%20%28Block%29.xlsm), `PLAN-ACTUAL`. |
| Material standard variance | Daily production forms compare actual material usage with standard/setup amounts and include variance values/ratios; reporting is in kg for fields explicitly labeled kg. | [`Production Report (Block).xlsm`](../doc/Oct26/Production%20Report%20%28Block%29.xlsm), daily sheets; standards in `Std Data`. The precise aggregate numerator/rounding rule needs confirmation. |
| Logger-to-report discrepancy | Logger comparison averages material channels by report date/shift and mix threshold, and reports discrepancy/maximum-deviation checks. Mix-number cutoff `>200` is explicit in the workbook formula; tolerance and applicability require validation. | [`Aggregate Data Logger.xlsx`](../doc/Oct26/Aggregate%20Data%20Logger.xlsx), `database`, `Production Report`, `Pivot`. |
| Yield | Workbook reports yield percentage and wet production/material use; exact numerator, denominator, moisture correction, and whether body/face are combined are not established. | [`Yield วัตถุดิบ.xlsx`](../doc/Oct26/Yield%20%E0%B8%A7%E0%B8%B1%E0%B8%95%E0%B8%96%E0%B8%B8%E0%B8%94%E0%B8%B4%E0%B8%9A.xlsx), Block/Fence yield and stone/sand worksheets. |
| Mould remaining drops | Daily/period drop quantities are summed when positive and used with mould/drop-limit fields to calculate remaining drops. Formula errors in lookups mean current results are not dependable without source-link resolution. | [`Mould drop_OMAG.xlsx`](../doc/Oct26/Mould%20drop_OMAG.xlsx), numbered/year-like sheets. |
| Quality capability and abnormality | Inspection values are compared to standards/limits and sheets include Cp/Cpk and normal/abnormal summaries. Sampling plan, subgrouping, acceptance rules and reject linkage are not confirmed. | [`บันทึกความหนาผิวหน้า-ความสูง-น้ำหนักบล็อก 2026.xlsx`](../doc/Oct26/%E0%B8%9A%E0%B8%B1%E0%B8%99%E0%B8%97%E0%B8%B6%E0%B8%81%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%AB%E0%B8%99%E0%B8%B2%E0%B8%9C%E0%B8%B4%E0%B8%A7%E0%B8%AB%E0%B8%99%E0%B9%89%E0%B8%B2-%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%AA%E0%B8%B9%E0%B8%87-%E0%B8%99%E0%B9%89%E0%B8%B3%E0%B8%AB%E0%B8%99%E0%B8%B1%E0%B8%81%E0%B8%9A%E0%B8%A5%E0%B9%87%E0%B8%AD%E0%B8%81%202026.xlsx), daily/measurement/`Abnormal` sheets. |
| Material receiving moisture adjustment | Summary distinguishes quantities before and after moisture adjustment and material tabs include weights/calculation fields. Formula meaning and approved adjustment basis need confirmation. | [`บันทึกตรวจรับหินทรา.xlsx`](../doc/Oct26/บันทึกตรวจรับหินทรา.xlsx), `ผลรวม` and material worksheets. |
| Silo variance | Formula columns compare reported and load-cell or prior quantities; sampled formulas include row-shifted references and differences whose sign does not consistently match an obvious column interpretation. | [`1.เปรียบเทียบยอดวัตถุดิบใน Silo.xlsx`](../doc/Oct26/1.%E0%B9%80%E0%B8%9B%E0%B8%A3%E0%B8%B5%E0%B8%A2%E0%B8%9A%E0%B9%80%E0%B8%97%E0%B8%B5%E0%B8%A2%E0%B8%9A%E0%B8%A2%E0%B8%AD%E0%B8%94%E0%B8%A7%E0%B8%B1%E0%B8%95%E0%B8%96%E0%B8%B8%E0%B8%94%E0%B8%B4%E0%B8%9A%E0%B9%83%E0%B8%99%20Silo.xlsx), all monthly sheets; do not infer intended formula. |

## 7. Candidate MES functional modules

These are discovery candidates derived from observed reporting, not approved scope or architecture:

1. Production reporting and plan-versus-actual (date, shift, product, lot, quantities).
2. Product and production-standard reference management (product/material standards and packaging attributes).
3. Material consumption and batch/logger capture, reconciliation, and variance reporting.
4. Material receiving, moisture adjustment, Silo/load-cell reconciliation, and inventory movement visibility.
5. Equipment/machine and workstation reference with downtime and minor-stoppage reporting.
6. OEE and cycle-time reporting for Block/Fence.
7. Quality inspection, specification limits, abnormal findings and potential reject/yield reporting.
8. Mould/tooling use and drop-life tracking.
9. Packaging/pallet issue calculation and recycled-material reporting.
10. Operational summaries, dashboards and exportable reports.

## 8. Potential data entities (conceptual only)

These are nouns/topics observed in forms; they are **not a database design** and no table structure, key, cardinality or migration is specified: plant/factory; shift; product and product standard; material and material standard; production/plan/lot record; batch or mixer/logger observation; material consumption and receipt/adjustment; equipment/machine/workstation; downtime reason/event; OEE/cycle-time observation; quality measurement/specification/abnormal result; mould/tooling and drop count; packaging/pallet record; recycled concrete usage; and report period/output. Any future relational model must first audit existing authoritative sources and follow the database skill in section 1.

## 9. Missing information, inconsistencies and open questions

### Verified limitations and data concerns

- [`Production Report (Block).xlsm`](../doc/Oct26/Production%20Report%20%28Block%29.xlsm) contains a VBA project. Its VBA source was not inspected or executed. No macros were run.
- Multiple workbooks contain external links, including historical local paths and a temporary Internet-cache `.xls` source. The referenced sources may be missing or stale. Workbook links and cached formula values were inspected, not refreshed.
- Cached spreadsheet errors were observed: about 67,291 in [`OEE Report.xlsx`](../doc/Oct26/OEE%20Report.xlsx), 35,672 in [`Mould drop_OMAG.xlsx`](../doc/Oct26/Mould%20drop_OMAG.xlsx), 37,278 in the 2026 quality workbook, 3,588 in the Block production workbook, 2,232 in the logger production-comparison output, 306 in [`Totalสรุปรายละเอียด OEE_2026.xlsx`](../doc/Oct26/Totalสรุปรายละเอียด%20OEE_2026.xlsx), and smaller counts in material receipt, dry-production comparison and pallet reports. Errors include `#REF!`, `#N/A`, `#VALUE!` and `#DIV/0!`. Counts refer to saved cached error cells, not recalculated results; presence of an error does not establish cause.
- `Aggregate Data Logger.xlsx` has external-link parts, pivot caches and charts; no `connections.xml` was found. This does not rule out integrations external to the file.
- Silo formulas have suspicious row references/sign behavior in sampled formulas (for example, `D10-F11` and `N3-P4`); intent is unclear.
- File/tab naming and historical dates are mixed: Silo sheets are named `July24`/`Aug24`/`SEP24`; the quality workbook is titled 2026 but links to an older-named workbook; production daily forms also use mixed Excel serial dates and text date strings.
- Some fields do not have clearly stated units, and many forms use merged/repeated headings or wide cell layouts. Numeric values may be stored as serial dates, numbers, or text depending on the sheet.

### Business-owner clarifications needed

1. Which plant/factory, product line, and process steps are in OmagMES scope? What are the authoritative operation and workstation sequences for Block and Fence?
2. What are the official shift names and start/end times, date attribution for overnight shifts, and production reporting cut-off rules?
3. What is the approved OEE definition: availability/performance/quality components, numerator/denominator for each, planned-stop treatment, minor-stoppage threshold, zero-production handling, and aggregation/weighting across machines and shifts?
4. Which loss categories are planned versus unplanned, and what are the authoritative equipment/reason codes and standard-duration rules?
5. What precisely qualifies as production quantity, good output, waste, reject, rework and yield? Are rejects recorded by reason, lot, operation, or inspection sample?
6. What formula and moisture basis define raw-material yield? How do body/face streams, recycled concrete, and wet/dry production reconcile?
7. What units and sign conventions are intended for Silo blow-in, load-cell, actual, reported and variance fields? Which Silo formulas are correct?
8. How are products, materials, recipes, equipment, moulds, suppliers, lots, shifts and plant identities governed, and which reference sources are authoritative?
9. What are material inventory rules for receipts, moisture adjustment, silo balances, consumption, returns, waste, pallet issues and stock reconciliation?
10. Which external workbook paths/files are authoritative and current? Should historic report links be replaced by local records or preserved only for audit?
11. Are the cached spreadsheet errors known placeholders, expected unmatched lookups, or data defects? Which reports must be reconciled before they can be used as acceptance criteria?
12. What are the quality sampling frequency/subgroup rules, specification revision rules, Cp/Cpk method and abnormal/reject disposition workflow?

## 10. Recommended next analysis steps

1. Confirm the open business definitions above with production, maintenance, quality and inventory owners; prioritize shifts, process routing, OEE, yield and material units.
2. Identify authoritative/current source workbooks, external link targets and source owners; decide whether saved links and cached values are trustworthy.
3. Reconcile and document formulas with report owners, especially OEE components, loss classification, yield, moisture adjustment, Silo differences and product/material variance.
4. Obtain/read-only review of the VBA source and any relevant external connections with the workbook owner; do not run macros as part of this discovery.
5. Establish a validated field dictionary (label, meaning, unit, source, manual/calculated/system-entered, range and update cadence), including Thai/English terminology.
6. Assess formula errors and duplicate/overlapping reporting using approved source data and report owner sign-off; do not use cached error values as intended outcomes.
7. After explicit approval, audit any existing authoritative systems/masters against the ID-first skill before beginning architecture or implementation.

## Method and limitations

Workbooks were inspected read-only by reading their OOXML contents: workbook/sheet metadata, cell values, formula text, cached cell values, defined names, and workbook package relationships. No Excel application session was available, so formulas were not recalculated and visual formatting, print behavior, VBA source, connection behavior, external-link refreshes, and macro execution were not tested. No source workbook was modified. Conclusions marked as inferred are based only on labels, formula references and report layout; they are not confirmed business rules.
