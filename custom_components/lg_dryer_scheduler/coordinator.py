"""Data coordinator: polls device status and exposes capabilities from profile."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from thinqconnect.thinq_api import ThinQApi

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CAP_DELAY_END,
    CAP_DELAY_END_MINUTES,
    CAP_DELAY_END_RANGE,
    CAP_DELAY_START,
    CAP_DELAY_START_MINUTES,
    CAP_DELAY_START_RANGE,
    CAP_OPERATIONS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

_LOG = logging.getLogger(__name__)


class DryerCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls one LG dryer via the official ThinQ Connect API."""

    def __init__(
        self,
        hass: HomeAssistant,
        pat: str,
        country_code: str,
        client_id: str,
        device_id: str,
        device_alias: str,
    ) -> None:
        super().__init__(
            hass,
            _LOG,
            name=f"{DOMAIN} {device_alias}",
            update_interval=timedelta(seconds=DEFAULT_POLL_INTERVAL),
        )
        self._pat = pat
        self._country_code = country_code
        self._client_id = client_id
        self.device_id = device_id
        self.device_alias = device_alias
        self.capabilities: dict[str, Any] = {}

    def _api(self, session: aiohttp.ClientSession) -> ThinQApi:
        return ThinQApi(
            session=session,
            access_token=self._pat,
            country_code=self._country_code,
            client_id=self._client_id,
        )

    async def async_load_capabilities(self) -> None:
        """Read the device profile once and derive capability flags."""
        session = async_get_clientsession(self.hass)
        api = self._api(session)
        profile = await api.async_get_device_profile(self.device_id) or {}
        prop = profile.get("property", {})

        timer = prop.get("timer", {}) or {}
        operation = prop.get("operation", {}) or {}

        def _writable(field: dict | None) -> bool:
            if not field:
                return False
            mode = field.get("mode", [])
            return "w" in mode

        def _range(field: dict | None) -> tuple[int, int] | None:
            if not field:
                return None
            v = field.get("value", {}) or {}
            w = v.get("w")
            if not isinstance(w, dict):
                return None
            lo = w.get("min")
            hi = w.get("max")
            if isinstance(lo, int) and isinstance(hi, int):
                return (lo, hi)
            return None

        ops = operation.get("dryerOperationMode") or operation.get("washerOperationMode")
        op_values: set[str] = set()
        if isinstance(ops, dict):
            op_values = set((ops.get("value", {}) or {}).get("w", []) or [])

        self.capabilities = {
            CAP_OPERATIONS: op_values,
            CAP_DELAY_END: _writable(timer.get("relativeHourToStop")),
            CAP_DELAY_END_MINUTES: _writable(timer.get("relativeMinuteToStop")),
            CAP_DELAY_END_RANGE: _range(timer.get("relativeHourToStop")),
            CAP_DELAY_START: _writable(timer.get("relativeHourToStart")),
            CAP_DELAY_START_MINUTES: _writable(timer.get("relativeMinuteToStart")),
            CAP_DELAY_START_RANGE: _range(timer.get("relativeHourToStart")),
        }
        _LOG.info("Dryer %s capabilities: %s", self.device_alias, self.capabilities)

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        api = self._api(session)
        try:
            status = await api.async_get_device_status(self.device_id)
        except Exception as exc:  # pylint: disable=broad-except
            # NOT_CONNECTED_DEVICE etc. — surface as offline
            return {"online": False, "error": repr(exc), "raw": {}}

        if not status:
            return {"online": False, "error": "empty status", "raw": {}}

        return self._flatten(status)

    @staticmethod
    def _flatten(status: dict) -> dict[str, Any]:
        run_state = (status.get("runState") or {}).get("currentState")
        rce = (status.get("remoteControlEnable") or {}).get("remoteControlEnabled")
        timer = status.get("timer") or {}
        operation = status.get("operation") or {}
        return {
            "online": True,
            "raw": status,
            "current_state": run_state,
            "remote_control_enabled": rce,
            "operation_mode": (
                operation.get("dryerOperationMode")
                or operation.get("washerOperationMode")
            ),
            "remain_hour": timer.get("remainHour"),
            "remain_minute": timer.get("remainMinute"),
            "total_hour": timer.get("totalHour"),
            "total_minute": timer.get("totalMinute"),
            "relative_hour_to_stop": timer.get("relativeHourToStop"),
            "relative_minute_to_stop": timer.get("relativeMinuteToStop"),
            "relative_hour_to_start": timer.get("relativeHourToStart"),
            "relative_minute_to_start": timer.get("relativeMinuteToStart"),
        }

    # --- control commands ---

    async def async_send_operation(self, mode: str) -> None:
        """Send {operation: {dryerOperationMode: mode}}."""
        await self._post({"operation": {"dryerOperationMode": mode}})

    async def async_set_delay_end(self, hours: int, minutes: int = 0) -> None:
        """Set delay-end timer. Will only include minutes if writable."""
        timer: dict[str, int] = {"relativeHourToStop": hours}
        if minutes and self.capabilities.get(CAP_DELAY_END_MINUTES):
            timer["relativeMinuteToStop"] = minutes
        await self._post({"timer": timer})

    async def async_set_delay_start(self, hours: int, minutes: int = 0) -> None:
        """Set delay-start timer (and START)."""
        timer: dict[str, int] = {"relativeHourToStart": hours}
        if minutes and self.capabilities.get(CAP_DELAY_START_MINUTES):
            timer["relativeMinuteToStart"] = minutes
        await self._post({"timer": timer})
        # Some models require an explicit START after timer; others auto-go to RESERVED.
        # Send START opportunistically; ignore if rejected.
        try:
            await self.async_send_operation("START")
        except Exception as exc:  # pylint: disable=broad-except
            _LOG.debug("delay_start: explicit START rejected (likely already RESERVED): %s", exc)

    async def _post(self, payload: dict[str, Any]) -> None:
        session = async_get_clientsession(self.hass)
        api = self._api(session)
        await api.async_post_device_control(device_id=self.device_id, payload=payload)
        # Refresh state after a brief delay
        await self.async_request_refresh()
