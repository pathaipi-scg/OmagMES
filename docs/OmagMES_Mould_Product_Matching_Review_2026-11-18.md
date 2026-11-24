# Mould-to-Product Matching Review — Owner Approval Required

**Prepared:** 2026-11-18  
**Disposition:** Read-only candidate review only. No official `ProductID` is assigned by this document. Every candidate below is **SUGGESTED — NOT VERIFIED** and requires owner confirmation.

## Scope and evidence

- Mould source: `Master/Omag_Mould_Master.xlsx`, worksheet `No.Mould`; source records are Excel rows 4–42 (39 rows). Row 43 has a date but no Mould number or model and is separately flagged as incomplete, not counted as a Mould record.
- Product source: live `omagmes.Product`, queried read-only on `SCGLS-NK\\SQLEXPRESS`, database `OMAG`, as `OMAG_MES`. The live table returned 825 records with `id`, `ProductCode`, `ProductName`, `ProductNameThai`, and `ProductFamily`.
- `ProductFamily` is NULL for all 825 live Product records.
- Matching uses source model names and explicit dimensions/thickness where present, compared with live English and Thai names. Color and formulation words are not treated as shape identity. The candidate rank is heuristic, not a probability or approval. Candidates are shown only as a shortlist; omission is not proof of incompatibility.
- The source model text in column B contains the shape/dimension clues used here. Columns C–E describe production count/weight/yield values, not mould geometry; column I and the monthly columns are formula/usage history and were not treated as initial SQL age. No reliable physical mould dimensions are supplied in separate fields.
- All candidates show `ProductCode`, live `Product.id`, both names, `ProductFamily`, and reason/evidence. No descriptions or code patterns were used to set an official Product relationship.

## Source register — all 39 Mould rows

The duplicate MouldCode rows are preserved, not deduplicated. Excel `No.` is a worksheet sequence, not a trusted physical identifier.

| Excel row | Excel No. | MouldCode (column H) | Excel model / Product reference (column B) | Owner disposition |
|---:|---:|---|---|---|
| 4 | 1 | NKFL01103 | ขอบคันหินใหญ่ทรงมน Large curb | Pending |
| 5 | 2 | NKFL00805 | ขอบคันหินเล็กทรงมน Small curb | Pending |
| 6 | 3 | NKFL01171 | UNI-Mini 6 CM. | Pending |
| 7 | 4 | NKFL00806 | คดกริช UNI 6 CM. | Pending |
| 8 | 5 | NKFL01300 | คดกริช UNI 6 CM. | Pending |
| 9 | 6 | NKFL00380 | คดกริช UNI 10 CM. | Pending |
| 10 | 7 | NKFL00742 | บล็อคปลูกหญ้า TURF STONE 8 CM | Pending |
| 11 | 8 | NKFL00741 | บล็อคปลูกหญ้า TURF STONE 8 CM | Pending |
| 12 | 9 | NKFL70901 | บล็อคปลูกหญ้า TURF STONE 9 CM | Pending |
| 13 | 10 | NKFL01172 | บล็อคปลูกหญ้า TURF Sqaure 8 CM | Pending |
| 14 | 11 | NKFL71810 | ศิลาเหลี่ยม RHOMBIC 6 CM | Pending |
| 15 | 12 | NKFL71609 | คฑา QUADRA 6 CM | Pending |
| 16 | 13 | NKFL71929 | อัฐศิลา OCTA 6 CM | Pending |
| 17 | 14 | NKFL71103 | ศิลาเหลี่ยม 10X10X6 | Pending |
| 18 | 15 | NKFL00801 | ศิลาเหลี่ยม 10X20X6 | Pending |
| 19 | 16 | NKFL01101 | ศิลาเหลี่ยม 20X20X6 | Duplicate code — resolve with row 41 |
| 20 | 17 | NKFL71403 | ศิลาเหลี่ยม 20X30X6 | Pending |
| 21 | 18 | NKFL00807 | ศิลาเหลี่ยม 30X30X6 | Pending |
| 22 | 19 | NKFL01295 | 40X40X3.8 No Spacer; converted from 3.5 to 3.8 CM | Pending |
| 23 | 20 | NKFL00435 | 40X40X4 | Pending |
| 24 | 20 | NKFL00436 | 40X40X4 | Pending |
| 25 | 20 | NKFL00437 | 40X40X4 | Pending |
| 26 | 21 | NKFL00438 | 40X40X4 | Pending |
| 27 | 22 | NKFL01088 | 40X40X4 CM No.spacer | Pending |
| 28 | — | NKFL01089 | 40X40X4 CM No.spacer สานเส้น | Pending |
| 29 | 23 | NKFL73006 | 40X40X6 CM | Pending |
| 30 | 24 | NKFL25001 | 50X50X6 CM | Duplicate code — resolve with row 34 |
| 31 | 25 | NKFL25003 | 40X80X6 CM | Pending |
| 32 | 26 | NKFL25004 | 60X60X5 CM | Pending |
| 33 | 27 | NKFL70410 | จัตุรัส CUBE 6 CM | Pending |
| 34 | 28 | NKFL25001 | ศิลาเหลี่ยม 50X50X6 CM | Duplicate code — resolve with row 30 |
| 35 | 29 | NKFL71702 | ศรศิลา ARROW 6 CM | Pending |
| 36 | 30 | NKFL01174 | Cobble stone 6cm.RT3 | Pending |
| 37 | 31 | NKFL01173 | Cobble stone 6cm.RT2 | Pending |
| 38 | 32 | NKFL01170 | Hexagonal Block 6 CM | Pending — no reasonable candidate found |
| 39 | 33 | NKFL01312 | 30X30X3.5 CM | Pending |
| 40 | 33 | NKFL00430 | ศิลาเหลี่ยม 30X30X6 No.spacer | Pending |
| 41 | 34 | NKFL01101 | ศิลาเหลี่ยม 20X20X6 | Duplicate code — resolve with row 19 |
| 42 | 35 | NKFL01195 | Sakura Block 6 CM | Pending — no reasonable candidate found |

