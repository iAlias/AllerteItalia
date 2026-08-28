"""Binary sensors: is something worth attention happening right now."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_ALERT_MIN_LEVEL,
    CONF_HEAT_THRESHOLD,
    CONF_QUAKE_MIN_MAGNITUDE,
    DEFAULT_HEAT_THRESHOLD,
    DEFAULT_QUAKE_MIN_MAGNITUDE,
    DOMAIN,
)
from .coordinator import SourceCoordinator
from .sources.civil_protection import is_at_least

# How long a quake keeps the sensor on after it happened.
QUAKE_WINDOW = timedelta(hours=6)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, SourceCoordinator] = stored["coordinators"]
    options = {**entry.data, **entry.options}
    entities: list[BinarySensorEntity] = []

    if "quakes" in coordinators:
        entities.append(RecentQuakeBinarySensor(coordinators["quakes"], entry, options))
    if "alerts" in coordinators:
        entities.append(AlertBinarySensor(coordinators["alerts"], entry, options))
    if "heat" in coordinators:
        entities.append(HeatBinarySensor(coordinators["heat"], entry, options))

    async_add_entities(entities)


class _BaseBinarySensor(CoordinatorEntity[SourceCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: SourceCoordinator, entry: ConfigEntry, options: dict
    ) -> None:
        super().__init__(coordinator)
        self._options = options
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Allerte Italia",
            manufacturer="Allerte Italia",
        )

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and data is not None and data.available


class RecentQuakeBinarySensor(_BaseBinarySensor):
    """On when a quake above the configured magnitude happened recently."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_name = "Terremoto recente"

    def __init__(self, coordinator, entry, options) -> None:
        super().__init__(coordinator, entry, options)
        self._attr_unique_id = f"{entry.entry_id}_recent_quake"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        if data is None or not data.events:
            return False

        minimum = float(
            self._options.get(CONF_QUAKE_MIN_MAGNITUDE, DEFAULT_QUAKE_MIN_MAGNITUDE)
        )
        cutoff = datetime.now(timezone.utc) - QUAKE_WINDOW

        return any(
            event.magnitude >= minimum and event.occurred_at >= cutoff
            for event in data.events
        )


class AlertBinarySensor(_BaseBinarySensor):
    """On when the Civil Protection level reaches the configured minimum."""

    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_name = "Allerta attiva"

    def __init__(self, coordinator, entry, options) -> None:
        super().__init__(coordinator, entry, options)
        self._attr_unique_id = f"{entry.entry_id}_alert_active"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        if data is None or data.level is None:
            return False
        minimum = self._options.get(CONF_ALERT_MIN_LEVEL, "giallo")
        return is_at_least(data.level, minimum)


class HeatBinarySensor(_BaseBinarySensor):
    """On when the heat index is above the configured threshold."""

    _attr_device_class = BinarySensorDeviceClass.HEAT
    _attr_name = "Allerta caldo"

    def __init__(self, coordinator, entry, options) -> None:
        super().__init__(coordinator, entry, options)
        self._attr_unique_id = f"{entry.entry_id}_heat_alert"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        if data is None or not data.measurements:
            return False
        threshold = float(
            self._options.get(CONF_HEAT_THRESHOLD, DEFAULT_HEAT_THRESHOLD)
        )
        return data.measurements[0].value >= threshold
