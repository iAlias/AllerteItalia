"""Sensors: fuel prices, the last quake, the alert level, the heat index."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SourceCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the sensors the enabled sources can feed."""
    stored = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, SourceCoordinator] = stored["coordinators"]
    entities: list[SensorEntity] = []

    fuel = coordinators.get("fuel")
    if fuel is not None and fuel.data is not None:
        for measurement in fuel.data.measurements:
            if measurement.key.startswith("cheapest_"):
                entities.append(CheapestFuelSensor(fuel, entry, measurement.key))
            else:
                entities.append(FuelPriceSensor(fuel, entry, measurement.key))
        if fuel.data.available:
            _remove_stale_fuel_entities(hass, entry, entities)

    quakes = coordinators.get("quakes")
    if quakes is not None:
        entities.append(LastQuakeSensor(quakes, entry))

    alerts = coordinators.get("alerts")
    if alerts is not None:
        entities.append(AlertLevelSensor(alerts, entry))

    heat = coordinators.get("heat")
    if heat is not None:
        entities.append(HeatIndexSensor(heat, entry))

    async_add_entities(entities)


def _remove_stale_fuel_entities(
    hass: HomeAssistant, entry: ConfigEntry, entities: list[SensorEntity]
) -> None:
    """Drop fuel sensors this refresh no longer produces.

    Turning per-station sensors off, or a station leaving the radius, would
    otherwise leave hundreds of restored, unavailable entities behind. Only
    called after a successful refresh, so a feed outage never wipes them.
    """
    prefix = f"{entry.entry_id}_fuel_"
    current = {entity.unique_id for entity in entities}
    registry = er.async_get(hass)
    for registered in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            registered.domain == "sensor"
            and registered.unique_id.startswith(prefix)
            and registered.unique_id not in current
        ):
            registry.async_remove(registered.entity_id)


class _BaseSensor(CoordinatorEntity[SourceCoordinator], SensorEntity):
    """Shared wiring: device identity and availability."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SourceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Allerte Italia",
            manufacturer="Allerte Italia",
        )

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return super().available and data is not None and data.available


class FuelPriceSensor(_BaseSensor):
    """One price at one station, or the cheapest for a fuel.

    Per-station sensors have no state class: with a hundred of them, long-term
    statistics would grow the database for prices nobody charts. The cheapest
    sensor is the one worth keeping statistics for.
    """

    _attr_native_unit_of_measurement = "€/L"
    _attr_icon = "mdi:fuel"

    def __init__(
        self, coordinator: SourceCoordinator, entry: ConfigEntry, key: str
    ) -> None:
        super().__init__(coordinator, entry)
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_fuel_{key}"

    @property
    def _measurement(self):
        data = self.coordinator.data
        if data is None:
            return None
        return next((m for m in data.measurements if m.key == self._key), None)

    @property
    def name(self) -> str:
        measurement = self._measurement
        if measurement is None:
            return self._key
        if self._key.startswith("cheapest_"):
            return f"{measurement.attributes.get('fuel')} più economico"
        station = measurement.attributes.get("station") or "distributore"
        fuel = measurement.attributes.get("fuel") or ""
        service = "self" if measurement.attributes.get("self_service") else "servito"
        return f"{fuel} {service} {station}"

    @property
    def native_value(self) -> float | None:
        measurement = self._measurement
        return measurement.value if measurement else None

    @property
    def extra_state_attributes(self) -> dict:
        measurement = self._measurement
        return dict(measurement.attributes) if measurement else {}


class CheapestFuelSensor(FuelPriceSensor):
    """Lowest price for a fuel, with a ranking of the best stations."""

    _attr_state_class = SensorStateClass.MEASUREMENT


class LastQuakeSensor(_BaseSensor):
    """Magnitude of the most recent earthquake in range."""

    _attr_icon = "mdi:pulse"
    _attr_name = "Ultimo terremoto"

    def __init__(self, coordinator: SourceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_last_quake"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None or not data.events:
            return None
        return data.events[0].magnitude

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None or not data.events:
            return {}
        event = data.events[0]
        return {
            "place": event.description,
            "occurred_at": event.occurred_at.isoformat(),
            **event.attributes,
        }


class AlertLevelSensor(_BaseSensor):
    """Civil Protection alert level for the configured zone."""

    _attr_icon = "mdi:alert"
    _attr_name = "Allerta Protezione Civile"

    def __init__(self, coordinator: SourceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_alert_level"

    @property
    def native_value(self) -> str | None:
        data = self.coordinator.data
        return data.level if data else None

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None or not data.measurements:
            return {}
        return dict(data.measurements[0].attributes)


class HeatIndexSensor(_BaseSensor):
    """Apparent temperature, and the level it corresponds to."""

    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-alert"
    _attr_name = "Indice di calore"

    def __init__(self, coordinator: SourceCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_heat_index"

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None or not data.measurements:
            return None
        return data.measurements[0].value

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        if data is None or not data.measurements:
            return {}
        return dict(data.measurements[0].attributes)
