"""Data coordinator: polls device status and exposes capabilities from profile."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from thinqconnect.thinq_api import ThinQApi

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

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
        self.profile: dict[str, Any] = {}
        self._last_state: str | None = None
        self._last_running_started: datetime | None = None
        self._last_finished: datetime | None = None

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
        self.profile = profile
        prop = profile.get("property", {})
        timer = prop.get("timer", {}) or {}
        operation = prop.get("operation", {}) or {}

        def _writable(field: dict | None) -> bool:
            return bool(field and "w" in (field.get("mode", []) or []))

        def _range(field: dict | None) -> tuple[int, int] | None:
            if not field:
                return None
            w = (field.get("value", {}) or {}).get("w")
            if isinstance(w, dict):
                lo, hi = w.get("min"), w.get("max")
                if isinstance(lo, int) and isinstance(hi, int):
                    return (lo, hi)
            return None

        ops = operation.get("dryerOperationMode") or operation.get("washerOperationMode")
        op_values: set[str] = set()
        if isinstance(ops, dict):
            op_values = set((ops.get("value", {}) or {}).get("w", []) or [])

        self.capabilities = {
            CAP_OPERATIONS: sorted(op_values),
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
        now = datetime.now(timezone.utc)
        try:
            status = await api.async_get_device_status(self.device_id)
        except Exception as exc:  # pylint: disable=broad-except
            return {
                "online": False,
                "error": repr(exc),
                "raw": {},
                "last_update": now,
            }

        if not status:
            return {
                "online": False,
                "error": "empty status",
                "raw": {},
                "last_update": now,
            }

        data = self._flatten(status)
        data["last_update"] = now
        self._track_transitions(data, now)
        data["last_running_started"] = self._last_running_started
        data["last_finished"] = self._last_finished
        return data

    def _track_transitions(self, data: dict[str, Any], now: datetime) -> None:
        state = data.get("current_state")
        prev = self._last_state
        if state != prev:
            if state == "RUNNING":
                self._last_running_started = now
            if prev == "RUNNING" and state in ("END", "POWER_OFF", "INITIAL", "SLEEP"):
                self._last_finished = now
            self._last_state = state

    @staticmethod
    def _flatten(status: dict) -> dict[str, Any]:
        run = status.get("runState") or {}
        rce = status.get("remoteControlEnable") or {}
        timer = status.get("timer") or {}
        operation = status.get("operation") or {}

        run_state = run.get("currentState")
        remain_h = timer.get("remainHour") or 0
        remain_m = timer.get("remainMinute") or 0
        total_h = timer.get("totalHour") or 0
        total_m = timer.get("totalMinute") or 0
        rel_stop_h = timer.get("relativeHourToStop") or 0
        rel_stop_m = timer.get("relativeMinuteToStop") or 0
        rel_start_h = timer.get("relativeHourToStart") or 0
        rel_start_m = timer.get("relativeMinuteToStart") or 0

        progress_pct: int | None = None
        if run_state == "RUNNING" and (total_h or total_m):
            total_min = total_h * 60 + total_m
            remain_min = remain_h * 60 + remain_m
            if total_min > 0:
                progress_pct = max(0, min(100, round((1 - remain_min / total_min) * 100)))

        now = datetime.now(timezone.utc)
        estimated_finish: datetime | None = None
        estimated_start: datetime | None = None

        if run_state == "RUNNING" and (remain_h or remain_m):
            estimated_finish = now + timedelta(hours=remain_h, minutes=remain_m)
        elif run_state == "RESERVED":
            if rel_stop_h or rel_stop_m:
                estimated_finish = now + timedelta(hours=rel_stop_h, minutes=rel_stop_m)
                if total_h or total_m:
                    estimated_start = estimated_finish - timedelta(
                        hours=total_h, minutes=total_m
                    )
            elif rel_start_h or rel_start_m:
                estimated_start = now + timedelta(hours=rel_start_h, minutes=rel_start_m)
                if total_h or total_m:
                    estimated_finish = estimated_start + timedelta(
                        hours=total_h, minutes=total_m
                    )

        return {
            "online": True,
            "raw": status,
            "current_state": run_state,
            "remote_control_enabled": rce.get("remoteControlEnabled"),
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
            "progress_pct": progress_pct,
            "estimated_finish": estimated_finish,
            "estimated_start": estimated_start,
        }

    # --- control commands ---

    async def async_send_operation(self, mode: str) -> None:
        await self._post({"operation": {"dryerOperationMode": mode}})

    async def async_set_delay_end(self, hours: int, minutes: int = 0) -> None:
        timer: dict[str, int] = {"relativeHourToStop": hours}
        if minutes and self.capabilities.get(CAP_DELAY_END_MINUTES):
            timer["relativeMinuteToStop"] = minutes
        await self._post({"timer": timer})

    async def async_set_delay_start(self, hours: int, minutes: int = 0) -> None:
        timer: dict[str, int] = {"relativeHourToStart": hours}
        if minutes and self.capabilities.get(CAP_DELAY_START_MINUTES):
            timer["relativeMinuteToStart"] = minutes
        await self._post({"timer": timer})
        try:
            await self.async_send_operation("START")
        except Exception as exc:  # pylint: disable=broad-except
            _LOG.debug("delay_start: explicit START rejected: %s", exc)

    async def async_get_energy_usage(
        self,
        start: str,
        end: str,
        period: str = "DAY",
        energy_property: str = "totalEnergy",
    ) -> Any:
        """Fetch energy usage between two ISO date strings (YYYY-MM-DD)."""
        session = async_get_clientsession(self.hass)
        api = self._api(session)
        return await api.async_get_device_energy_usage(
            device_id=self.device_id,
            energy_property=energy_property,
            period=period,
            start_date=start,
            end_date=end,
        )

    async def async_get_energy_profile(self) -> Any:
        """Fetch the energy property profile for this device."""
        session = async_get_clientsession(self.hass)
        api = self._api(session)
        return await api.async_get_device_energy_profile(device_id=self.device_id)

    async def _post(self, payload: dict[str, Any]) -> None:
        session = async_get_clientsession(self.hass)
        api = self._api(session)
        await api.async_post_device_control(device_id=self.device_id, payload=payload)
        await self.async_request_refresh()
