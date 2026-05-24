# AppSheet Apps with Google Sheets Backend

**Applies to:** usedautopartsfl.com (confirmed)

---

## Identification

- Inventory iframe src: `https://www.appsheet.com/start/{appId}`
- App loads client-side with IndexedDB caching under `{appId}||0|` database
- Background color/logo loaded from `fsimage.png?datasource=google` — the `datasource=google` param confirms Google Sheets backend

## How to Find the Google Sheets DocId Fast

1. Load the iframe URL in a browser
2. Check `localStorage` key `launch_background_{appId}` — it contains a URL with `filename=DocId%3D{spreadsheetId}` embedded
3. OR: POST to `https://www.appsheet.com/api/template/{appId}/` (no auth) — response includes full app config
4. In the config, `Template.AppData.DataSets[*].Source` = `"DocId={spreadsheetId}"` for each table

## Google Sheets CSV Export

Once you have the DocId, access any sheet directly:
```
GET https://docs.google.com/spreadsheets/d/{docId}/gviz/tq?tqx=out:csv&sheet={sheetName}
```

No auth required if the spreadsheet is publicly accessible (AppSheet apps are often backed by sheets shared as "Anyone with the link can view").

The `SourceQualifier` field in the AppSheet DataSet config is the exact sheet name to use in the URL parameter.

## AppSheet Template API

```
POST https://www.appsheet.com/api/template/{appId}/
Content-Type: application/json

{"AppName":"{appName}","AppVersion":"...","SyncToken":"","DataSetRequests":[...]}
```

- No API key required for public/guest-accessible apps
- `appName` found in the URL hash `#appName={appName}&...` after the app loads
- Returns full app definition including all table schemas, data source configs, and a Firebase custom token for real-time updates
- `NestedDataSets[*].DataSet` will be null if data is being served from Google Sheets cache (use the direct CSV export instead)

## AppSheet v2 REST API

```
POST https://www.appsheet.com/api/v2/apps/{appId}/tables/{tableName}/Action
```

Requires `ApplicationAccessKey` in the header — only available to the app owner.
**Cannot be used server-side without the owner's API key.**

## Notes

- The Google Sheets export is simpler, more reliable, and requires no session/token
- AppSheet's Firebase real-time sync (`signaler-pa.googleapis.com`) is not needed for scraping
- Images are served via `https://www.appsheet.com/fsimage.png?appid={appId}&datasource=google&filename={path}&tableprovider=google&userid={ownerId}` — the `userid` is the AppSheet owner ID embedded in the template API response (`OwnerId` field)
- The IndexedDB store uses `localForage` with a key-value format; data shards are stored as `{TABLE}~#N` but are `{data:{}, cmp:"ZL"}` (empty/placeholder) until a full sync completes
