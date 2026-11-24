# OMAG MES — Linked Server Error 7416 Resolution

**Date:** 2026-11-24  
**Status:** Fix verified for direct OPENQUERY using OMAG_MES; application view verification pending.

## 1. Environment

| Item | Value |
|---|---|
| Local SQL Server | 10.28.255.98 |
| Local database | OMAG |
| Application login | OMAG_MES |
| Administrator login | sa |
| Linked Server | 172.18.8.139 |
| Provider (as displayed in sys.servers) | SQLNCLI |
| Remote database | PIS |
| Remote login | crtc |
| Remote source | PIS.dbo.vw_ActivePlan |
| Local synonym | dbo.OmagPlan |
| Application view | dbo.vw_OmagPlan |

## 2. Problem

The administrator `sa` could read the remote plan data, but `OMAG_MES` received:

```text
Msg 7416, Level 16, State 2
Access to the remote server is denied because no login-mapping exists.
```

The error persisted for the local view, direct four-part queries, OPENQUERY and sp_testlinkedserver, even after granting SELECT and recreating the explicit remote login mapping. A new login session also failed before the provider-string change.

## 3. Existing login mapping

Run as `sa`:

```sql
EXEC master.dbo.sp_helplinkedsrvlogin
    @rmtsrvname = N'172.18.8.139';
```

Observed mappings before the successful fix:

| Local Login | Is Self Mapping | Remote Login |
|---|---:|---|
| NULL (default mapping) | 0 | crtc |
| sa | 0 | crtc |
| OMAG_MES | 0 | crtc |

The explicit mapping was already present. Recreating it alone did not resolve Error 7416. Do not repeatedly recreate working mappings or grant sysadmin to the application login.

## 4. Successful fix — add User ID to Provider String

Original provider string:

```ini
Encrypt=Yes;TrustServerCertificate=yes
```

Run the following on the local SQL Server **as sa**, not as OMAG_MES:

```sql
USE master;
GO
EXEC master.dbo.sp_serveroption
    @server   = N'172.18.8.139',
    @optname  = N'provider string',
    @optvalue = N'Encrypt=Yes;TrustServerCertificate=yes;User ID=crtc';
GO
```

Verify:

```sql
SELECT name, provider, data_source, provider_string
FROM sys.servers
WHERE name = N'172.18.8.139';
```

Expected provider string (case may be normalized):

```ini
Encrypt=Yes;TrustServerCertificate=yes;User ID=crtc
```

This is the change that was followed by a successful query. The precise internal cause of the provider behavior was not independently established. No Linked Server recreation was needed for this final fix.

## 5. Verified result

Connect to `10.28.255.98` using the actual SQL login `OMAG_MES` and execute:

```sql
SELECT *
FROM OPENQUERY([172.18.8.139],
    'SELECT TOP 10 * FROM PIS.dbo.vw_ActivePlan'
);
```

**PASS:** Screenshot after the provider-string change shows ten returned rows under OMAG_MES, session 267 (the same session that previously failed). The unfiltered remote query returned historical rows from other plants; this verifies connectivity, not OMAG plan freshness.

## 6. Local view and application verification

The synonym was previously redirected from PIS_TEST_LINK to the real existing Linked Server:

```sql
-- Intended existing synonym target; inspect before making any changes.
SELECT name, base_object_name
FROM OMAG.sys.synonyms
WHERE name = N'OmagPlan';
```

Expected target: `[172.18.8.139].[PIS].[dbo].[vw_ActivePlan]`.

The local SELECT permissions were already granted successfully:

```sql
USE OMAG;
GO
GRANT SELECT ON OBJECT::dbo.vw_OmagPlan TO [OMAG_MES];
GRANT SELECT ON OBJECT::dbo.OmagPlan TO [OMAG_MES];
GO
```

Next, test with both `OMAG_MES` and `sa`:

```sql
SELECT TOP (100) *
FROM OMAG.dbo.vw_OmagPlan
ORDER BY StartTime DESC, VersionNo DESC;
```

Expected: OMAG production plan rows, with the existing view's filters retained. Then verify the OmagMES Production Plan dropdown and refresh workflow. These post-fix checks are not yet confirmed by the supplied screenshots.

## 7. Rollback

If the shared Linked Server has regressions, restore its previous provider string as `sa`:

```sql
EXEC master.dbo.sp_serveroption
    @server   = N'172.18.8.139',
    @optname  = N'provider string',
    @optvalue = N'Encrypt=Yes;TrustServerCertificate=yes';
```

This may restore the original Error 7416 for OMAG_MES. Coordinate changes because the Linked Server is shared.

## 8. Operational notes

- Keep PIS access read-only for OmagMES; do not change remote production data.
- Do not store remote passwords in Markdown, Git, or provider strings. Use authorized credentials in the login mapping. Rotate exposed credentials in coordination with the database administrator.
- The existing default mapping applies to other local logins; review its necessity separately without disrupting existing consumers.
- TrustServerCertificate=yes bypasses certificate validation; it was an existing setting, not the newly identified fix. Review certificate trust separately.
- SQLNCLI is a legacy provider label. Provider modernization is a separate change requiring compatibility testing.
- For future Error 7416 incidents where mappings exist, inspect the provider string and compare with this verified configuration before rebuilding the Linked Server.

Suggested repository location: `D:\AI\OmagMES\docs\OMAG_MES_LinkedServer_Error7416_Fix.md`.
