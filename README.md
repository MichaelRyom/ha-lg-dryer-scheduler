# LG Dryer Scheduler — LG ThinQ Connect HA integration

Home Assistant custom integration that schedules an LG dryer to finish (or start) at a specific time using LG's **official ThinQ Connect API**. Built because the unofficial `smartthinq_sensors` integration's `wake_up` + `button.press` flow is unreliable and LG has hard-blocked the unofficial API for many accounts.

The dryer runs on its **own internal clock** once the timer is set — no WiFi or HA needed during the wait.

## Features

- Auto-detects what your dryer's profile actually supports (`delay_end` vs `delay_start`, valid hour ranges, whether minutes are settable)
- Buttons for `start`, `stop`, `power_off`, `wake_up` — only the ones the API exposes for your model
- Sensors for run state, operation mode, remaining time, total time, time until start/end
- Binary sensors for `online` and `remote_control_enabled`
- Two services for scheduling:
  - `lg_dryer_scheduler.delay_end` — finish in N hours
  - `lg_dryer_scheduler.delay_start` — start in N hours (model-dependent)
- Polls every 30s

## Why this exists

LG dryers expose their delay timer via the official ThinQ Connect API. Setting `relativeHourToStop` puts the dryer into `RESERVED` state where it counts down on its own clock and starts itself — completely robust against WiFi / HA / cloud outages once the command is sent.

The official `lg_thinq` integration in HA core does not expose the delay timer as a service. This integration does.

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

The integration immediately fetches the device profile and configures itself based on what your dryer supports.

## Usage

### Manually

After loading the dryer and pressing **Remote Start** physically on the dryer:

**Developer Tools → Actions** → `lg_dryer_scheduler.delay_end`:

```yaml
service: lg_dryer_scheduler.delay_end
data:
  hours: 8
```

The dryer enters `RESERVED` state and counts down. State updates show up in HA via the `sensor.{alias}_run_state` entity.

### From an automation

```yaml
automation:
  - alias: "Dryer at cheapest electricity"
    trigger:
      - platform: state
        entity_id: binary_sensor.torretumbler_remote_control_enabled
        to: "on"
    action:
      - service: lg_dryer_scheduler.delay_end
        data:
          # compute hours from your cheap-window logic
          hours: >
            {% set start_dt = as_datetime(states('sensor.dryer_optimal_start')) | as_local %}
            {% set duration = state_attr('sensor.dryer_optimal_start', 'duration_hours') | int %}
            {% set end_dt = start_dt + timedelta(hours=duration) %}
            {{ ((end_dt - now()).total_seconds() / 3600) | round(0, 'ceil') | int }}
```

### Capabilities

The integration exposes capabilities at runtime so you can build fallbacks:

```yaml
{% set caps = state_attr('sensor.torretumbler_run_state', 'capabilities') %}
{% if caps and caps.delay_end %}
  use delay_end
{% elif caps and caps.delay_start %}
  use delay_start
{% endif %}
```

(Capabilities aren't currently surfaced as state attributes — coming in a future version. For now check the integration's debug log on first setup.)

## Notes on minute precision

Many LG dryers expose only `relativeHourToStop` as writable, with `relativeMinuteToStop` read-only. The integration accepts a `minutes` parameter but silently drops it if the profile says minutes aren't writable. That's a per-model API limitation, not a bug here.

## License

MIT
