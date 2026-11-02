# OmagMES Manufacturing Process Analysis — Jan–Oct 2026

**Status:** Read-only workbook analysis; evidence and coverage limits are stated explicitly.  
**Scope:** OmagMES manufacturing records only. Unrelated legacy database tables were not inspected, and no database or application changes were made.

## 1. Scope, method, and confidence

The production report workbook in each of the ten monthly folders was opened read-only with cached values; macros were not executed and workbook files were not changed. All 31 numeric daily worksheets per monthly workbook were scanned in rows 58 onward. The scan identified production rows by populated Product Code and Lot fields (columns B and M), and dry-output summary rows by populated Lot and positive AQ value. Counts below are outputs of those predicates, not certified totals for every worksheet section or every auxiliary workbook.

Representative records were then inspected with exact cells. The curing, quality-measurement, mould-use, loss-time, and minor-stoppage workbooks were inspected for structure and selected actual rows, primarily for October; curing records and corresponding June production examples were checked directly. The available workbooks include OEE and raw-material reports, but their actual records were not comprehensively reconciled in this analysis. Accordingly, this document does **not** claim a complete audit of every auxiliary event or every cell across all workbooks.

Confidence labels used below:

- **High — directly observed:** exact cell/row values in a named workbook.
- **Medium — repeated pattern:** result of the same scan over all ten monthly production workbooks; business interpretation still requires validation.
- **Unresolved:** source fields are missing, ambiguous, or conflict with other workbook fields.

## 2. Confirmed plant rules and process model

The plant owner confirmed these operating rules for OmagMES:

1. OMAG operates one physical production line shared by Block and Fence products.
2. A product change starts a new Production Run; a Production Lot belongs to exactly one Product.
3. Products are made, transferred into curing, hardened, then depalletized.
4. Every depallet operation must reference the original Production Lot; a Lot may have multiple depallet operations.
5. Product Codes must be matched exactly to the authoritative Product Master. Do not infer identity, color, or mould compatibility from code prefixes/suffixes, normalize away differences, or merge similar codes.

Evidence-based process model:

```text
Production Run on shared line
  -> shift-level production summary (Product Code, name, plan/actual, Lot)
  -> curing-room record (Lot, production date, room, close/open date and time)
  -> hardened product
  -> depallet / dry-output record referencing original Lot
  -> quality inspection and rejection evidence where recorded
```

This is the owner-confirmed process sequence, not a fully traceable transaction chain in the inspected spreadsheets. In particular, curing rows lack a quantity, and the production report's dry-output block does not show enough event-level fields to prove it is a separate depallet transaction ledger.

## 3. Production record structure and ten-month scan

The daily production report presents shift labels in column A, Product Code in B, Product Name in C, planned quantity in E, actual quantity in G, and Production Lot in M. The dry-output block in the same daily sheet includes per-Drop / Cube-out fields around AQ/AR and a Lot field in AU. A report row can contain a shift summary rather than a time-stamped individual production event.

The consistent scan results are:

| Monthly source | Daily sheets | Production rows | Distinct Lot strings | Lots with >1 exact Product Code | Dry-output rows | Distinct dry-output Lot strings |
|---|---:|---:|---:|---:|---:|---:|
| [Jan26 production report](../doc/Jan26/Production%20Report%20%28Block%29.xlsm) | 31 | 73 | 41 | 7 | 69 | 40 |
| [Feb26 production report](../doc/Feb26/Production%20Report%20%28Block%29.xlsm) | 31 | 84 | 40 | 9 | 84 | 40 |
| [Mar26 production report](../doc/Mar26/Production%20Report%20%28Block%29.1.xlsm) | 31 | 101 | 59 | 1 | 101 | 59 |
| [April26 production report](../doc/April26/Production%20Report%20%28Block%29.1.xlsm) | 31 | 84 | 45 | 5 | 76 | 39 |
| [May26 production report](../doc/May26/Production%20Report%20%28Block%291.xlsm) | 31 | 71 | 45 | 2 | 69 | 45 |
| [Jun26 production report](../doc/Jun26/Production%20Report%20%28Block%296.xlsm) | 31 | 76 | 38 | 0 | 71 | 36 |
| [Jul26 production report](../doc/Jul26/Production%20Report%20%28Block%29%201.xlsm) | 31 | 110 | 72 | 1 | 105 | 71 |
| [Aug26 production report](../doc/Aug26/Production%20Report%20%28Block%29.xlsm) | 31 | 108 | 66 | 7 | 106 | 66 |
| [Sep26 production report](../doc/Sep26/Production%20Report%20%28Block%29.xlsm) | 31 | 103 | 61 | 6 | 98 | 58 |
| [Oct26 production report](../doc/Oct26/Production%20Report%20%28Block%29.xlsm) | 31 | 68 | 40 | 3 | 63 | 37 |

