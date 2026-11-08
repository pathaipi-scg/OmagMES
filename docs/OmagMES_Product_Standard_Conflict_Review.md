# OmagMES Product Standard Conflict Review — Jan–Oct 2026

**Prepared:** 2026-11-08  
**Status:** Read-only evidence register for factory/engineering review. No standard value is selected, averaged, corrected, or approved by this report.  
**Related:** [Product Production Standard Master design](OmagMES_Product_Production_Standard_Master_Design.md), [confirmed business rules](OmagMES_Confirmed_Business_Rules.md), [Excel evidence analysis](OmagMES_Product_Standards_and_Wet_OEE_Excel_Analysis.md), and the [conflict register CSV](OmagMES_Product_Standard_Conflict_Review.csv).

## 1. Confirmed units and derived rates

The owner has confirmed the meanings of the source fields:

- `Std Data!BA` is **Pieces per Press Drop** (`StandardPiecesPerDrop`, Pieces/Drop).
- `Std Data!BC` is **seconds per Press Drop** (`StandardCycleTimeSec`, seconds/Drop).
- Both standards belong to **Product**, not Mould. One press stroke is one Drop, not one Piece.

The corresponding rates are derived from cycle time and are not separate workbook-authoritative inputs:

- Standard Drops/minute = $60 / StandardCycleTimeSec$.
- Standard Drops/hour = $3600 / StandardCycleTimeSec$.
- Standard Pieces/hour = $StandardDropsPerHour \times StandardPiecesPerDrop$.

No new source column or separately stored rate is implied; storing derived rates would require an explicit design decision. Units are confirmed, but each historical numeric value remains evidence only until the factory resolves conflicts and approves its source/revision/effective date.

## 2. Scope and method

A read-only scan covered the `Std Data` worksheet in each monthly `Production Report (Block)` workbook for Jan–Oct 2026. Product Codes were compared as exact strings (case-sensitive; no trimming, uppercasing, suffix removal, or name matching). For each exact code, all populated rows were inspected, including repeated code rows in one sheet. Conflict means at least two distinct saved numeric values for the same exact Product Code and field across the scanned rows. Scope distinguishes duplicate-row disagreements within one monthly workbook from disagreements across month snapshots; both can occur.

The scan inspected formula and saved-value workbook views, used the saved cached values for this evidence register, and did not calculate formulas, refresh external links, run macros, save or modify workbooks. A cell locator in the CSV is shown as `Month[Cell]`; the worksheet is `Std Data`. The workbook corresponding to each month is listed below, so each locator resolves to a specific source file and row.

| Month | Source workbook path |
|---|---|
| Jan | `doc/Jan26/Production Report (Block).xlsm` |
| Feb | `doc/Feb26/Production Report (Block).xlsm` |
| Mar | `doc/Mar26/Production Report (Block).1.xlsm` |
| Apr | `doc/April26/Production Report (Block).1.xlsm` |
| May | `doc/May26/Production Report (Block)1.xlsm` |
| Jun | `doc/Jun26/Production Report (Block)6.xlsm` |
| Jul | `doc/Jul26/Production Report (Block) 1.xlsm` |
| Aug | `doc/Aug26/Production Report (Block).xlsm` |
| Sep | `doc/Sep26/Production Report (Block).xlsm` |
| Oct | `doc/Oct26/Production Report (Block).xlsm` |

## 3. Conflict totals

- **25** exact Product Codes have at least one BA or BC conflict.
- **13** exact Product Codes have conflicting BA values; **17** have conflicting BC values. These groups overlap.
- **22** of the 25 codes exactly match the 855-row Product Master CSV; **3** do not. The three unmatched strings are lowercase codes and remain unmatched under the confirmed exact-code rule.
- Conflict review must retain each candidate value and its source locator. None of the observed values is designated as the winner.

## 4. Complete exact-code review list

Values are displayed without ranking or preference. “Within month” means duplicate rows for the exact code disagree in one or more monthly sheets; “across months” means month snapshots disagree. The CSV contains the month/cell locators for each candidate value.

