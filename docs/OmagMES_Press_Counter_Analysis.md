# OmagMES Press Stroke Counter — Read-Only Analysis

**Prepared:** 2026-11-03  
**Scope:** Read-only examination of `OMAG.dbo.PRESS` for `OPC.OMAG.OMAG.PRESS.ProductCnt`. No database, source code, or existing design document was modified.  
**Status:** Findings below describe a point-in-time bounded sample, not a complete historical validation or authorization to implement.

## Design-revision note (2026-11-04)

The current OmagMES requirement is one shared accumulator for the approved ProductCnt feed, expected at approximately five-minute intervals, with a daily reset boundary at 07:00 Asia/Bangkok. That boundary does not alter the historic sample results below: the bounded legacy `PRESS` sample contains denser rows in some periods (roughly 25–48 seconds on the three selected days), long gaps, and decreases at varying times. It has not been proven to be the approved feed. Verify source/time alignment before implementation. Do not sum across the known daily boundary; if its reset observation is missing, preserve uncertainty. Also detect decreases/restarts outside 07:00, establish a baseline, and never apply a negative delta. Do not fabricate missing strokes. Mould Age remains separate from PLC counter resets and resets only on approved Return from Recondition.

## 1. Access, verified database skill, and limits

The OmagMES project path `D:\AI\OmagMES` and its `.env` were verified. Before SQL inspection, the applicable skill was located and read:

- [skill/DATABASE_ID_FIRST_DESIGN_SKILL.md](../skill/DATABASE_ID_FIRST_DESIGN_SKILL.md) — verified absolute path `D:\AI\OmagMES\skill\DATABASE_ID_FIRST_DESIGN_SKILL.md`.

It requires new tables to use opaque `id bigint IDENTITY(1,1)` PKs, `Rectime datetime NOT NULL DEFAULT (GETDATE())`, and ID-based FKs to authoritative records. This was an investigation only; no new object or schema design artifact was executed.

No OmagMES application database module/source file was present in the inspected project tree, so no in-project connection loader could be verified. The existing approved OmagMES `.env` settings were loaded locally through the installed dotenv parser, without displaying any setting values or credentials. The connection used the configured SQL Server driver/settings and `ApplicationIntent=ReadOnly`; SQL reported database `OMAG`. Connection intent does not prove that the configured login is technically denied writes; its write permissions were not probed, and no write was attempted.

Every query was a SELECT against system catalogs or bounded `PRESS` ID ranges. No DDL/DML, stored procedure, or user-defined function was executed. `PRESS` was not changed. Because `PRESS` has no index on `_NAME` or `_TIMESTAMP`, investigations used bounded ranges on the clustered identity `id` and narrow timestamp windows where possible; no unbounded full-table query was intentionally issued.

## 2. Actual table schema and access paths

`OMAG.dbo.PRESS` is a user table. Catalog metadata reported:

| Column | SQL type | Nullability | Observed/catalog detail |
|---|---|---|---|
| `id` | `int` | NOT NULL | Identity; sole clustered primary key; unique row identity in this table. |
| `_NAME` | `varchar(64)` | NULL | Tag name. |
| `_NUMERICID` | `int` | NULL | Present; not used as a row key in this investigation. |
| `_VALUE` | `varchar(64)` | NULL | Counter values are text and require validated numeric conversion. |
| `_TIMESTAMP` | `datetime` | NULL | Timezone-naive SQL Server `datetime`, approximately 3.33 ms representational precision; it contains no offset/timezone metadata. |
| `_QUALITY` | `int` | NULL | Numeric OPC quality field. |

Only one index was found: clustered PK on `id`. There is no cataloged index on `_NAME`, `_TIMESTAMP`, or the tag/value pair. Queries filtering on the tag name or timestamp alone therefore lack a supporting index and may scan. `id` provides a stable identity within this legacy table and a bounded clustered-key access path; insertion order should not be confused with event-time order. Analysis ordered samples by `_TIMESTAMP, id` to break timestamp ties deterministically.

