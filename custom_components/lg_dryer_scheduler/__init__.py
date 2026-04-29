"""LG Dryer Scheduler integration."""

from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    CAP_DELAY_END,
    CAP_DELAY_END_MINUTES,
    CAP_DELAY_END_RANGE,
    CAP_DELAY_START,
    CAP_DELAY_START_MINUTES,
    CAP_DELAY_START_RANGE,
    CONF_CLIENT_ID,
    CONF_COUNTRY_CODE,
    CONF_DEVICE_ID,
    CONF_PAT,
    DOMAIN,
    SERVICE_DELAY_END,
    SERVICE_DELAY_START,
    SERVICE_GET_ENERGY_USAGE,
    SERVICE_REFRESH,
)
from .coordinator import DryerCoordinator

_LOG = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up LG Dryer Scheduler from a config entry."""
    data = entry.data
    coordinator = DryerCoordinator(
        hass,
        pat=data[CONF_PAT],
        country_code=data[CONF_COUNTRY_CODE],
        client_id=data[CONF_CLIENT_ID],
        device_id=data[CONF_DEVICE_ID],
        device_alias=entry.title,
    )
    await coordinator.async_load_capabilities()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


def _coordinators(hass: HomeAssistant) -> list[DryerCoordinator]:
    return list(hass.data.get(DOMAIN, {}).values())


def _resolve_target(hass: HomeAssistant, call: ServiceCall) -> DryerCoordinator:
    """Find the coordinator whose entity_id was targeted, else the only one."""
    coords = _coordinators(hass)
    if not coords:
        raise HomeAssistantError("No dryer scheduler configured")
    target = call.data.get("entity_id")
    if isinstance(target, list):
        target = target[0] if target else None
    if target:
        for c in coords:
            if c.device_id in target or c.device_alias.lower() in (target or "").lower():
                return c
    if len(coords) == 1:
        return coords[0]
    raise HomeAssistantError(
        "Multiple dryers configured — pass an entity_id from the target dryer"
    )


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_DELAY_END):
        return  # already registered

    async def _handle_delay_end(call: ServiceCall) -> None:
        coord = _resolve_target(hass, call)
        if not coord.capabilities.get(CAP_DELAY_END):
            raise HomeAssistantError(
                f"{coord.device_alias} does not support delay-end via API"
            )
        hours = int(call.data["hours"])
        minutes = int(call.data.get("minutes", 0))
        rng = coord.capabilities.get(CAP_DELAY_END_RANGE)
        if rng and not (rng[0] <= hours <= rng[1]):
            raise HomeAssistantError(
                f"hours must be in {rng[0]}..{rng[1]} (got {hours})"
            )
        if minutes and not coord.capabilities.get(CAP_DELAY_END_MINUTES):
            _LOG.warning(
                "%s: delay-end minutes not writable on this model — ignoring minute=%d",
                coord.device_alias,
                minutes,
            )
            minutes = 0
        await coord.async_set_delay_end(hours=hours, minutes=minutes)

    async def _handle_delay_start(call: ServiceCall) -> None:
        coord = _resolve_target(hass, call)
        if not coord.capabilities.get(CAP_DELAY_START):
            raise HomeAssistantError(
                f"{coord.device_alias} does not support delay-start via API "
                "(this model only supports delay-end — use that instead)"
            )
        hours = int(call.data["hours"])
        minutes = int(call.data.get("minutes", 0))
        rng = coord.capabilities.get(CAP_DELAY_START_RANGE)
        if rng and not (rng[0] <= hours <= rng[1]):
            raise HomeAssistantError(
                f"hours must be in {rng[0]}..{rng[1]} (got {hours})"
            )
        if minutes and not coord.capabilities.get(CAP_DELAY_START_MINUTES):
            _LOG.warning(
                "%s: delay-start minutes not writable on this model — ignoring",
                coord.device_alias,
            )
            minutes = 0
        await coord.async_set_delay_start(hours=hours, minutes=minutes)

    delay_schema = vol.Schema(
        {
            vol.Optional("entity_id"): cv.string,
            vol.Required("hours"): vol.All(vol.Coerce(int), vol.Range(min=0, max=24)),
            vol.Optional("minutes", default=0): vol.All(
                vol.Coerce(int), vol.Range(min=0, max=59)
            ),
        }
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELAY_END, _handle_delay_end, schema=delay_schema
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELAY_START, _handle_delay_start, schema=delay_schema
    )

    async def _handle_refresh(call: ServiceCall) -> None:
        coord = _resolve_target(hass, call)
        await coord.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _handle_refresh,
        schema=vol.Schema({vol.Optional("entity_id"): cv.string}),
    )

    async def _handle_get_energy_usage(call: ServiceCall) -> dict:
        coord = _resolve_target(hass, call)
        try:
            data = await coord.async_get_energy_usage(
                start=str(call.data["start_date"]),
                end=str(call.data["end_date"]),
                period=call.data.get("period", "DAY"),
                energy_property=call.data.get("energy_property", "totalEnergy"),
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise HomeAssistantError(f"Energy usage fetch failed: {exc}") from exc
        return {"data": data}

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_ENERGY_USAGE,
        _handle_get_energy_usage,
        schema=vol.Schema(
            {
                vol.Optional("entity_id"): cv.string,
                vol.Required("start_date"): cv.string,
                vol.Required("end_date"): cv.string,
                vol.Optional("period", default="DAY"): vol.In(["DAY", "MONTH", "YEAR"]),
                vol.Optional("energy_property", default="totalEnergy"): cv.string,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