**Duplicate MouldCode groups:** `NKFL01101` (rows 19 and 41), `NKFL25001` (rows 30 and 34). These could represent duplicate register entries or repeated physical IDs; owner must confirm. Both cannot be inserted as separate rows under the deployed unique MouldCode constraint. Excel `No.` also repeats (20 at rows 23–25 and 33 at rows 39–40), so it is not suitable as a physical key.

## Suggested Product candidates

Each line is **SUGGESTED — NOT VERIFIED**; `—` means the live ProductFamily value is NULL. Repeated source model names share a shortlist, but each listed MouldCode remains a separate physical record unless the owner says otherwise.

### `NKFL01103` — row 4 — ขอบคันหินใหญ่ทรงมน / Large curb
- **SUGGESTED — NOT VERIFIED:** `ZCC025010000011DU` (id 490) — CURB 15X30X100 CM. - GREY / ขอบคันหินใหญ่ทรงมน สีเทาDU; family —. Evidence: matching Thai/English large rounded curb description.
- **SUGGESTED — NOT VERIFIED:** `ZCC025010000011` (id 489) — CURB 15X30X100 CM. - GREY / ขอบคันหินใหญ่ทรงมน สีเทา; family —. Evidence: matching Thai/English large rounded curb description.
- **SUGGESTED — NOT VERIFIED:** `ZCC025010000011(ทดลอง)` (id 487) — CURB 15X30X100 CM. - GREY(ทดลอง) / ขอบคันหินใหญ่ทรงมน สีเทา(ทดลอง); family —. Evidence: matching shape words; experimental formulation qualifier differs.

### `NKFL00805` — row 5 — ขอบคันหินเล็กทรงมน / Small curb
- **SUGGESTED — NOT VERIFIED:** `ZCC025020000011du` (id 498) — CURB 11X20X50 CM. - GREY / ขอบคันหินเล็กทรงมน สีเทา DU; family —. Evidence: matching Thai/English small rounded curb description.
- **SUGGESTED — NOT VERIFIED:** `ZCC025020000011` (id 499) — CURB 11X20X50 CM. - GREY / ขอบคันหินเล็กทรงมน สีเทา; family —. Evidence: matching Thai/English small rounded curb description.
- **SUGGESTED — NOT VERIFIED:** `ZCC025020000011(พร้อมขอบเข้ามุม)` (id 497) — CURB 11X20X50 CM. - GREY / ขอบคันหินเล็กทรงมน สีเทา; family —. Evidence: matching description; code qualifier indicates a corner-edge variant that requires confirmation.

