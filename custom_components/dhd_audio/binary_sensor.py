"""Binary sensor platform for the HA DHD Audio integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_LOGIC_ID,
    CONF_LOGIC_NAME,
    CONF_LOGIC_TYPE,
    CONF_LOGICS,
    DOMAIN,
    LOGIC_TYPE_SENSOR,
)
from .coordinator import DHDCoordinator
from .entity import DHDEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DHD binary sensors from a config entry."""
    coordinator: DHDCoordinator = hass.data[DOMAIN][entry.entry_id]

    logics: list[dict[str, Any]] = entry.options.get(
        CONF_LOGICS, entry.data.get(CONF_LOGICS, [])
    )

    entities = [
        DHDBinarySensor(
            coordinator=coordinator,
            logic_id=int(logic[CONF_LOGIC_ID]),
            logic_name=logic[CONF_LOGIC_NAME],
        )
        for logic in logics
        if logic[CONF_LOGIC_TYPE] == LOGIC_TYPE_SENSOR
    ]

    async_add_entities(entities)


class DHDBinarySensor(DHDEntity, BinarySensorEntity):
    """Represents a read-only DHD logic state as a binary sensor."""

    def __init__(
        self,
        coordinator: DHDCoordinator,
        logic_id: int,
        logic_name: str,
    ) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, logic_id, logic_name)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{logic_id}_sensor"
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the logic is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._logic_id)