**Interpretation:** these are screening counts, not counts of confirmed errors. The multi-code test compares raw code strings (so case and suffix differences are preserved); it flags Lots for investigation under the owner-confirmed one-Lot/one-Product rule. Within-month multi-sheet recurrence is common. The scan found 12 exact Lot strings present in more than one monthly workbook; this may represent continuation, file-period overlap, or mis-entry and cannot be classified from folder names alone.

Examples across months include the same Lot `C280526201B` under Product Code `ZCC010163360011` on June sheets 2–4 (rows 59, 64, 58, 64, and 58). The June row groups explicitly show shifts 1 and 2, so the Lot string is not simply a one-row/one-shift key. See the [June production report](../doc/Jun26/Production%20Report%20%28Block%296.xlsm), sheets 2–4, columns A, B, and M, rows 58–64. This is evidence of repeated shift-sheet records, not proof that physical production was uninterrupted.

## 4. Lot-number behavior: findings and unresolved questions

| Question | Finding from inspected records | Assessment |
|---|---|---|
| Does a Lot remain unchanged across shift records? | June Lot `C280526201B` is present in rows labeled shift 1 and shift 2 on multiple daily sheets. June Lots `C160626201B` and `C170626101B` also appear in multiple dated production sheets (see Section 6). | **Observed recurrence;** suggests a Lot can span shift records. Whether those rows represent continuous production, repeated postings, or separate quantities cannot be proven from the summaries. |
| Does a Lot remain unchanged across production dates? | In June, `C160626201B` appears on sheets dated 18 and 19 June, and `C170626101B` on sheet dated 19 June. The curing log records production dates of 16 and 17 June for those same strings. | **Observed across dated records;** interpretation as production continuation versus an entry/date inconsistency is unresolved. |
| Is a new Lot issued for each product change? | Some shift sections show different Product Codes with different Lots, consistent with the owner rule. Other rows in multiple monthly files associate one Lot string with multiple raw Product Codes. | The business rule is confirmed by the owner; workbook compliance is **not established**. Flag conflicting records; do not repair them automatically. |
| Does the same Lot appear in Production and Depallet? | Production and dry-output Lot fields overlap for 40/40 scanned January production Lots, 40/40 in February, 59/59 in March, and similarly in most months (37/40 in October). They are fields in the **same daily production workbook**, not an independently validated depallet event register. | **Same-report linkage observed;** independent depallet trace and event count are unresolved. |
| Do exact Lot strings repeat across monthly workbooks? | The ten-month scan found 12 Lot strings in more than one monthly workbook. Examples include `C280126201B` in Jan/Feb, `C270726201B` in Jul/Aug, and `C280926101B` in Sep/Oct. | **High-confidence string recurrence;** whether cross-month recurrence is legitimate is unresolved. Do not assume month-folder membership establishes production date. |
| What context makes a Lot unique? | One-line production is owner-confirmed; Lot recurrence crosses shifts, sheets, and monthly files. No authoritative Lot-numbering specification or reconciliation key was found in the inspected records. | Unresolved. Do not impose uniqueness on Lot alone, nor assume a particular Plant/Year/Date scope without owner confirmation and validated source data. |