### `NKFL01171` — row 6 — UNI-Mini 6 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010010060011` (id 5) — UNI PAVE 6 CM. - GREY / คดกริช 6 ซม. สีเทา ; family —. Evidence: nominal 6 cm, UNI model term.
- **SUGGESTED — NOT VERIFIED:** `ZCC010010060011 - 1` (id 662) — UNI PAVE 6 CM -GREY / คดกริช 6 ซม. สีเทา - สูตร 1; family —. Evidence: nominal 6 cm, UNI model term; formulation variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010010060011 - 11` (id 667) — UNI PAVE 6 CM - GREY / คดกริช 6 ซม. สีเทา - สูตร 1; family —. Evidence: nominal 6 cm, UNI model term; formulation variant.

### `NKFL00806` and `NKFL01300` — rows 7 and 8 — คดกริช UNI 6 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010010060011du` (id 1) — UNI PAVE 6 CM. - GREY DU / คดกริช 6 ซม. สีเทา DU; family —. Evidence: nominal 6 cm, matching UNI / คดกริช terms.
- **SUGGESTED — NOT VERIFIED:** `ZCC010010060021du` (id 8) — UNI PAVE 6 CM. - RED / คดกริช 6 ซม. สีแดงDU; family —. Evidence: nominal 6 cm, matching UNI / คดกริช terms; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010010060031du` (id 11) — UNI PAVE 6 CM. - ORANGEdu / คดกริช 6 ซม. สีส้มdu; family —. Evidence: nominal 6 cm, matching UNI / คดกริช terms; color variant.

### `NKFL00380` — row 9 — คดกริช UNI 10 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010010100011` (id 24) — UNI PAVE 10 CM - GREY / คดกริช 10 ซม. สีเทา; family —. Evidence: nominal 10 cm, matching UNI / คดกริช terms.
- **SUGGESTED — NOT VERIFIED:** `ZCC010010100021` (id 26) — UNI PAVE 10 CM - RED / คดกริช 10 ซม. สีแดง; family —. Evidence: nominal 10 cm, matching UNI / คดกริช terms; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010010100031` (id 27) — UNI PAVE 10 CM - ORANGE / คดกริช 10 ซม. สีส้ม; family —. Evidence: nominal 10 cm, matching UNI / คดกริช terms; color variant.

### `NKFL00742` and `NKFL00741` — rows 10 and 11 — TURF STONE 8 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010120080081` (id 108) — TURF STONE 8 CM - GREEN / บล็อคปลูกหญ้า 8 ซม. สีเขียว; family —. Evidence: nominal 8 cm and matching Turf Stone / บล็อคปลูกหญ้า terms.
- **SUGGESTED — NOT VERIFIED:** `สินค้าทดลองผลิตสีน้ำตาล` (id 750) — TURF STONE 8 CM BROWN / บล็อคปลูกหญ้า 8 ซม. สีน้ำตาล; family —. Evidence: nominal 8 cm, matching model; formulation/color variant.
- **SUGGESTED — NOT VERIFIED:** `สินค้าทดลองผลิตสีส้ม` (id 751) — TURF STONE 8 CM ORANGE / บล็อคปลูกหญ้า 8 ซม.สีส้ม; family —. Evidence: nominal 8 cm, matching model; formulation/color variant.

### `NKFL70901` — row 12 — TURF STONE 9 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010120090081` (id 114) — TURF STONE 9 CM - GREEN / บล็อคปลูกหญ้า 9 ซม. สีเขียว; family —. Evidence: nominal 9 cm and matching model description.
- **SUGGESTED — NOT VERIFIED:** `ZCC010370090011` (id 112) — TURF STONE 9 CM - GREY (FACING) / บล็อคปลูกหญ้า 9 ซม. สีเทา (มีผิวหน้า); family —. Evidence: nominal size and shape; facing variant needs confirmation.
- **SUGGESTED — NOT VERIFIED:** `ZCC010120090011` (id 113) — TURF STONE 9 CM - GREY (NO FACING) / บล็อคปลูกหญ้า 9 ซม. สีเทา (ไม่มีผิวหน้า); family —. Evidence: nominal size and shape; facing variant needs confirmation.

