"""Button entities: start, stop, power_off, wake_up."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CAP_OPERATIONS,
    DOMAIN,
    OP_POWER_OFF,
    OP_START,
    OP_STOP,
    OP_WAKE_UP,
)
from .coordinator import DryerCoordinator

_LOG = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: DryerCoordinator = hass.data[DOMAIN][entry.entry_id]
    ops = coord.capabilities.get(CAP_OPERATIONS) or set()
    entities = []
    if OP_START in ops:
        entities.append(_OpButton(coord, entry, "start", "Start", OP_START, "mdi:play"))
    if OP_STOP in ops:
        entities.append(_OpButton(coord, entry, "stop", "Stop", OP_STOP, "mdi:stop"))
    if OP_POWER_OFF in ops:
        entities.append(
            _OpButton(coord, entry, "power_off", "Power Off", OP_POWER_OFF, "mdi:power")
        )
    if OP_WAKE_UP in ops:
        entities.append(
            _OpButton(coord, entry, "wake_up", "Wake Up", OP_WAKE_UP, "mdi:alarm")
        )
    async_add_entities(entities)


class _OpButton(CoordinatorEntity[DryerCoordinator], ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, entry, key, name, op_value, icon):
        super().__init__(coord)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_icon = icon
        self._op = op_value

    async def async_press(self) -> None:
        try:
            await self.coordinator.async_send_operation(self._op)
        except Exception as exc:  # pylint: disable=broad-except
            raise HomeAssistantError(f"{self._op} failed: {exc}") from exc

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.device_id)},
            "name": self.coordinator.device_alias,
            "manufacturer": "LG",
            "model": "ThinQ Connect Dryer",
            "entry_type": "service",
        }
