"""Sensor entities for LG Dryer Scheduler."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
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
            _Field(coord, entry, "current_state", "Run State", "mdi:tumble-dryer"),
            _Field(coord, entry, "operation_mode", "Operation Mode", "mdi:cog-outline"),
            _Time(coord, entry, "remain", "Remaining"),
            _Time(coord, entry, "total", "Total Duration"),
            _Time(coord, entry, "relative_to_stop", "Time Until End"),
            _Time(coord, entry, "relative_to_start", "Time Until Start"),
        ]
    )


class _Base(CoordinatorEntity[DryerCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coord: DryerCoordinator, entry: ConfigEntry, key: str, name: str):
        super().__init__(coord)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.coordinator.device_id)},
            "name": self.coordinator.device_alias,
            "manufacturer": "LG",
            "model": "ThinQ Connect Dryer",
            "entry_type": "service",
        }


class _Field(_Base):
    def __init__(self, coord, entry, field, name, icon):
        super().__init__(coord, entry, field, name)
        self._field = field
        self._attr_icon = icon

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._field)


class _Time(_Base):
    """Renders an Hh Mm string from {prefix}_hour and {prefix}_minute."""

    def __init__(self, coord, entry, prefix, name):
        super().__init__(coord, entry, prefix, name)
        self._prefix = prefix
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        h = self.coordinator.data.get(f"{self._prefix}_hour")
        m = self.coordinator.data.get(f"{self._prefix}_minute")
        if h is None and m is None:
            return None
        h = h or 0
        m = m or 0
        return f"{h}h {m:02d}m"

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
        return {
            "hours": self.coordinator.data.get(f"{self._prefix}_hour"),
            "minutes": self.coordinator.data.get(f"{self._prefix}_minute"),
        }