### `NKFL01172` — row 13 — TURF Sqaure 8 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010120080081` (id 108) — TURF STONE 8 CM - GREEN / บล็อคปลูกหญ้า 8 ซม. สีเขียว; family —. Evidence: nominal 8 cm and matching turf-block description; source says “Sqaure,” which the candidate name does not explicitly confirm.
- **SUGGESTED — NOT VERIFIED:** `สินค้าทดลองผลิตสีน้ำตาล` (id 750) — TURF STONE 8 CM BROWN / บล็อคปลูกหญ้า 8 ซม. สีน้ำตาล; family —. Evidence: nominal 8 cm and turf-block description; color/formulation variant.
- **SUGGESTED — NOT VERIFIED:** `สินค้าทดลองผลิตสีส้ม` (id 751) — TURF STONE 8 CM ORANGE / บล็อคปลูกหญ้า 8 ซม.สีส้ม; family —. Evidence: nominal 8 cm and turf-block description; color/formulation variant.

### `NKFL71810` — row 14 — RHOMBIC 6 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010090060011` (id 62) — RHOMBIC 6 CM -  GREY / ศิลาหกเหลี่ยม 6 ซม. สีเทา; family —. Evidence: RHOMBIC model term and nominal 6 cm.
- **SUGGESTED — NOT VERIFIED:** `ZCC010090060021` (id 63) — RHOMBIC 6 CM -   RED / ศิลาหกเหลี่ยม 6 ซม. สีแดง; family —. Evidence: RHOMBIC model term and nominal 6 cm; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010090060031` (id 64) — RHOMBIC 6 CM -  ORANGE / ศิลาหกเหลี่ยม 6 ซม. สีส้ม; family —. Evidence: RHOMBIC model term and nominal 6 cm; color variant.

### `NKFL71609` — row 15 — QUADRA 6 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010100060011` (id 69) — QUADRA 6 CM -  GREY / คฑา 6 ซม. สีเทา; family —. Evidence: QUADRA model term and nominal 6 cm.
- **SUGGESTED — NOT VERIFIED:** `ZCC010100060021` (id 70) — QUADRA 6 CM - RED / คฑา 6 ซม. สีแดง; family —. Evidence: QUADRA model term and nominal 6 cm; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010100060031` (id 71) — QUADRA 6 CM -  ORANGE / คฑา 6 ซม. สีส้ม; family —. Evidence: QUADRA model term and nominal 6 cm; color variant.

### `NKFL71929` — row 16 — OCTA 6 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010060060011` (id 54) — OCTA 6 CM -  GREY / อัฐศิลา 6 ซม. สีเทา; family —. Evidence: OCTA / อัฐศิลา model terms and nominal 6 cm.
- **SUGGESTED — NOT VERIFIED:** `ZCC010060060021` (id 55) — OCTA 6 CM - RED / อัฐศิลา 6 ซม. สีแดง; family —. Evidence: matching model and size; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010060060031` (id 56) — OCTA 6 CM -  ORANGE / อัฐศิลา 6 ซม. สีส้ม; family —. Evidence: matching model and size; color variant.

### `NKFL71103` — row 17 — 10X10X6
- **SUGGESTED — NOT VERIFIED:** `ZCC010171160011-1` (id 161) — LINEA 10X10X6 - GREY / ศิลาเหลี่ยม 10X10X6 ซม. สีเทา; family —. Evidence: exact dimensions and matching Thai shape description.
- **SUGGESTED — NOT VERIFIED:** `ZCC010171160021-1` (id 159) — LINEA 10X10X6 - RED / ศิลาเหลี่ยม 10X10X6 ซม. สีแดง; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010171160031-1` (id 168) — LINEA 10X10X6 - ORANGE / ศิลาเหลี่ยม 10X10X6 ซม. สีส้ม; family —. Evidence: exact dimensions; color variant.

