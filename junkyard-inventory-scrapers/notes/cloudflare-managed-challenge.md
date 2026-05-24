# Cloudflare Managed Challenge

**Applies to:** pyp.com (confirmed), likely any site using Cloudflare Bot Management

## Identification

- HTTP 403 with `cf-mitigated: challenge` response header
- Body is a "Just a moment..." JS challenge page (`/cdn-cgi/challenge-platform/...`)
- Blocks all `curl`/`requests`/non-browser clients regardless of User-Agent spoofing
- Affects **both HTML pages and AJAX/API endpoints** at pyp.com

## Strategy

**Must use Playwright (real browser).** No server-side bypass approach is viable.

- Navigate to the main site first with Playwright to clear the CF challenge
- Then call the API endpoints via `page.evaluate(() => fetch(...))` — inherits the browser's CF clearance cookie
- No need to extract or manage the CF cookie manually — Playwright's browser context handles it

## Key Note

Cloudflare managed challenge is distinct from the simpler `cf-turnstile` widget — it cannot be bypassed with header tricks. The only reliable approach is a real browser session.
