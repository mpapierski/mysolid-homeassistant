## MySolid

[![Open your Home Assistant instance and add this repository from HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=mpapierski&repository=mysolid&category=integration)

Home Assistant custom component for MySolid / Solid Security.

This integration is based on the HTTP API and push flow reverse engineered from
the original Android APK. To receive near-real-time events, it impersonates a
mobile phone: it logs in with app-like headers, registers a device ID and
Firebase token, and keeps the Google MCS push listener used by the mobile app.
That lets Home Assistant track alarm changes quickly and use them in
automations.

## What It Provides

- config-flow setup for Poland, Czech Republic, or a custom host
- persisted MySolid session, `deviceId`, push credentials, and MCS
  `persistent_id` state
- hybrid push plus polling refresh, with automatic push reconnect
- `alarm_control_panel` entities for arm-capable relays
- `switch` entities for non-alarm relays
- `camera` entities using RTSP URL patterns derived from the Android app
- diagnostic `sensor` and `binary_sensor` entities
- `mysolid.*` services for relay execution and account/admin-style API actions

Reverse-engineered API notes are documented in `docs/MYSOLID.md`.

## Installation

Install it as a Home Assistant custom integration by placing
`custom_components/mysolid` in your Home Assistant configuration, or by adding
this repository as a custom repository in HACS.

## Development

This project is `uv`-managed.

```bash
uv sync --group dev
uv run pytest -q
uv run ruff check .
uv run python -m compileall custom_components
```

CI also runs Home Assistant `hassfest` validation for the custom component.