### `NKFL00801` — row 18 — 10X20X6
- **SUGGESTED — NOT VERIFIED:** `ZCC010161260021` (id 185) — LINEA 10X20X6 - RED / ศิลาเหลี่ยม 10X20X6 ซม. สีแดง; family —. Evidence: exact dimensions and matching Thai shape description.
- **SUGGESTED — NOT VERIFIED:** `ZCC010161260031` (id 187) — LINEA 10X20X6 - ORANGE / ศิลาเหลี่ยม 10X20X6 ซม. สีส้ม; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010161260061` (id 196) — LINEA 10X20X6 - BLACK / ศิลาเหลี่ยม 10X20X6 ซม. สีดำ; family —. Evidence: exact dimensions; color variant.

### `NKFL01101` — rows 19 and 41 — 20X20X6 — **duplicate MouldCode**
- **SUGGESTED — NOT VERIFIED:** `ZCC010162260011` (id 218) — LINEA 20X20X6 - GREY / ศิลาเหลี่ยม 20X20X6 ซม. สีเทา; family —. Evidence: exact dimensions and matching Thai shape description.
- **SUGGESTED — NOT VERIFIED:** `ZCC010162260021` (id 228) — LINEA 20X20X6 - RED / ศิลาเหลี่ยม 20X20X6 ซม. สีแดง; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010162260031` (id 229) — LINEA 20X20X6 - ORANGE / ศิลาเหลี่ยม 20X20X6 ซม. สีส้ม; family —. Evidence: exact dimensions; color variant.

### `NKFL71403` — row 20 — 20X30X6
- **SUGGESTED — NOT VERIFIED:** `ZCC010162360011` (id 246) — LINEA 20X30X6 - GREY / ศิลาเหลี่ยม 20X30X6 ซม. สีเทา; family —. Evidence: exact dimensions and matching Thai shape description.
- **SUGGESTED — NOT VERIFIED:** `ZCC010162360021` (id 247) — LINEA 20X30X6 - RED / ศิลาเหลี่ยม 20X30X6 ซม. สีแดง; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010162360031` (id 248) — LINEA 20X30X6 - ORANGE / ศิลาเหลี่ยม 20X30X6 ซม. สีส้ม; family —. Evidence: exact dimensions; color variant.

### `NKFL00807` — row 21 — 30X30X6
- **SUGGESTED — NOT VERIFIED:** `ZCC010163360011` (id 267) — LINEA 30X30X6 - GREY / ศิลาเหลี่ยม 30X30X6 ซม. สีเทา; family —. Evidence: exact dimensions and matching Thai shape description.
- **SUGGESTED — NOT VERIFIED:** `ZCC010163360021` (id 271) — LINEA 30X30X6 - RED / ศิลาเหลี่ยม 30X30X6 ซม. สีแดง; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010163360031` (id 274) — LINEA 30X30X6 - ORANGE / ศิลาเหลี่ยม 30X30X6 ซม. สีส้ม; family —. Evidence: exact dimensions; color variant.

### `NKFL01295` — row 22 — 40X40X3.8 No Spacer
- **SUGGESTED — NOT VERIFIED:** `zcc01172438NO11` (id 129) — กระเบื้อง 40X40X3.8 สีเทา หมากรุก  No-Space / กระเบื้อง 40X40X3.8 สีเทา หมากรุก  No-Space; family —. Evidence: exact dimensions and No-Space wording.
- **SUGGESTED — NOT VERIFIED:** `zcc01160438NO11` (id 130) — กบ. 40X40X3.8 ซม.สานเส้นเทา / กบ. 40X40X3.8 ซม.สานเส้นเทา; family —. Evidence: exact dimensions; model/pattern details differ.
- **SUGGESTED — NOT VERIFIED:** `ZCC011604380021A` (id 131) — กบ. 40X40X3.8 ซม.สานเส้นแดง FT / กบ. 40X40X3.8 ซม.สานเส้นแดง FT; family —. Evidence: exact dimensions; pattern/color/formulation details differ.