| Exact Product Code | Std Data Product name (source) | BA candidates (Pieces/Drop) | BC candidates (seconds/Drop) | Conflict scope | Exact CSV match |
|---|---|---:|---:|---|---|
| `ZCC01016226B23S` | ศิลาเหลี่ยม 20X20X6 ซม. สีฟ้า B2+3S | — | 30, 60 | BC: within month and across months | Yes |
| `ZCC010163330011R` | กระเบื้องหน้าเรียบ 30*30*3.5สีเทา | — | 36, 37 | BC: across months | Yes |
| `ZCC010163330081R` | กระเบื้องหน้าเรียบ 30*30*3.5สี GREEN | — | 36, 37 | BC: across months | Yes |
| `ZCC01021226091S` | บล็อกลากูน่า 20X20X6 ซม. สีขาว S | — | 55, 60 | BC: within month and across months | Yes |
| `ZCC01021446091S` | บล็อกลากูน่า 40X40X6 ซม. สีขาว S | — | 50, 60 | BC: within month | Yes |
| `ZCC0102A5560011` | LA 50x50x6 CM. - ORANGE / ลายดาราวดี - GREY | — | 35, 40, 41 | BC: within month and across months | Yes |
| `ZCC01041116M021` | Laguna Maldives 10x10x6 cm. - Red Coral | 8, 30 | — | BA: within month | Yes |
| `ZCC01041116M041` | Laguna Maldives 10x10x6 cm - Yellow Sandy | 8, 30 | — | BA: within month | Yes |
| `ZCC01041116M061` | Laguna Maldives 10x10x6 cm. - Black Pearl | 8, 30 | — | BA: within month | Yes |
| `ZCC01041116M091` | Laguna Maldives 10x10x6 cm. - White Beach | 8, 30 | — | BA: within month | Yes |
| `ZCC010415560002K` | LA 50x50x6 CM.Grey Stone (GGN) พระเมรุมาศ | — | 40, 41 | BC: across months | Yes |
| `ZCC010415561LG1` | Laguna 50x50x6 cm. -Grey Ston (GGN) / พระเมรุมาศ | 2, 4 | 50, 51 | BA: within month and across months; BC: within month | Yes |
| `ZCC010582260168` | CPACDRAINBLOCK(DRAIN OUT2)-HONEY BROWN | — | 3, 30 | BC: across months | Yes |
| `ZCC012001160011` | Lucky stone Grey 2 / แกรนิตโค้ทติ้งสโตน เทา | 8, 99 | — | BA: across months | Yes |
| `ZCC012001160011-1` | Lucky stone Grey 1 / แกรนิตโค้ทติ้งสโตน เทา | 99, 120 | — | BA: within month and across months | Yes |
| `ZCC012001160019` | Lucky stone Grey 3 / แกรนิตโค้ทติ้งสโตน เทาเข้ม | 8, 99 | — | BA: within month and across months | Yes |
| `ZCC012001160127` | Lucky stone Grey / แกรนิตโค้ทติ้งสโตน เบท | 8, 99 | — | BA: within month and across months | Yes |
| `ZCC02514000M091` | ขอบลากูน่า มัลดิฟ15*30*100 ซ.ม. ไวท์บีช | — | 50, 70 | BC: within month and across months | Yes |
| `ZCC025200000014` | FLEX CURB 12x14x20 CM.BLACK GREY | 1, 56 | 30, 150 | BA and BC: within month | Yes |
| `ZCC025200000023` | FLEX CURB 12x14x20 CM.DARK RED | 1, 56 | 30, 150 | BA and BC: within month | Yes |
| `ZCC025200000051` | FLEX CURB 12x14x20 CM.LIGHT BROWN | 1, 56 | 30, 150 | BA and BC: within month | Yes |
| `ZCC025200000052` | FLEX CURB 12x14x20 CM.DARK BROWN | 1, 56 | 30, 150 | BA and BC: within month | Yes |
| `zcc010165560011` | LA 50x50x6 CM. -เทา / Laguna 50x50x6 cm. เทา | — | 35, 50 | BC: within month | No |
| `zcc010165560031` | LA 50x50x6 CM. - ORANGE / Laguna 50x50x6 cm. ส้ม | — | 35, 50 | BC: within month | No |
| `zcc011491260510` | POROUS 10x20x6 CM ส้ม / JAZZY ORANGE | — | 28, 50 | BC: within month | No |

Names are shown for identification only and are shortened in a few summary rows; where source rows have differing descriptions, they do not establish Product identity or authorize name selection. The CSV preserves the source-name text, exact Product Codes, and all per-value source cell locators in the [register](OmagMES_Product_Standard_Conflict_Review.csv).

## 5. Factory review required

For each candidate code, the responsible Product/Process/Engineering owner should:

1. Verify the code and physical product identity against the authoritative Product Master, especially the three exact-code CSV misses and any code with multiple source descriptions.
2. Review every locator/value in the CSV against the specified monthly workbook and confirm whether duplicate rows represent distinct configurations/products, an obsolete row, or an erroneous/conflicting entry. Do not merge or normalize codes by appearance.
3. State the approved BA Pieces/Drop and BC seconds/Drop values, the authoritative source, approver, reason, and effective-from date (and end date if applicable). Resolve each disagreement explicitly; do not choose “latest month” automatically.
4. Confirm whether a historical correction is needed and how it should be versioned. Preserve the observed evidence and decision trail even if a source workbook is later corrected.

Until that review is recorded, both numeric standards remain **unresolved for these 25 codes**. There is no winner, average, bulk seed, historical backfill, or workbook correction authorized by this review. No SQL, DDL, migration, application code, database write, source workbook edit, commit, or push was performed.