The representative tag query returned latest rows with table IDs 301860, 301856, 301852, etc. For this tag, `_VALUE` values in the inspected range were integer text, but that does not make the column a numeric type or guarantee every future row is parseable.

## 3. Sample plan and coverage

The live query connected to `OMAG` and reviewed only `OPC.OMAG.OMAG.PRESS.ProductCnt`. Data inspection used clustered identity ranges, including `id BETWEEN 250000 AND 301860` and narrower ranges around representative dates. This bounded range contained 12,740 rows for the tag. Three consecutive dense counter-data calendar days—2026-10-28, 2026-10-29, and 2026-10-30—were examined closely. A table containing only this tag cannot independently certify that a date was a production day or distinguish production from idle/operator activity; these dates are described as dense counter-sample days.

### Per-day sample statistics

The statistics below order samples within each timestamp date. Intervals are between adjacent rows within that date; gaps can span idle time, missing collection, or other unobserved conditions.

| Date | Rows | First / last sample | Avg adjacent interval | Min / max adjacent interval | Quality 192 | Unchanged values | Negative within-day deltas |
|---|---:|---|---:|---:|---:|---:|---:|
| 2026-10-28 | 2,147 | 00:00:29.927 / 23:59:32.267 | 40.2 s | 9 s / 3 h 03 m 22 s | 2,147 | 0 | 2 |
| 2026-10-29 | 1,801 | 00:00:23.263 / 23:52:44.077 | 47.7 s | 2 s / 3 h 38 m 47 s | 1,801 | 0 | 5 |
| 2026-10-30 | 2,365 | 00:07:13.950 / 23:32:10.073 | 35.7 s | 3 s / 23 m 24 s | 2,365 | 0 | 2 |

Across the broader bounded range `id 250000..301860`, all 12,740 tag rows had `_QUALITY=192`; there were no NULL `_VALUE`, non-integer `_VALUE`, NULL `_TIMESTAMP`, or duplicate timestamp groups in that range. The three-day table likewise showed no duplicate timestamps or unchanged adjacent counter values. OPC quality integer 192 is conventionally the OPC DA “Good” quality code; the database does not document the encoding, so confirm the PLC/OPC gateway's quality convention before making that a hard validation rule.

These are sample-range results only, not a guarantee of table-wide behavior. Values are ordered by event timestamp, and `id` breaks ties; timestamp duplicates were not found in the bounded set.

## 4. Observed behavior around 07:00 (historical sample only)

The current owner-confirmed ProductCnt feed has a 07:00 Asia/Bangkok daily boundary. The inspected legacy `PRESS` sample is not proven to be that feed and does **not** show a reset at 07:00 on the three consecutive sampled days. Each date has good-quality samples immediately before and after 07:00 with continuous increasing values. This mismatch is a source-alignment warning, not a reason to discard the confirmed ProductCnt contract:

| Date | Last shown before 07:00 | First shown after 07:00 | Observed change |
|---|---|---|---:|
| 2026-10-28 | 06:59:45.873, value 1019 | 07:00:12.873, value 1020 | +1 |
| 2026-10-29 | 06:59:44.020, value 1191 | 07:00:13.017, value 1192 | +1 |
| 2026-10-30 | 06:59:45.997, value 1193 | 07:00:13.997, value 1194 | +1 |

A further bounded 07:00 window on 2026-10-27 showed 06:59:54.703 value 1288 followed by 07:00:19.717 value 1289. Thus, for the sampled records and the timestamps as stored, the observed counter continues through 07:00 rather than restarting there. The timestamp is timezone-naive, so these rows cannot establish whether the recorded clock is Bangkok local time, UTC, or another source time. This historical evidence does not establish a reset schedule; source time semantics still need confirmation.