## 5. Critical Product Code / Lot conflicts

### Lot `01161` in October PLAN-ACTUAL

In the [October production report](../doc/Oct26/Production%20Report%20%28Block%29.xlsm), sheet `PLAN-ACTUAL`, row 4 labels columns D–J as Lot, Product Code, Product Name, planned quantity, planned weight, planned units, and actual quantity. Rows 5 and 6 both record Lot `01161` but different exact Product Codes and descriptions:

| Row | Lot (D) | Product Code (E) | Plan pieces (G) | Actual pieces (J) |
|---:|---|---|---:|---:|
| 5 | `01161` | `zcc025010000011` | 2,700 | 1,222 |
| 6 | `01161` | `zcc025010000011du` | 1,300 | 1,303 |

This establishes an observed same-Lot/different-code conflict in the summary, not its cause. Both codes are preserved as written. The sheet date cell E3 is formula-linked to sheet `1` E3 and caches `2026-01-10`; the workbook is in `Oct26`. The month/date context is therefore also unverified. Rows 32–33 of the same sheet record a similar two-code pattern for Lot `02162` (different exact codes and descriptions).

### Daily production corroboration and date inconsistency

The same Lot string `C300926201B` appears in the October daily production sheets with different exact codes:

- Sheet `2`, row 67: A=`shift 2`, B=`ZCC025010000011DU`, E=1,317, G=1,314, M=`C300926201B`; E3 is cached `2026-02-10`.
- Sheet `3`, row 58: A=`shift 1`, B=`zcc025010000011`, E=1,517, G=1,512, M=`C300926201B`; E3 is `2026-10-03`.
- Sheet `6`, row 64: A=`shift 2`, B=`zcc025010000011`, E=2,132, G=2,124, M=`C300926201B`; E3 is `2026-06-10`.

The raw Product Code variation and inconsistent date values are both present in cells, not an extraction-column shift. For another same-shift example, July sheet `14`, rows 59, 64, and 65 record Lot `C100726202B` with `ZCC025020000011du` and `ZCC025020000011`; row 65 has shift 2 and the base code. See the [July production report](../doc/Jul26/Production%20Report%20%28Block%29%201.xlsm).

### Product-reference check

The October quality workbook's `Std Data` sheet contains uppercase `ZCC025010000011` at A451 with the product name “CURB 15X30X100 CM. - GREY.” An exact-text lookup there did not find lowercase `zcc025010000011` or either DU spelling. However, the workbook has not been verified by the plant owner as the authoritative Product Master, so this is only a workbook-local reference check—not proof that either exact code is valid or invalid in the authoritative master. The October quality measurement sheet 1 rows 29–35 also use lowercase `zcc025010000011`, but the Lot field (column E) is blank in those rows; this cannot resolve Lot `01161` or `C300926201B`.

**Conclusion:** the records do not distinguish genuine separate Products, incorrect entry, or different reporting contexts. Do not normalize case, remove `DU`, merge codes, or silently change historical records. The authoritative Product Master and original reporting context are required to resolve this conflict.

## 6. Production → curing → depallet evidence

### Production and curing

The [curing log](../doc/Aug26/1.%E0%B8%82%E0%B9%89%E0%B8%AD%E0%B8%A1%E0%B8%B9%E0%B8%A5%E0%B9%80%E0%B8%9B%E0%B8%B4%E0%B8%94-%E0%B8%9B%E0%B8%B4%E0%B8%94%E0%B8%AB%E0%B9%89%E0%B8%AD%E0%B8%87%E0%B8%9A%E0%B9%88%E0%B8%A1%E0%B8%AA%E0%B8%B4%E0%B8%99%E0%B8%84%E0%B9%89%E0%B8%B2.xlsx), sheet `Aug26`, has actual Lot-level room records in rows 3–4. The columns include production date, shift, product name, produced Lot, room, room close/fill date and time, room open date and time, actual open fields, operator, and status. Examples:

- Row 3: produced date 17-Jun-2026; Lot `C170626101B`; room-close date/time 18-Jun 06:00; room-open date/time 18-Jun 22:00.
- Row 4: produced date 16-Jun-2026; Lot `C160626201B`; room-close date/time 16-Jun 16:00; room-open date/time 17-Jun 08:00.

The [June production report](../doc/Jun26/Production%20Report%20%28Block%296.xlsm), sheet `18`, row 65 records `C160626201B` with Product Code `ZCC01041116M061-1`, planned 8,678, actual 8,640, shift 2, and sheet date 18-Jun-2026. Sheet `19`, row 58 records that Lot again with the same code, planned 11,452, actual 11,400, shift 1, and sheet date 19-Jun-2026. Sheet `19`, rows 59 and 64 record `C170626101B` with Product Code `ZCC010224440011FT`, actual quantities 1,632 and 3,072, respectively, on sheet date 19-Jun-2026.

These are useful exact-Lot links between production sheets and curing entries. They also show that Lot strings can appear in production records dated later than the curing log's “production date.” The source does not provide a production-to-curing quantity transfer, so the timing and quantity reconciliation remain unresolved; the recurrence might represent continued production, partial transfer, or a date/entry issue.

### Depallet / dry-output

In the daily production sheets, columns AQ/AR are labeled for output “to Drop” and “Cube out,” with Lot in AU. Same-row Lot overlap with production Lot M is observed in the all-month scan. The block is embedded in the daily production report and has no separate event timestamp/operator or explicit transaction key in the inspected rows. It is therefore treated here as a **dry-output/depallet-related summary**, not verified as an independent depallet transaction ledger. No independent workbook trace was established from production Lot through curing quantity to one or more depallet event quantities.

## 7. Quality, downtime, mould, material, and OEE records

- **Quality measurements:** The October [quality measurement workbook](../doc/Oct26/%E0%B8%9A%E0%B8%B1%E0%B8%99%E0%B8%97%E0%B8%B6%E0%B8%81%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%AB%E0%B8%99%E0%B8%B2%E0%B8%9C%E0%B8%B4%E0%B8%A7%E0%B8%AB%E0%B8%99%E0%B9%89%E0%B8%B2-%E0%B8%84%E0%B8%A7%E0%B8%B2%E0%B8%A1%E0%B8%AA%E0%B8%B9%E0%B8%87-%E0%B8%99%E0%B9%89%E0%B8%B3%E0%B8%AB%E0%B8%99%E0%B8%B1%E0%B8%81%E0%B8%9A%E0%B8%A5%E0%B9%87%E0%B8%AD%E0%B8%81%202026.xlsx) has timed sample rows with dimensions/weight measurements. Sheet `2`, rows 32–35, records Lot `C021026101B`, code `zcc010010060011`, hourly times 11:30–14:30, and measurements. Sheet `1`, rows 29–35, has product/time/measurement values but blank Lot cells. Quality measurements are not, by themselves, a rejection transaction ledger; no complete Lot-level quality/rejection reconciliation was completed.
- **Downtime:** The October [Loss Time Report](../doc/Oct26/Loss%20Time%20Report.xlsx) contains monthly/day sheets, shift-level loss categories, and a code/meaning reference. The reference lists categories such as cleaning, color change, setup, and mould change by size. The selected day-sheet entries are category/duration summaries; they do not carry the production Lot in the reviewed rows. This supports loss-category reporting, not Lot-level attribution or complete changeover event chronology.
- **Minor stops:** The October [Minor Stoppage Losses report](../doc/Oct26/Minor%20Stoppage%20Losses.xlsx) organizes loss categories and seconds by shift/day. The inspected form includes machine-manual and waiting-for-mix categories. It is an aggregate loss report, not a Lot-level event trace.
- **Mould use:** The October [Mould drop register](../doc/Oct26/Mould%20drop_OMAG.xlsx) has a product/mould list and day-indexed ACT columns; for example, sheet `2569`, row 6 shows mould inventory entry `NKFL01171` and recorded ACT values. The reviewed register does not associate an actual mould-change start/end event with a production Lot. Mould compatibility must not be inferred from its product labels or code patterns.
- **Material and OEE:** October contains raw-material, yield, logger, OEE, and summary workbooks, but their actual populated records were not reconciled against Lots or the sampled production exceptions here. No conclusions about Lot-specific material consumption, OEE, or yield are asserted.

