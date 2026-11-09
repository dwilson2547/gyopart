# Cloudflare banned the one VPN exit every parts-direct site was using

**Date:** 2026-10-29 · **Status:** resolved — the proxy rotates its exit (nordvpn-proxy `e02dd66`, live 2026-10-29 21:29 UTC)

## Symptom

From about 13:30 UTC, parts-direct runs on the RevolutionParts sites stopped with exit 65
(`blocked: Browser403Error`). Subaru, Ford and Acura were blocked partway through a run. Ford had
fetched about 550 part pages in 84 min, and image downloads from `cdn-product-images.revolutionparts.io`
had already started returning 403. Every run after that (GM, Honda, Hyundai, Infiniti, Mazda, Mopar,
VW) was refused on the homepage: `blocked at session start: Attention Required! | Cloudflare Sorry,
you have been blocked`. Mitsubishi and Volvo finished normally on the same exit that morning.

## Cause

The proxy never changed its exit. All 25 parts-direct pods in the namespace that day logged the same
exit, `186.247.38.121`. OpenVPN switched servers only when the tunnel died, or when the load-check cron
found server load above 75. That check reads `nordvpn.com/api/server/stats/`, which now returns
403, so it skips every 15 min ("No response from NordVPN API to get server load"). With no `RANDOM_TOP`,
a reconnect also took NordVPN's single top recommendation, so even a restart tended to land on the same
server. The drop seen about every 20 min was OpenVPN refreshing its keys on the same server, not a
rotation. The earlier belief that the exit rotated every 20 min came from that.

So one IP carried every parts-direct site, and the junkyard scrapers, for days. Cloudflare's block
covers the whole RevolutionParts network (all the dealer sites and the image CDN). Probed through the
proxy at 21:21 UTC, every host returned the hard block page, while the home IP got only the usual JS
challenge (`Just a moment...`) that a browser passes.

## Fix

nordvpn-proxy `e02dd66`:

- `ROTATE_CRON` (default `*/20 * * * *`) stops OpenVPN on a schedule. runit reruns it, and it picks
  a new server.
- `RANDOM_TOP` defaults to 20. A reconnect picks at random among the top 20 recommendations and
  skips the server it is leaving.
- Privoxy runs as its own user, and iptables lets that user out only through the tunnel or to the
  local networks.

The scraper side needed nothing new. It already waits out proxy drops (polls for up to 3 min) and
Cloudflare's challenge (up to 45 s). Both happen at each rotation, because the challenge cookie is
tied to the IP.

## Verification

- After the restart (21:29 UTC) the exit was `187.14.224.240`. oemfordpart.com and gmpartsdirect.com
  answered with the JS challenge, not the block, and the image CDN returned 200.
- The blocked jobs were Degraded, not suspended, so they retry on their next scheduled window.

## Open

If Cloudflare blocks NordVPN's ranges wholesale, rotation stops helping. Signs: new exits blocked within
hours, or blocked on first use.