Near midnight, the first available rows on 2026-10-28 and 2026-10-29 were values 344 and 472, respectively, and increased from there. This is not evidence of a reset at midnight either; the preceding-day boundary rows were not included in that narrow midnight sample.

## 5. Counter drops, periodicity, idle periods and data gaps

### Negative deltas / resets

Although the counter usually increased, the bounded dense-day set contained valid-quality, same-day downward jumps. Examples from the observed rows:

- 2026-10-28: value 1130 at 07:58:04.830 followed 12 seconds later by value 0 at 07:58:16.827.
- 2026-10-29: value 1249 at 07:31:08.090 followed 103.997 seconds later by value 0 at 07:32:51.087.
- 2026-10-30: value 1309 at 08:01:12.010 followed 5 seconds later by value 0 at 08:01:17.020.

All these rows had `_QUALITY=192`. They are observed counter decreases/reset-to-zero events, but the tag table cannot identify their cause. They do not coincide with 07:00 in the stored timestamps. Possible causes (PLC reset/restart, tag reinitialization, timestamp semantics, source correction, or another process) are hypotheses only; no cause was verified. Do not silently interpret these as daily boundary resets or as counter rollover without PLC/OPC configuration evidence.

The daily within-day negative-jump counts were 2, 5, and 2 for Oct 28, 29, and 30 respectively. Adjacent equal readings numbered zero on those dates. Other negative jumps in the broader bounded range were also observed, for example values 842 to 0 on 2026-10-31 at 08:09, after the last shown prior-day sample at 23:32. That gap is about 8 h 37 min, so the exact time and cause of the reset are unknown.

### Sampling frequency and event-vs-periodic recording

During dense periods, samples often arrive roughly every 25–30 seconds and the count often advances by one; other intervals are shorter/longer, and some values jump by more than one across a wider interval. Across the three sample days, mean intervals are about 36–48 seconds, with maximum same-day gaps of 3 h 03 min to 3 h 39 min. The wider range also included sparse days with a single tag sample.

This supports the conclusion that the table contains sampled/history records, not a per-stroke transaction ledger. The rows alone cannot establish whether the collector inserts strictly on every value change, polls periodically and suppresses unchanged values, or combines those behaviors. No unchanged adjacent values were seen in the bounded dense-day range, but gaps and multi-count deltas show that one row cannot be assumed to correspond to exactly one physical stroke. The source does not contain an explicit poll sequence, collection interval, device event flag, or insertion timestamp separate from `_TIMESTAMP`.

### Idle versus missing data

A constant value is not itself proof of idle, because no unchanged rows were observed and the historian may suppress them. A multi-hour gap is not proof of idle either: it may represent no production, collection outage, historian retention/filtering, or source unavailability. The schema contains no machine-run state or collector-health field. Counter behavior during idle cannot be confidently separated from data loss using these columns alone.

## 6. Mould-change boundary accuracy

`PRESS` has no Mould ID, Product ID, Color, Lot ID, run/assignment ID, or explicit Mould-change event. The counter continues independently of Lot/Mould assignment per the confirmed business rule. The sampled counter values therefore cannot identify which Mould accumulated strokes during any interval.

Even if a future operator workflow records Mould-change timestamps, if a change falls between two counter samples the delta across that interval cannot be divided exactly between the old and new Mould. The observed sampling intervals (normally tens of seconds, occasionally hours) and the absence of a boundary sample mean exact retrospective allocation is not generally supportable from this table alone. A color change or new Lot must not be used as a proxy for a Mould change: coating Color does not reset Mould Age, and the Mould is associated with Product shape, not Color.

## 7. Recommended safe and auditable Current Age / Lifetime Age calculation

The following is a proposed calculation contract; it does not change or write `OMAG.dbo.PRESS`.

