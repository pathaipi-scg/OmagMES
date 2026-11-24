# Press Diff Quality and Timestamp Handling

**Status: factory-owner decision recorded 2026-11-17.** `_QUALITY` is not used to determine whether PRESS DropCnt is counted. It remains informational only. This decision does not set a timestamp conversion or enable candidate/official write gates.

## `_QUALITY` handling

The factory owner confirms that no quality value blocks Diff. The SQL Diff view preserves the current row's `_QUALITY` as `QualityCode` for information, but does not join `PressDiffQualityPolicy`, reject codes, or alter Diff/ACC based on quality.

The `PressDiffQualityPolicy` table, if already present from Migration 004, is retained untouched for compatibility/history and is dormant: it has no effect on the five views. Do not insert policy rows as part of this fix and do not drop the table. Quality 192 has no special treatment; any value is treated identically for Diff purposes.

Diff remains based on ordered source `_TIMESTAMP`, numeric `_VALUE`, and `id`: positive increase yields current minus previous; unchanged or counter decrease yields zero; decreases set `ResetDetected=1`. Missing predecessors and invalid current/previous counter values remain explicitly classified and do not yield a Diff. `_QUALITY` does not fix invalid counter values or create a missing predecessor.

## Timestamp interpretation

LIVE `dbo.PRESS._TIMESTAMP` is SQL Server `datetime`, with no timezone or UTC-offset metadata. Workspace review found Kepware Data Logger documentation, but no Kepware configuration export or SQL writer implementation proving whether persisted timestamps are factory-local, UTC, or transformed. Reader-side timezone settings are not evidence of writer behavior. The local application configuration has `Asia/Bangkok` but keeps source-timezone confirmation false.

Preserve and compare existing source values as stored; do not shift, relabel as UTC, or automatically convert them. Counter Diff ordering uses these raw timestamps and `id` as the tie-breaker. Production Date assignment and operator Lot-window comparisons still use the stored wall-clock value and should be interpreted with this limitation recorded; do not fabricate timezone semantics.

## Evidence required for approval

1. Kepware project export or Data Logger configuration for the `PRESS` table and DropCnt channel/tag, to understand source provenance (not to gate Diff by quality).
2. Confirmation of `_TIMESTAMP` provenance: PLC/source timestamp vs logger/server insertion time, clock timezone, and any gateway offset/conversion.
3. A bounded comparison of source event times to a trusted local factory clock and known events before enabling candidate window writes.
