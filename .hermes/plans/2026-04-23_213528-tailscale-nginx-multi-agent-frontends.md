# Plan: Tailscale -> Nginx baseline for multiple local agents and frontends

## Goal

Run multiple local agent gateways and custom browser frontends on one host, with browser-recognized TLS for voice/microphone support, while avoiding breakage to the existing OpenClaw setup.

The desired steady state is:

- Tailscale owns public/tailnet DNS and browser-recognized HTTPS.
- Tailscale forwards HTTPS to a single local Nginx listener.
- Nginx owns all routing, prefixes, WebSocket upgrades, upload limits, and proxy headers.
- OpenClaw, Hermes, Agent, and future services remain bound to loopback ports.
- Each service has one stable path prefix or subdomain-equivalent path.
- OpenClaw no longer tries to manage Tailscale Serve/Funnel itself.

## Current context observed

### Host state

- `tailscaled` is active.
- `nginx` is installed but inactive.
- Nginx already has `/etc/nginx/conf.d/agent.conf` copied from `$HOME/Agent/.deploy/nginx-agent.conf`.
- Current listener observations include:
  - Tailscale/IP-bound HTTPS on `100.123.222.98:443` and tailnet IPv6 `:443`.
  - OpenClaw gateway on `127.0.0.1:18789` and `[::1]:18789`.
  - OpenClaw also listens on `127.0.0.1:18791`.
  - Agent web config expects `127.0.0.1:18080`.
  - Private publish server on `127.0.0.1:8123`.
  - Timezones app on `127.0.0.1:8125`.
  - Hermes gateway process is running; its Telegram platform is connected.

### OpenClaw config

`/home/brunomanti/.openclaw/openclaw.json` currently has:

```json5
{
  "gateway": {
    "mode": "local",
    "auth": { "mode": "token", "token": "..." },
    "port": 18789,
    "bind": "loopback",
    "tailscale": {
      "mode": "serve",
      "resetOnExit": false
    },
    "controlUi": {
      "allowInsecureAuth": true,
      "allowedOrigins": ["https://bvm-ws.axolotl-saurolophus.ts.net"]
    }
  }
}
```

OpenClaw docs say:

- Integrated Tailscale Serve is a supported mode.
- `gateway.controlUi.basePath` can prefix the Control UI, e.g. `/openclaw`.
- For reverse-proxy/non-loopback deployments, `gateway.controlUi.allowedOrigins` should be explicit.
- `gateway.tailscale.mode: "off"` disables OpenClaw's Tailscale automation.
- Tailscale Serve identity headers only apply when OpenClaw itself is behind Tailscale Serve in the expected way. If we put Nginx in the middle, we should not rely on OpenClaw's Tailscale header auth unless we deliberately preserve and validate that model.

### Existing Agent frontend

`$HOME/Agent` has a deployed web frontend with important voice/iPad ideas:

- `$HOME/Agent/.deploy/webui/static/app.js`
- `$HOME/Agent/.deploy/webui/static/app.css`
- `$HOME/Agent/.deploy/webui/index.html.tmpl`
- `$HOME/Agent/.deploy/nginx-agent.conf`
- `$HOME/Agent/.deploy/agent.yaml`

Notable frontend features in `app.js`:

- Microphone permission flow.
- Walkie-talkie style recording button.
- Audio upload button.
- File attachment button.
- Audio provider/model/language/prompt controls.
- Raw voice routing/refinement controls.
- iPad-friendly sketch/drawing surface and maximized layout support.

The current Nginx fragment routes:

- `/` -> `127.0.0.1:18080`
- `/a/<9xxx>/...` -> dynamic local agent ports
- `/projects/` -> local file listing

This is useful but too broad for a multi-agent baseline because `/` and `/a/` have global meaning and would collide with OpenClaw/Hermes prefixes.

## Proposed architecture

### Layering

1. Tailscale Serve:
   - Serve only one local Nginx endpoint.
   - Do not let individual apps call `tailscale serve` or `tailscale funnel`.

2. Nginx:
   - Listen on loopback only, e.g. `127.0.0.1:8443` or `127.0.0.1:8080`.
   - Provide all path routing.
   - Preserve WebSocket upgrade headers.
   - Forward `X-Forwarded-*` and `X-Forwarded-Prefix` consistently.
   - Keep generous body limits for audio uploads.
   - Disable proxy buffering for streaming and voice flows.