1. **Keep the legacy source immutable.** Read samples using the source row `id`, exact `_NAME`, raw `_VALUE`, `_TIMESTAMP`, and `_QUALITY`. Preserve the source identity and raw source fields in any future Omag-owned audit/ledger process; do not write back to the legacy table.
2. **Resolve time semantics first.** Confirm the PLC/gateway clock basis and distinguish DataLogger observations from the legacy `PRESS` rows. Convert timezone-naive source timestamps only after the clock basis is established. Do not assume or synthesize a reset at 07:00; identify resets from observed counter decreases or independently verified reset events.
3. **Parse and validate samples.** Accept only numeric, non-NULL values and an owner-approved good-quality set. Order by `_TIMESTAMP, id`, detect duplicates/out-of-order arrival, and retain rejected/anomalous samples for review. Do not sum `_VALUE` readings; they are cumulative-counter snapshots.
4. **Create counter epochs and deltas.** For ordered, valid observations, a supported monotonic pair contributes `current_value - previous_value`. When a decrease/reset/restart is observed, record the discontinuity and establish the new reading as a baseline; never subtract across it or treat the post-reset value as a known increment unless a zero baseline is verified. Deduplicate each ordered source-sample pair so retries/reprocessing cannot add a delta twice. Counter epochs do **not** reset Mould age. Do not invent a full counter wrap.
5. **Treat decreases and ambiguity explicitly.** Never add a negative delta. An observed decrease starts a new baseline and flags the preceding-to-current interval as uncertain unless reset timing/semantics establish the missing portion. Do not automatically add the post-drop value as a complete interval increment when pre-reset activity may be missing.
6. **Treat gaps as unknown, not zero or extrapolated.** Define a maximum trusted interval from an owner-approved sampling/operational specification. When a gap exceeds it, mark affected strokes/interval attribution as incomplete. Do not interpolate linearly by elapsed time, output quantity, assumed speed, or Mould lifetime statistics. A first post-reset sample may be counted from zero only if the reset time and zero baseline are independently verified and the sample is known to be the first reliable post-reset reading; otherwise account for the unobserved prefix as unknown.
7. **Attribute only across known Mould intervals.** Store controlled Mould-use intervals with exact MouldID, ProductID, ProductionRun/Lot references, start/end timestamps, actor/source, and boundary counter sample references. At Mould change, capture a reliable counter boundary reading and atomically close/open intervals. If unavailable, keep the spanning delta unallocated or explicitly uncertain for review; never split it by percentage or guess.
8. **Separate Mould-life epochs from PLC counter epochs.** Current Age is the sum of confirmed stroke-allocation ledger entries for that Mould since its most recent **approved Return from Recondition**. Lifetime Age is the sum of its confirmed allocations across every recondition cycle. Daily PLC resets only segment the counter-delta calculation; they do not reset Current Age or Lifetime Age. Color changes and new Lots do not reset either age.
9. **Make correction and aggregation auditable.** Use unique source sample/segment keys to make ingestion and pair allocation idempotent. Keep raw source observations immutable. Correct allocations with append-only reversal/adjustment records referencing the original ledger entry, including actor, time, reason, evidence and approval. Derive totals from the non-reversed ledger, or maintain a rebuildable projection with reconciliation—not both as independently additive totals.
10. **Protect concurrent transitions.** Serialize Mould assignment, interval close/open, recondition send/approved return, and allocation changes in a transaction. Server-side validation must re-read current Mould status/capability and ensure one open interval where policy requires. Preserve all events when changing Product/Color/Lot; a Color change creates the required Lot boundary but does not reset Mould Age.

Conceptually, for confirmed allocations $a$ attributed to Mould $m$:

$$
\text{LifetimeAge}(m)=\sum_{a\in\text{all confirmed allocations for }m} a.\text{Strokes}
$$

$$
\text{CurrentAge}(m)=\sum_{a\in\text{confirmed allocations for }m\text{ after the latest approved return}} a.\text{Strokes}
$$

Unknown or disputed stroke portions must be reported as unresolved separately, not silently included as zero or a guessed count.