### `NKFL00435`, `NKFL00436`, `NKFL00437`, `NKFL00438` — rows 23–26 — 40X40X4
- **SUGGESTED — NOT VERIFIED:** `ZCC010224440021` (id 141) — SLAB 40X40X4 CM - RED / แผ่นปูทางเท้า 40X40X4 สีแดง; family —. Evidence: exact dimensions.
- **SUGGESTED — NOT VERIFIED:** `ZCC010224440031` (id 142) — SLAB 40X40X4 CM - ORANGE / แผ่นปูทางเท้า 40X40X4 สีส้ม; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010224440041` (id 143) — SLAB 40X40X4 CM - YELLOW / แผ่นปูทางเท้า 40X40X4 สีเหลือง; family —. Evidence: exact dimensions; color variant.

### `NKFL01088` — row 27 — 40X40X4 No Spacer
- **SUGGESTED — NOT VERIFIED:** `zcc01175444NS11FT` (id 137) — แผ่นปูทางเท้า40X40X4 สีเทาNo Spacer(ลายสานเส้น)FT / แผ่นปูทางเท้า40X40X4 สีเทาNo Spacer(ลายสานเส้น)FT; family —. Evidence: exact dimensions and No Spacer; woven-pattern/formulation qualifier present.
- **SUGGESTED — NOT VERIFIED:** `zcc01175444NS21FT` (id 138) — แผ่นปูทางเท้า40X40X4 สีแดงNo Spacer(ลายสานเส้น)FT / แผ่นปูทางเท้า40X40X4 สีแดงNo Spacer(ลายสานเส้น)FT; family —. Evidence: exact dimensions and No Spacer; woven-pattern/formulation qualifier present.
- **SUGGESTED — NOT VERIFIED:** `ZCC010354440011` (id 136) — SLAB [NO FACING] 40X40X4 CM - GREY / แผ่นปูทางเท้า 40X40X4 สีเทา (ไม่มีผิวหน้า); family —. Evidence: dimensions only; “no facing” is not equivalent to “no spacer”—owner must decide.

### `NKFL01089` — row 28 — 40X40X4 No Spacer / woven-line description
- **SUGGESTED — NOT VERIFIED:** `zcc01175444NS11FT` (id 137) — แผ่นปูทางเท้า40X40X4 สีเทาNo Spacer(ลายสานเส้น)FT / แผ่นปูทางเท้า40X40X4 สีเทาNo Spacer(ลายสานเส้น)FT; family —. Evidence: exact dimensions and No Spacer/woven wording.
- **SUGGESTED — NOT VERIFIED:** `zcc01175444NS21FT` (id 138) — แผ่นปูทางเท้า40X40X4 สีแดงNo Spacer(ลายสานเส้น)FT / แผ่นปูทางเท้า40X40X4 สีแดงNo Spacer(ลายสานเส้น)FT; family —. Evidence: exact dimensions and No Spacer/woven wording; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC011354440041` (id 332) — LALINEAR- Lines 40x40x4 cm. Yellow / ศิลาเหลี่ยม 40X40X4 ซม. สีเหลือง (สานเส้น); family —. Evidence: exact dimensions and woven-line wording; spacer detail differs or is unstated.

### `NKFL73006` — row 29 — 40X40X6
- **SUGGESTED — NOT VERIFIED:** `ZCC010224460011` (id 288) — LA 40X40X6 CM - GREY / ศิลาเหลี่ยม 40X40X6 สีเทา (มีผิวหน้า); family —. Evidence: exact dimensions.
- **SUGGESTED — NOT VERIFIED:** `ZCC010224460021` (id 754) — LA 40X40X6 CM - RED / ศิลาเหลี่ยม 40X40X6 สีแดง ; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010224460031` (id 151) — SLAB 40x40x6 - ORANGE / แผ่นปูทางเท้า 40x40x6 สีส้ม; family —. Evidence: exact dimensions; alternate Product model name.

### `NKFL25001` — rows 30 and 34 — 50X50X6 — **duplicate MouldCode**
- **SUGGESTED — NOT VERIFIED:** `ZCC010165560021` (id 790) — LA 50x50x6 CM.  -แดง / ศิลาเหลี่ยม 50x50x6 ซม. สีแดง; family —. Evidence: exact dimensions.
- **SUGGESTED — NOT VERIFIED:** `ZCC010415560002K` (id 334) — LA 50x50x6 CM.Grey Stone (GGN)พระเมรุมาศ / LA 50x50x6 CM.Grey Stone (GGN); family —. Evidence: exact dimensions; project/design variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC0102A5560021` (id 335) — LA 50x50x6 CM. ลายดาราวดี - RED / ศิลาเหลี่ยม 50x50x6 ซม. ลายดาราวดี - สีแดง; family —. Evidence: exact dimensions; surface-pattern variant.

### `NKFL25003` — row 31 — 40X80X6
**No reasonable Product candidate found.** No live Product name was identified with the required 40X80X6 dimensions or a distinctive matching model name. Owner crosswalk is required; do not substitute a 40X40X6 Product.

