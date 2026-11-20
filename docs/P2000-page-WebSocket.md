# p2000.page WebSocket provider (experimental)

This is an **opt-in** P2000 enrichment source in FireServiceRota Extended. Each user obtains their own subscription and key from https://p2000.page/api. There is no bundled/shared account or redistributed feed.

## Home Assistant options

Open FireServiceRota Extended → Configure:

1. Enable P2000 enrichment.
2. Select exactly one online provider: existing AlarmeringDroid or **p2000.page WebSocket**, optionally combined with RTL-SDR MQTT. The legacy online+RTL selection remains supported.
3. When using p2000.page, enter your own key in the masked field and choose region codes (e.g. `06~17`).
4. Leave the key field empty on future edits to keep the existing key. To switch away, select another source.

Existing installations retain the existing online provider; no migration of existing settings is needed.

**Secrets:** Do not paste keys in issues, PRs, chats, screenshots, logs, sensor attributes, or source code. The Home Assistant options UI masks entry, but Home Assistant config-entry options storage is not an encrypted secrets vault. Protect your HA configuration backups and access.

## Protocol and processing

- WebSocket URL: `wss://api.p2000.page/api-/r/06/d/brandweer` with `X-Api-Key` header; provider documentation supports header authentication as an alternative to URL credentials. **Validate this exact header-only URL form with a trial account before release.**
- One WebSocket connection per config entry. The free trial allows one connection.
- Process live `type=melding` events, ignore welcome, pong, and replay `type=laatste` messages. No replay is requested; past alerts are never enqueued as live.
- Deduplicate using provider `uid` within a bounded process-local cache. Incoming events join the same existing P2000 manager and correlation pipeline as other sources.
- Live message arrivals wake the manager immediately; the regular polling cycle remains in place for existing online and RTL-SDR sources.
- Retry transient disconnects with bounded delay. Stop retrying on provider authorization/plan failures (4401/4403 or HTTP 401/403). Back off on excessive connections (4429 or HTTP 429).
- p2000.page may enrich the same UID later; this draft does not yet request `/uid/...` for enrichment. An initial message may therefore lack vehicle metadata. Do not pretend later vehicle additions are present.
- There is no cross-provider canonical P2000 UID. Existing correlation/grouping remains the source of truth for BWR incident enrichment; **test duplicate suppression with real online+RTL data before deployment**.

## Diagnostics and release gates

Existing `sensor.p2000_status` reports per-provider status. New provider diagnostics include transport, connection state, filters, message counts and queue capacity; not credentials or raw messages.

Pending before release:
- [ ] Verify WebSocket HTTP-header-only handshake using the trial key locally.
- [ ] Run Home Assistant config-flow tests, normalization tests and lifecycle/reconnect tests.
- [ ] Confirm all CI/Hassfest checks and rollback/unload.
- [ ] Confirm first real incoming event is processed promptly and does not trigger duplicate TTS/Telegram.
- [ ] Compare timestamps for p2000.page and RTL-SDR under real simultaneous reception.
- [ ] Consider bounded REST UID refresh for updated vehicle data, with rate limit safeguards.
- [ ] Confirm permitted public integration use and requirements for each user's subscription.

No changes to the production `extended` branch, existing release, or `brandweer.yaml` until these gates pass.
