# RevolutionParts vehicle picker endpoint is GET-only with CSRF token, blocking all tree builds with 403

**Date:** 2026-05-25  
**Component:** `parts-interchange/parts-direct/update-scraper/recent_tree_builder.py` — `_post_form`, `_build_params`; `updater.py` — `_build_recent_tree`  
**Severity:** High — completely blocked vehicle tree building for all parts-direct scrapers, meaning no new vehicle/part data could be scraped

---

## Observed symptom

Running `python3 run.py lexus 3 30` resulted in the scraper successfully fetching the makes list but returning HTTP 403 on every subsequent call to `/ajax/vehicle-picker/next`. After 4 retries the `TreeBuilderError` exception was raised and the run exited immediately with no data scraped:

```
[picker] POST https://www.lexusdirectparts.com/ajax/vehicle-picker/next → 403: 
Retrying post request...
[picker] POST https://www.lexusdirectparts.com/ajax/vehicle-picker/next → 403: 
...
Tree builder error caught, exiting
```

The 403 response body was empty (not a Cloudflare challenge page, which always includes HTML).

---

## Root cause

### Endpoint is GET-only, not POST

The `/ajax/vehicle-picker/next` endpoint on RevolutionParts storefronts only accepts GET requests with parameters in the query string. The scraper was sending POST requests with a multipart/form-data body, then later with a URL-encoded body — both methods are rejected at the server level.

Confirmed by testing inside the browser via Playwright MCP: a POST with CSRF token returned:

```
405 Method Not Allowed
"Method not allowed. Must be one of: GET, GET"
```

A GET with the same parameters as a query string returned 200 with the full model list.

### Missing X-CSRF-TOKEN header causes 403 before method is even checked

The RevolutionParts platform requires an `X-CSRF-TOKEN` header on all picker AJAX calls. The token is a session value embedded in `<meta name="csrf-token">` on every page. Without it the server returns 403 with an empty body before it even evaluates the HTTP method — which is why the earlier debugging attempts (adding `X-Requested-With`, switching to URL-encoded body) had no effect.

The site's `vehicle_drop_downs.js` bundle routes all picker calls through a `fetchWithCsrf()` helper that automatically attaches this header. The scraper was bypassing the widget's JS entirely and calling the endpoint directly without the token.

### Misleading prior failure mode

The endpoint accepting the makes list (`/ajax/vehicle-picker/makes/all`) via GET without CSRF caused the assumption that the `/next` endpoint had the same signature. The two endpoints have different authentication requirements.

---

## Troubleshooting steps taken

1. **Ran scraper, observed 403** — added debug logging to print the response body; confirmed it was empty, ruling out a Cloudflare HTML challenge page.

2. **Added `X-Requested-With: XMLHttpRequest` and switched from FormData to URL-encoded body** — still 403 empty body; ruled out content-type and XHR header as the issue.

3. **Loaded the site using Playwright MCP directly** — confirmed the page loads successfully, ruling out IP blocks.

4. **Inspected DOM and loaded JS** — found the site is a RevolutionParts storefront (`cdn-resources.revolutionparts.io`); found `<meta name="csrf-token">` with a session token value; identified `vehicle_drop_downs.js` and its `fetchWithCsrf()` pattern.

5. **Tested POST with CSRF token from within the browser** — received 405 "Method Not Allowed: Must be one of: GET, GET", confirming the endpoint is GET-only and that CSRF was the gating check.

6. **Tested GET with CSRF token and params as query string** — received 200 with the full model list, confirming the correct call signature.

---

## Fix

### `recent_tree_builder.py` — replaced `_post_form` with `_fetch_options` using GET

Renamed `_post_form` to `_fetch_options` and rewrote it to send a GET request with params serialised into the query string via `URLSearchParams` (browser path) or `urlencode` (session path). Added `X-CSRF-TOKEN` header to both paths. Added `csrf_token` parameter to `__init__`.

Before:
```python
result = page.evaluate(
    """async ([url, fields]) => {
        const params = new URLSearchParams();
        for (const [k, v] of Object.entries(fields)) params.append(k, v);
        const r = await fetch(url, {
            method: 'POST',
            body: params,
            credentials: 'include',
            headers: {'X-Requested-With': 'XMLHttpRequest'},
        });
        return {status: r.status, body: await r.text()};
    }""",
    [self.PICKER_AJAX_URL, form],
)
```

After:
```python
result = page.evaluate(
    """async ([url, params, csrf]) => {
        const qs = new URLSearchParams(params);
        const headers = {'X-Requested-With': 'XMLHttpRequest'};
        if (csrf) headers['X-CSRF-TOKEN'] = csrf;
        const r = await fetch(`${url}?${qs}`, {
            method: 'GET',
            credentials: 'include',
            headers,
        });
        return {status: r.status, body: await r.text()};
    }""",
    [self.PICKER_AJAX_URL, params, self.csrf_token],
)
```

### `updater.py` — extract CSRF token after homepage load and pass to tree builder

After the Playwright page loads the site homepage (which already passes Cloudflare challenge), extract the CSRF token from the page meta tag and pass it to `RecentTreeBuilder`.

```python
csrf_token = page.evaluate(
    "() => document.querySelector('meta[name=\"csrf-token\"]')?.content || null"
)
return RecentTreeBuilder(
    self.BASE_URL,
    years_to_refresh=self.years_to_refresh,
    request_auth=self.request_auth,
    current_year=self.current_year,
    csrf_token=csrf_token,
).scrape_car_list(page=page)
```

---

## Files changed

- `parts-interchange/parts-direct/update-scraper/recent_tree_builder.py` — `__init__`, `_post_form` → `_fetch_options`, `_build_form` → `_build_params`
- `parts-interchange/parts-direct/update-scraper/updater.py` — `_build_recent_tree`