3. Services:
   - OpenClaw: `127.0.0.1:18789`, prefix `/openclaw/`.
   - Hermes dashboard/gateway surfaces: separate loopback ports, prefix `/hermes/` or `/hermes-dashboard/`.
   - Agent experimental frontend: `127.0.0.1:18080`, prefix `/agent/`.
   - Dynamic per-agent ports: prefer `/agents/<name>/` over raw `/a/<port>/`, but retain `/agent/a/<port>/` for the existing prototype if needed.
   - Static/private tools: explicit prefixes such as `/publish/`, `/timezones/`, `/projects/` only if actually wanted.

### Preferred public URL model

Use the existing MagicDNS HTTPS host as the single origin:

- `https://bvm-ws.axolotl-saurolophus.ts.net/openclaw/`
- `https://bvm-ws.axolotl-saurolophus.ts.net/hermes/`
- `https://bvm-ws.axolotl-saurolophus.ts.net/agent/`
- `https://bvm-ws.axolotl-saurolophus.ts.net/agents/<agent-id>/`

A single origin is good for iPad and voice because browser microphone support requires secure context, which Tailscale HTTPS provides.

## Phase 0: Safety and inventory

Before changing anything:

1. Snapshot config files:
   - `/home/brunomanti/.openclaw/openclaw.json`
   - `/etc/nginx/nginx.conf`
   - `/etc/nginx/conf.d/*.conf`
   - any current Tailscale Serve configuration output.

2. Record current processes/listeners:
   - OpenClaw gateway PID and ports.
   - Hermes gateway PID and ports.
   - Tailscale Serve listeners.
   - Nginx active/inactive state.

3. Define rollback:
   - Restore OpenClaw config backup.
   - Stop Nginx if needed.
   - Restore previous Tailscale Serve config.
   - Restart OpenClaw gateway.

4. Avoid destructive commands until the new Nginx config passes `nginx -t`.

## Phase 1: Simplify OpenClaw expectations

Goal: make OpenClaw a plain loopback backend, not the owner of Tailscale.

Recommended OpenClaw config changes:

```json5
{
  "gateway": {
    "mode": "local",
    "port": 18789,
    "bind": "loopback",
    "tailscale": {
      "mode": "off",
      "resetOnExit": false
    },
    "controlUi": {
      "enabled": true,
      "basePath": "/openclaw",
      "allowedOrigins": [
        "https://bvm-ws.axolotl-saurolophus.ts.net"
      ]
    },
    "auth": {
      "mode": "token",
      "token": "existing-token"
    }
  }
}
```

Notes:

- Keep `bind: "loopback"`; do not expose OpenClaw directly on LAN/tailnet.
- Set `tailscale.mode: "off"`; this stops OpenClaw from running or mutating `tailscale serve`.
- Keep token auth initially. Do not switch to `trusted-proxy` until the proxy headers and threat model are deliberately designed.
- Add `controlUi.basePath: "/openclaw"` so OpenClaw generates URLs under the prefix where possible.
- Keep `allowedOrigins` as the full Tailscale HTTPS origin, not the prefixed URL.
- Remove or stop relying on `allowInsecureAuth` once the reverse proxy is stable; initially leave it only if current OpenClaw startup requires it.

Important caveat:

OpenClaw's integrated Serve mode previously made `openclaw qr --json` advertise a `wss://bvm-ws...` URL. With `tailscale.mode: "off"`, that auto-advertised URL may change. If mobile pairing depends on it, either:

- configure OpenClaw's public/external gateway URL if it has a setting for that, or
- patch the QR/pairing URL generation later to understand the Nginx prefix, or
- temporarily leave OpenClaw Serve enabled until Nginx can reproduce the required WebSocket route.

This is the main risk area for not borking OpenClaw.

## Phase 2: Establish Tailscale -> Nginx baseline

Pick one local Nginx port. Existing `$HOME/Agent` uses `127.0.0.1:8080`; reuse it only if it remains dedicated to Nginx.

Target:

```bash
tailscale serve --bg https / http://127.0.0.1:8080
```

or equivalent persistent systemd service. The important policy is:

- Tailscale serves exactly Nginx.
- Apps do not call `tailscale serve`.
- OpenClaw `tailscale.mode` is off.
- Agent `agent-tailscale-proxy.service` should be disabled or not installed, because it also runs `tailscale serve 8080` and resets Serve on stop.

Existing risky service:

`$HOME/Agent/.deploy/agent-tailscale-proxy.service`

It contains:

```ini
ExecStart=/usr/bin/tailscale serve 8080
ExecStop=/usr/bin/tailscale serve reset
```

That is too broad for the new architecture because stopping this service can reset unrelated Tailscale Serve config. Replace with a dedicated host-level service whose only job is to map Tailscale HTTPS to Nginx, and avoid `tailscale serve reset` in app-specific services.

## Phase 3: Nginx routing design

### Core proxy headers

Use a common include for proxied apps:

```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Original-URI $request_uri;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;
proxy_buffering off;
```

At `http {}` scope, define:

```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}
```

For voice and iPad uploads:

```nginx
client_max_body_size 128m;
proxy_request_buffering off;
```

### Prefix rules

For every prefix:

- Redirect bare prefix to slash: `/openclaw` -> `/openclaw/`.
- Strip prefix before proxying unless the backend is configured to know its base path.
- Set `X-Forwarded-Prefix` to the external prefix.
- Rewrite cookie paths when needed.
- Rewrite absolute redirects from backend to prefix.

### OpenClaw route

Because OpenClaw can be configured with `controlUi.basePath: "/openclaw"`, first try preserving the prefix:

```nginx
location = /openclaw { return 308 /openclaw/; }
location /openclaw/ {
    proxy_set_header X-Forwarded-Prefix /openclaw;
    proxy_pass http://127.0.0.1:18789;
}
```

If OpenClaw expects the prefix stripped despite `basePath`, switch to:

```nginx
location /openclaw/ {
    proxy_set_header X-Forwarded-Prefix /openclaw;
    proxy_pass http://127.0.0.1:18789/;
    proxy_redirect ~^(/.*)$ /openclaw$1;
    proxy_cookie_path / /openclaw/;
}
```

Validate which behavior OpenClaw expects before finalizing.

### Agent prototype route

Move current `$HOME/Agent` frontend from root to `/agent/`:

```nginx
location = /agent { return 308 /agent/; }
location /agent/ {
    proxy_set_header X-Forwarded-Prefix /agent;
    proxy_pass http://127.0.0.1:18080/;
    proxy_redirect ~^(/.*)$ /agent$1;
    proxy_cookie_path / /agent/;
}
```

For the existing dynamic port router, avoid global `/a/`; use:

```nginx
location ~ "^/agent/a/(9[0-9][0-9][0-9])(/.*)?$" {
    set $agent_port $1;
    set $agent_path $2;
    if ($agent_path = "") { set $agent_path /; }
    set $agent_prefix /agent/a/$agent_port;

    proxy_set_header Host 127.0.0.1:$agent_port;
    proxy_set_header X-Forwarded-Prefix $agent_prefix;
    proxy_pass http://127.0.0.1:$agent_port$agent_path$is_args$args;
    proxy_redirect ~^(/.*)$ $agent_prefix$1;
    proxy_redirect ~^https?://(?:127\.0\.0\.1|localhost|0\.0\.0\.0):9[0-9][0-9][0-9](/.*)?$ $agent_prefix$1;
    proxy_cookie_path / $agent_prefix/;
}
```

### Hermes route

Hermes dashboard defaults to `127.0.0.1:9119` when run via `hermes dashboard`. It has host-header protection and tokenized local dashboard auth. Before proxying it under a prefix, verify whether it supports a base path. If not, prefer a separate Tailscale host/subdomain or route it at `/hermes/` only after testing all static asset URLs.

Initial safer option:

- Keep Hermes Telegram gateway separate from web dashboard.
- If dashboard is needed, run `hermes dashboard --host 127.0.0.1 --port 9119 --no-open` and test `/hermes/` in a staging Nginx config.

### Private publish/timezones

Only expose these if intended:

```nginx
location /publish/ { proxy_pass http://127.0.0.1:8123/; }
location /timezones/ { proxy_pass http://127.0.0.1:8125/; }
```

Do not expose raw autoindex directories until access policy is clear.

## Phase 4: Validation checklist

After config changes, validate in this order:

1. Nginx syntax:
   - `sudo nginx -t`

2. Local Nginx over loopback:
   - `curl -I http://127.0.0.1:8080/openclaw/`
   - `curl -I http://127.0.0.1:8080/agent/`

3. Tailscale HTTPS to Nginx:
   - Visit `https://bvm-ws.axolotl-saurolophus.ts.net/openclaw/` from laptop/iPad.
   - Visit `https://bvm-ws.axolotl-saurolophus.ts.net/agent/` from iPad.

4. WebSocket checks:
   - OpenClaw Control UI connects.
   - OpenClaw node pairing still works or fails in a known, fixable way.
   - Agent streaming/chat functions work.

5. Voice checks:
   - iPad Safari shows microphone permission prompt.
   - Recording starts and stops reliably.
   - Audio upload size works.
   - Transcription path works.
   - Long-running request does not time out.

6. Isolation checks:
   - OpenClaw Telegram still works.
   - Hermes Telegram still works through BVMHermesBot.
   - Stopping/restarting Agent does not reset Tailscale Serve.
   - Stopping/restarting OpenClaw does not mutate Tailscale Serve.

## Risks and mitigations

### Risk: OpenClaw pairing URL changes when Tailscale mode is turned off

Mitigation:

- Make a backup first.
- Test `openclaw qr --json` before and after.
- If it regresses, either keep OpenClaw Serve until public URL override is found, or patch/configure OpenClaw to advertise the Nginx-prefixed WSS URL.

### Risk: Prefix handling breaks static assets or WebSockets

Mitigation:

- Prefer apps with explicit base path support.
- Configure `basePath` where available.
- Use browser devtools network panel to identify absolute `/asset` or `/ws` paths.
- Consider separate MagicDNS hostnames if path-prefixing a specific app is brittle.

### Risk: Tailscale identity headers are lost or unsafe through Nginx

Mitigation:

- Do not rely on Tailscale identity headers for app auth at first.
- Keep app-level tokens/passwords enabled.
- Only switch to `trusted-proxy` after explicitly setting and validating trusted source IPs/headers.

### Risk: App-specific service resets global Tailscale Serve

Mitigation:

- Disable/remove app-specific `tailscale serve reset` services.
- Centralize Serve config in one host-level service.
- Never use `tailscale serve reset` casually once multiple routes exist.

### Risk: microphone APIs fail despite tailnet access

Mitigation:

- Use HTTPS, not HTTP over tailnet IP.
- Test on actual iPad Safari.
- Avoid iframes for mic UI unless permissions policy is configured.
- Add `Permissions-Policy` deliberately if embedding frontends later.

## Open questions

1. Should public access be tailnet-only Serve or public internet Funnel?
   - The stated goal sounds like tailnet HTTPS is enough, but “public DNS” could mean Tailscale MagicDNS, not internet-public Funnel.

2. Should services be path-prefixed on one MagicDNS host, or should we use multiple Tailscale Serve hostnames/routes if available?
   - Path-prefixing is elegant but can break apps that assume `/`.

3. Does OpenClaw expose a canonical public URL/base URL setting for QR and WebSocket advertisement independent of `gateway.tailscale.mode`?
   - Need to locate this before turning Serve off permanently.

4. Does Hermes dashboard support serving behind a subpath?
   - If not, it may need frontend/router changes or its own host.

5. Which frontends should be exposed to iPad immediately?
   - OpenClaw, Agent, Hermes dashboard, private publish, timezones, projects, or only a subset.

## Recommended next action

Do not change OpenClaw yet. First build a staging Nginx config at a new loopback port, e.g. `127.0.0.1:18088`, that proxies OpenClaw under `/openclaw/` and Agent under `/agent/`. Test locally with `curl` and browser. Once the route behavior is confirmed, move Tailscale Serve to point at the staging Nginx port, then switch OpenClaw `tailscale.mode` to `off` only after QR/pairing behavior is understood.