### `NKFL25004` — row 32 — 60X60X5
- **SUGGESTED — NOT VERIFIED:** `ZCC010166650011` (id 771) — LA 60*60*5cm GREY / ศิลาเหลี่ยม 60*60*5 CM เทา; family —. Evidence: exact dimensions.
- **SUGGESTED — NOT VERIFIED:** `ZCC010166650065` (id 772) — LA 60*60*5cm R-Black / ศิลาเหลี่ยม 60*60*5 CM ดำเข้ม; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC01041665M061` (id 719) — Laguna 60x60x5 cm. ดำ มัลดีฟ / Laguna 60x60x5 cm. ดำมัลดีฟ; family —. Evidence: exact dimensions; design/color differs.

### `NKFL70410` — row 33 — CUBE 6 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010080060011-1` (id 41) — CUBE 6 CM - GREY / จัตุรัส 6 ซม. สีเทา; family —. Evidence: CUBE / จัตุรัส name terms and nominal 6 cm.
- **SUGGESTED — NOT VERIFIED:** `ZCC010080060021-1` (id 40) — CUBE 6 CM - RED / จัตุรัส 6 ซม. สีแดง; family —. Evidence: matching model and size; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010080060041-1` (id 45) — CUBE 6 CM - YELLOW / จัตุรัส 6 ซม. สีเหลือง; family —. Evidence: matching model and size; color variant.

### `NKFL71702` — row 35 — ARROW 6 CM
- **SUGGESTED — NOT VERIFIED:** `ZCC010110060011` (id 77) — ARROW BLOCK 6 CM - GREY / ศรศิลา 6 ซม. สีเทา; family —. Evidence: ARROW / ศรศิลา terms and nominal 6 cm.
- **SUGGESTED — NOT VERIFIED:** `ZCC010110060021` (id 78) — ARROW BLOCK 6 CM - RED / ศรศิลา 6 ซม. สีแดง; family —. Evidence: matching model and size; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010110060031` (id 79) — ARROW BLOCK 6 CM - ORANGE / ศรศิลา 6 ซม. สีส้ม; family —. Evidence: matching model and size; color variant.

### `NKFL01174` — row 36 — Cobble Stone RT3
- **SUGGESTED — NOT VERIFIED:** `ZCC010460060112` (id 396) — COBBLE STONE RT3-MOSS GREY / COBBLE STONE RT3-MOSS GREY; family —. Evidence: exact RT3 model token.
- **SUGGESTED — NOT VERIFIED:** `ZCC010460060113` (id 397) — COBBLE STONE RT3-LILY PURPLE / COBBLE STONE RT3-LILY PURPLE; family —. Evidence: exact RT3 model token; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010460060115` (id 399) — COBBLE STONE RT3-ROSY PINK / COBBLE STONE RT3-ROSY PINK; family —. Evidence: exact RT3 model token; color variant.

### `NKFL01173` — row 37 — Cobble Stone RT2
- **SUGGESTED — NOT VERIFIED:** `ZCC010450060120` (id 394) — COBBLE STONE RT2-SEA BLUE / COBBLE STONE RT2-SEA BLUE; family —. Evidence: exact RT2 model token.
- **SUGGESTED — NOT VERIFIED:** `ZCC010450060112` (id 386) — COBBLE STONE RT2-MOSS GREY / COBBLE STONE RT2-MOSS GREY; family —. Evidence: exact RT2 model token; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010450060113` (id 387) — COBBLE STONE RT2-LILY PURPLE / COBBLE STONE RT2-LILY PURPLE; family —. Evidence: exact RT2 model token; color variant.

### `NKFL01170` — row 38 — Hexagonal Block 6 CM
**No reasonable Product candidate found.** The 6 cm size and generic “Block” word are insufficient to establish the hexagonal shape; no verified hexagonal Product candidate was found in the live Product names. Owner crosswalk required.