## 8. Data-quality findings and evidence limitations

1. **Lot-to-product conflicts:** The all-month screening found multi-code Lot strings in nine of ten monthly reports (none detected in June under the selected predicate). These are exception flags under the owner-confirmed one-Lot/one-Product rule, not automatically proven operator errors. October's `01161` and `C300926201B` examples were directly verified.
2. **Date context is unreliable in some workbooks:** In the October workbook, daily sheet `2` E3 is `2026-02-10`, sheet `3` E3 is `2026-10-03`, sheet `6` E3 is `2026-06-10`, and `PLAN-ACTUAL` E3 links to sheet `1` E3 and caches `2026-01-10`. These values do not consistently align with the October folder. Cross-month Lots therefore cannot be interpreted as date errors or genuine carryovers without validating workbook source and intended report period.
3. **Case and suffix variation are preserved:** Examples include uppercase/lowercase versions and `DU`/`du`/no suffix. Raw string comparison is intentional; exact Product Master matching is still pending.
4. **No verified event-level end-to-end trace:** production summaries have Lot and shift fields; curing has room/time fields but no quantity; dry-output summaries have Lot and output counts but are not independently validated transactions; quality and downtime sources do not consistently carry the Lot.
5. **Repeated rows are not automatically duplicates:** Same Lot/product records can appear in multiple shifts or sheets. Without source row IDs, event timestamps, or quantity-transfer references, it is not safe to deduplicate them or sum every repeated row as a unique physical event.
6. **Scope boundary:** The analysis did not inspect the SQL Server, unrelated legacy tables, application code, or `.env`; did not execute macros; and did not comprehensively audit all auxiliary reports or all workbook formula results. The preceding discovery/assessment/design documents were not modified.

## 9. Conclusions and validation needed before database design

**Verified:** the plant-owner rules define a single shared line and a one-Product-per-Lot relationship; all ten monthly production reports contain populated shift/Lot records; selected Lots recur across shifts and sheets; October has a directly observed `01161` two-code conflict; and two June Lots link between production sheets and a curing room log.

**Not verified:** that any code pair is a single Product or two valid Products; that monthly workbook date cells represent the intended reporting period; the uniqueness scope or issuance trigger of Lot numbers; curing quantities/transfers; whether the daily dry-output block is a true depallet transaction source; and complete Lot-specific quality, mould, downtime, material, or OEE lineage.

Before treating the historical data as authoritative or using it to finalize data rules, obtain:

1. The plant-owner-approved authoritative Product Master with exact case-sensitive code values and effective dates.
2. Confirmation of the intended date/reporting period for each daily workbook and correction history for the October date mismatch.
3. Operator/source-system explanation for Lots `01161`, `02162`, `C300926201B`, and the 12 cross-month repeated Lot strings; preserve original values during investigation.
4. Curing quantity/transfer evidence and a distinct depallet event register containing original Lot, quantity, event time, and event reference.
5. A verified definition for planned/actual/reject quantities, shift boundaries, production-run boundaries, and repeat-row semantics.
6. A broader, row-addressed audit of the available monthly quality, downtime, mould, material, and OEE reports before claiming full Jan–Oct exception coverage.

No database schema or implementation proposal is made in this report. The mandatory skill was previously verified at `D:\AI\OmagMES\skill\DATABASE_ID_FIRST_DESIGN_SKILL.md`; no database work was performed in this analysis.
