"""Sensor entities for LG Dryer Scheduler."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DryerCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coord: DryerCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        _Field(coord, entry, "current_state", "Run State", "mdi:tumble-dryer"),
        _Field(coord, entry, "operation_mode", "Operation Mode", "mdi:cog-outline"),
        _Time(coord, entry, "remain", "Time Remaining"),
        _Time(coord, entry, "total", "Cycle Total"),
        _Time(coord, entry, "relative_to_stop", "Time Until End"),
        _Time(coord, entry, "relative_to_start", "Time Until Start"),
        _Progress(coord, entry),
        _Timestamp(coord, entry, "estimated_finish", "Estimated Finish", "mdi:clock-end"),
        _Timestamp(coord, entry, "estimated_start", "Estimated Start", "mdi:clock-start"),
        _Timestamp(
            coord, entry, "last_running_started", "Last Cycle Started",
            "mdi:play-circle-outline",
        ),
        _Timestamp(
            coord, entry, "last_finished", "Last Cycle Finished",
            "mdi:check-circle-outline",
        ),
        _Diagnostic(coord, entry),
    ]
    async_add_entities(entities)


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
        return (self.coordinator.data or {}).get(self._field)


class _Time(_Base):
    """Renders an Hh Mm string from {prefix}_hour and {prefix}_minute."""

    def __init__(self, coord, entry, prefix, name):
        super().__init__(coord, entry, prefix, name)
        self._prefix = prefix
        self._attr_icon = "mdi:timer-outline"

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        h = d.get(f"{self._prefix}_hour")
        m = d.get(f"{self._prefix}_minute")
        if h is None and m is None:
            return None
        return f"{h or 0}h {(m or 0):02d}m"

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data or {}
        h = d.get(f"{self._prefix}_hour") or 0
        m = d.get(f"{self._prefix}_minute") or 0
        return {
            "hours": d.get(f"{self._prefix}_hour"),
            "minutes": d.get(f"{self._prefix}_minute"),
            "total_minutes": h * 60 + m,
        }


class _Progress(_Base):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:progress-clock"

    def __init__(self, coord, entry):
        super().__init__(coord, entry, "progress_pct", "Cycle Progress")

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("progress_pct")


class _Timestamp(_Base):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coord, entry, field, name, icon):
        super().__init__(coord, entry, field, name)
        self._field = field
        self._attr_icon = icon

    @property
    def native_value(self) -> datetime | None:
        v = (self.coordinator.data or {}).get(self._field)
        return v if isinstance(v, datetime) else None


class _Diagnostic(_Base):
    """Exposes capabilities + raw status as attributes for dashboard logic."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:information-outline"

    def __init__(self, coord, entry):
        super().__init__(coord, entry, "diagnostic", "Diagnostics")

    @property
    def native_value(self):
        d = self.coordinator.data or {}
        if not d.get("online", True):
            return "offline"
        return "online"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {
            "device_id": self.coordinator.device_id,
            "alias": self.coordinator.device_alias,
            "capabilities": self.coordinator.capabilities,
            "last_update": d.get("last_update"),
            "last_error": d.get("error"),
            "raw_status": d.get("raw"),
        }