### `NKFL01312` — row 39 — 30X30X3.5
- **SUGGESTED — NOT VERIFIED:** `ZCC010163330059P` (id 254) — LINER 30X30X3.5 BROWN / ศิลาเหลี่ยม 30X30X3.5 ซม. น้ำตาล โปรเจค; family —. Evidence: exact dimensions.
- **SUGGESTED — NOT VERIFIED:** `ZCC010163330071` (id 260) — LINEA 30X30X3.5  BLUE / ศิลาเหลี่ยม 30X30X3.5 ซม. สีฟ้า; family —. Evidence: exact dimensions; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC010163330011` (id 255) — LINEA 30X30X3.5 GREY(FACING 10 CM) / ศิลาเหลี่ยม 30X30X3.5 ซม. สีเทา (ผิวหน้า 10 มม.); family —. Evidence: exact dimensions; facing specification needs owner confirmation.

### `NKFL00430` — row 40 — 30X30X6 No Spacer
- **SUGGESTED — NOT VERIFIED:** `ZCC010163360011P` (id 283) — LINEA 30X30X6 - GREY ( NO SPACER ) / ศิลาเหลี่ยม 30X30X6 ซม. สีเทา ( No Spacer); family —. Evidence: exact dimensions and No Spacer detail.
- **SUGGESTED — NOT VERIFIED:** `ZCC010163360021P` (id 284) — LINEA 30X30X6 - RED  (NO SPACER ) / ศิลาเหลี่ยม 30X30X6 ซม. สีแดง ( No Spacer); family —. Evidence: exact dimensions and No Spacer; color variant.
- **SUGGESTED — NOT VERIFIED:** `ZCC011433360011` (id 285) — LINEA 30X30X6 - GREY (FACING 10 MM. NO.SPACER) / ศิลาเหลี่ยม 30X30X6 ซม. สีเทา (ผิวหน้า 10 มม. No.Spacer); family —. Evidence: exact dimensions; facing specification differs.

### `NKFL01195` — row 42 — Sakura Block 6 CM
**No reasonable Product candidate found.** A generic 6 cm block match is not enough to map the Sakura model to another shape. Owner crosswalk required.

## Owner decision fields — leave blank until approved

| MouldCode | Source Excel row(s) | Owner-confirmed ProductCode | Owner-confirmed Product.id | Confirm physical Mould identity? | Notes / evidence / approver |
|---|---|---|---:|---|---|
| NKFL01101 | 19, 41 |  |  |  |  |
| NKFL25001 | 30, 34 |  |  |  |  |
| NKFL25003 | 31 |  |  |  |  |
| NKFL01170 | 38 |  |  |  |  |
| NKFL01195 | 42 |  |  |  |  |

## Interpretation and unresolved decisions

1. The source has no ProductCode column. Excel model names, physical mould numbers, and Product descriptions are candidate-search evidence only; owner approval must provide an authoritative shape-to-Product crosswalk.
2. There are 37 distinct nonblank MouldCodes across the 39 rows, including two duplicated identifiers. Duplicates are unresolved and conflict with deployed `UQ_Mould_MouldCode` if both rows are separate physical records.
3. Three Moulds have no reasonable candidate based on available names/dimensions: `NKFL25003` (40X80X6), `NKFL01170` (Hexagonal), and `NKFL01195` (Sakura). A generic size/block match must not be used as a substitute.
4. Exact dimensions still do not prove tooling interchangeability. Facing, spacer, woven-line, pattern, and surface variants require physical/owner confirmation.
5. Product color/formulation variants are separate live Product rows with different `Product.id` values (examples include UNI 6 cm colors/formulas and LINEA dimension/color variants). `ProductFamily` is NULL for every live Product record, so it cannot serve as a shape grouping key.

## One-Product-per-Mould model fit

The current `omagmes.Mould.ProductID` foreign key can represent **one** Product row per physical Mould. It can represent use across color variants only when all those variants resolve to the **same `Product.id`**. The live master instead contains color/formulation variants as separate Product records with different IDs. Therefore, under the observed data, a single `ProductID` cannot express one physical Mould serving multiple color-variant Product IDs without either rejecting valid variant relationships or assigning a semantically incorrect Product.

No change is made here. Before import, the owner must decide whether to designate an authoritative canonical shape Product for each Mould or revise the model to separate shape identity from color/formulation Product identity (for example, an approved shape master referenced by both Product and Mould). Do not implement either option without explicit schema/design approval.

## Read-only / not approved for import

This file is an owner-review artifact, not an import source. No official ProductID is assigned. No database write, DDL, permission change, Excel edit, import script, commit, or push was performed.
