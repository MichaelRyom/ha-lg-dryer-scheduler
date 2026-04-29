"""Binary sensors: online + remote_control_enabled."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DryerCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: DryerCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            _Bool(coord, entry, "online", "Online", "mdi:cloud-check"),
            _Bool(
                coord,
                entry,
                "remote_control_enabled",
                "Remote Control Enabled",
                "mdi:remote",
            ),
        ]
    )


class _Bool(CoordinatorEntity[DryerCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord, entry, field, name, icon):
        super().__init__(coord)
        self._attr_unique_id = f"{entry.entry_id}_{field}"
        self._attr_name = name
        self._attr_icon = icon
        self._field = field

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return bool(self.coordinator.data.get(self._field))

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.device_id)},
            "name": self.coordinator.device_alias,
            "manufacturer": "LG",
            "model": "ThinQ Connect Dryer",
            "entry_type": "service",
        }