## 8. OmagMES relationship to the confirmed design

- One physical line and one main Press remain the only line/Press identities for the initial system.
- Each Mould is assigned to exactly one Product shape. Multiple Moulds may be associated with the same Product. Color is independent and is not part of Mould assignment or eligibility; do not create a Mould/Product capability junction or Mould-to-Color settings.
- Production save validates the registered Mould, eligible status, and exact equality between the Mould's Product and the Lot's Product.
- Product or coating Color changes create a new Production Lot under the confirmed rules. A pause without either change retains its Lot. Mould changes alone do not manufacture a new Lot; they create a new Mould-use interval.
- Current Age resets only when an approved Return from Recondition is recorded. Lifetime Age remains cumulative. Any observed PLC counter reset is only an accumulator baseline boundary, never a Mould-life reset.

These rules are owner-confirmed inputs; the sampled database rows do not independently prove their operational implementation.

## 9. Unresolved questions and risks before implementation

1. Why do the sampled values continue through 07:00 and then drop to zero at varying times around 07:32–08:01? Confirm reset/restart semantics and whether the stored timestamp is local or UTC; do not assume a fixed 07:00 reset.
2. Does `_TIMESTAMP` denote source event time, OPC acquisition time, historian write time, or another clock? Is there a separate clock-synchronization/offset specification?
3. What is the writer policy—on-change, periodic polling, deadband, or hybrid—and what is its configured period/deadband? The table schema and sample sequence cannot answer this conclusively.
4. What do quality values mean for this OPC server, and are bad/uncertain rows retained, filtered, or omitted? The bounded range showed only 192, not a full historical quality audit.
5. How should unexplained counter restarts, forced resets, PLC restarts, and counter rollover be distinguished and authorized? The sampled valid-quality negative deltas mean `QUALITY=192` alone does not establish semantic continuity.
6. What is the maximum acceptable data gap, and who resolves unknown stroke attribution? Dense-day gaps reach multiple hours; there is no collector heartbeat or machine-state field in `PRESS`.
7. Can a boundary sample be captured reliably at each Mould installation/removal and recondition return? If not, exact Mould-specific stroke counts are impossible for intervals crossing sample gaps/change boundaries; decide whether the business requires estimates or allows an explicit unknown/unallocated quantity. Estimation must never be disguised as an exact count.
8. Determine whether `id` is retained permanently and can be used as a stable source key under PLC/historian retention/reload practices. It is the current table PK, but lifecycle/retention guarantees were not inspected.
9. Decide how corrected or deleted legacy samples would be detected and reconciled; there is no separate source-row version/tombstone field in the inspected schema.
10. Agree counter precision/range, overflow behavior, units (strokes), qualifying machine states/setup/test strokes, and expected relationship to physical mould wear. Do not convert strokes to finished pieces.
11. Confirm authorization for Omag-owned derived audit/ledger storage in a separate implementation task. No table, index, migration, or code was created here.

## Conclusion

The actual table has a clustered identity key but no tag/time index, stores counter values as nullable text and timestamps without timezone, and contains only numeric quality values with no source semantics in the table definition. Bounded samples show dense roughly 25–30 second observations during active periods, multi-hour gaps, no duplicate timestamps in the inspected range, and valid-quality counter decreases. Samples on Oct 27–30 continue increasing through 07:00 as stored, while zero resets were seen at variable later times. These are historical sample findings only and do not establish the behavior or cadence of the Kepware DataLogger feed required by the current design.

The current legacy history can support qualified counter-delta estimates only where the epoch, data continuity, and Mould interval boundaries are verified. It cannot itself accurately allocate strokes to Moulds at unobserved changes. OmagMES should retain source evidence, segment resets without resetting Mould life, deduplicate every allocated sample-pair delta, and leave missing or ambiguous stroke quantities visibly unresolved. The legacy table must remain read-only and unchanged.
