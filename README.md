# LG Dryer Scheduler — LG ThinQ Connect HA integration

Home Assistant custom integration that schedules an LG dryer using LG's **official ThinQ Connect API**. The dryer runs on its **own internal clock** once the timer is set — no WiFi or HA needed during the wait.

## Why this exists

LG dryers expose their delay timer via the official ThinQ Connect API. Setting `relativeHourToStop` puts the dryer into `RESERVED` state where it counts down on its own clock and starts itself — completely robust against WiFi / HA / cloud outages once the command is sent. The unofficial `smartthinq_sensors` integration's `wake_up` + `button.press` flow is unreliable, and LG has hard-blocked the unofficial API for many accounts.

This integration auto-detects what your specific dryer model supports and exposes only the appropriate buttons/services.

## Entities

### Sensors

| Entity | Description |
|---|---|
| `{alias}_run_state` | Current state: `INITIAL`, `SLEEP`, `RESERVED`, `RUNNING`, `END`, `POWER_OFF`, `ERROR`, ... |
| `{alias}_operation_mode` | Last operation sent (`START`, `STOP`, ...) |
| `{alias}_time_remaining` | Time left in current cycle (e.g. `1h 23m`) |
| `{alias}_cycle_total` | Total length of selected program |
| `{alias}_time_until_end` | Countdown to scheduled end (when in `RESERVED`) |
| `{alias}_time_until_start` | Countdown to scheduled start (model-dependent) |
| `{alias}_cycle_progress` | Percentage complete when running |
| `{alias}_estimated_finish` | Timestamp — when the cycle will be done |
| `{alias}_estimated_start` | Timestamp — when the cycle will actually start |
| `{alias}_last_cycle_started` | Timestamp — when the most recent cycle started running |
| `{alias}_last_cycle_finished` | Timestamp — when the most recent cycle ended |
| `{alias}_diagnostics` | `online`/`offline`. Attributes include `capabilities`, `last_update`, `last_error`, `raw_status` |

### Binary sensors

| Entity | Description |
|---|---|
| `{alias}_online` | True when the API can reach the dryer |
| `{alias}_remote_control_enabled` | True when Remote Start is active on the dryer |

### Buttons (only created if the dryer profile exposes them)

- `start`, `stop`, `power_off`, `wake_up`

## Services

### `lg_dryer_scheduler.delay_end` — finish in N hours

```yaml
service: lg_dryer_scheduler.delay_end
data:
  hours: 8
  minutes: 0   # ignored if model only supports whole hours
```

The dryer enters `RESERVED` and counts down on its own clock. Validates against the dryer's reported allowed range (e.g. 3–19 hours).

### `lg_dryer_scheduler.delay_start` — start in N hours (model-dependent)

```yaml
service: lg_dryer_scheduler.delay_start
data:
  hours: 5
```

Service will refuse with a clear error if the dryer's profile says delay-start isn't supported. Use `delay_end` instead.

### `lg_dryer_scheduler.refresh` — force an immediate poll

```yaml
service: lg_dryer_scheduler.refresh
```

### `lg_dryer_scheduler.get_energy_usage` — fetch energy data

Returns response data — use `response_variable` in your script:

```yaml
service: lg_dryer_scheduler.get_energy_usage
data:
  start_date: "2026-04-01"
  end_date: "2026-04-29"
  period: DAY
  energy_property: totalEnergy
response_variable: energy
```

## Setup

### 1. Get a Personal Access Token

1. Go to <https://connect-pat.lgthinq.com>
2. Sign in with the same LG account that owns your dryer
3. Click **Create new token**
4. Give it scopes: `device.read` and `device.write`
5. Copy the token

### 2. Install via HACS

1. HACS → 3-dot menu → **Custom repositories**
2. Add this repo URL, category: **Integration**
3. Install **LG Dryer Scheduler**
4. Restart HA

### 3. Add the integration

1. **Settings → Devices & Services → Add Integration**
2. Search for **LG Dryer Scheduler**
3. Paste your PAT, set country code (e.g. `DK`), leave client_id blank
4. Pick your dryer from the list

## Dashboard example

Replace `torretumbler` with your dryer's entity prefix.

```yaml
type: vertical-stack
cards:
  - type: heading
    heading: Tørretumbler
    icon: mdi:tumble-dryer

  - type: entities
    entities:
      - entity: sensor.torretumbler_run_state
        name: Status
      - entity: sensor.torretumbler_cycle_progress
        name: Progress
      - entity: sensor.torretumbler_estimated_start
        name: Starter
      - entity: sensor.torretumbler_estimated_finish
        name: Færdig
      - entity: sensor.torretumbler_time_remaining
        name: Resterende
      - entity: binary_sensor.torretumbler_remote_control_enabled
        name: Remote control klar

  - type: conditional
    conditions:
      - entity: sensor.torretumbler_run_state
        state: RUNNING
    card:
      type: gauge
      entity: sensor.torretumbler_cycle_progress
      min: 0
      max: 100
      severity:
        green: 0
        yellow: 60
        red: 90

  - type: horizontal-stack
    cards:
      - type: button
        entity: button.torretumbler_start
        name: Start
      - type: button
        entity: button.torretumbler_stop
        name: Stop
      - type: button
        entity: button.torretumbler_wake_up
        name: Vågn op
```

## Capability-aware automations

Capabilities are exposed as attributes on the diagnostics sensor:

```yaml
{% set caps = state_attr('sensor.torretumbler_diagnostics', 'capabilities') %}
{% if caps.delay_end %}
  service: lg_dryer_scheduler.delay_end
  ...
{% elif caps.delay_start %}
  service: lg_dryer_scheduler.delay_start
  ...
{% endif %}
```

## Notes on minute precision

Many LG dryers expose only `relativeHourToStop` as writable, with `relativeMinuteToStop` read-only. The integration accepts a `minutes` parameter but silently drops it if the profile says minutes aren't writable. That's a per-model API limitation, not a bug here.

## License

MIT
