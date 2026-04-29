"""Config flow: ask for PAT, list devices, pick a dryer."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import voluptuous as vol
from thinqconnect.thinq_api import ThinQApi

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_CLIENT_ID, CONF_COUNTRY_CODE, CONF_DEVICE_ID, CONF_PAT, DOMAIN

_LOG = logging.getLogger(__name__)


class DryerSchedulerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dryer Scheduler."""

    VERSION = 1

    def __init__(self) -> None:
        self._pat: str | None = None
        self._country: str | None = None
        self._client_id: str | None = None
        self._devices: list[dict[str, Any]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            self._pat = user_input[CONF_PAT].strip()
            self._country = user_input[CONF_COUNTRY_CODE].strip().upper()
            self._client_id = user_input.get(CONF_CLIENT_ID, "").strip() or str(
                uuid.uuid4()
            )
            session = async_get_clientsession(self.hass)
            api = ThinQApi(
                session=session,
                access_token=self._pat,
                country_code=self._country,
                client_id=self._client_id,
            )
            try:
                response = await api.async_get_device_list()
            except Exception:  # pylint: disable=broad-except
                _LOG.exception("Failed to list devices")
                errors["base"] = "cannot_connect"
            else:
                self._devices = [
                    d
                    for d in (response or [])
                    if (d.get("deviceInfo", {}).get("deviceType") or "").upper()
                    in ("DEVICE_DRYER", "DEVICE_WASHER", "DEVICE_WASHER_DRYER")
                ]
                if not self._devices:
                    errors["base"] = "no_dryer_found"
                else:
                    return await self.async_step_select_device()

        schema = vol.Schema(
            {
                vol.Required(CONF_PAT): str,
                vol.Required(CONF_COUNTRY_CODE, default="DK"): str,
                vol.Optional(CONF_CLIENT_ID): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_select_device(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID]
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            picked = next(d for d in self._devices if d["deviceId"] == device_id)
            alias = picked.get("deviceInfo", {}).get("alias", "Dryer")
            return self.async_create_entry(
                title=alias,
                data={
                    CONF_PAT: self._pat,
                    CONF_COUNTRY_CODE: self._country,
                    CONF_CLIENT_ID: self._client_id,
                    CONF_DEVICE_ID: device_id,
                },
            )

        choices = {
            d["deviceId"]: f"{d.get('deviceInfo', {}).get('alias', d['deviceId'])} ({d.get('deviceInfo', {}).get('modelName', '?')})"
            for d in self._devices
        }
        schema = vol.Schema({vol.Required(CONF_DEVICE_ID): vol.In(choices)})
        return self.async_show_form(step_id="select_device", data_schema=schema)
