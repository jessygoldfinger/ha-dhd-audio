"""Switch platform for the HA DHD Audio integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_LOGIC_ID,
    CONF_LOGIC_NAME,
    CONF_LOGIC_TYPE,
    CONF_LOGICS,
    DOMAIN,
    LOGIC_TYPE_SWITCH,
)
from .coordinator import DHDCoordinator
from .entity import DHDEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up DHD switches from a config entry."""
    coordinator: DHDCoordinator = hass.data[DOMAIN][entry.entry_id]

    logics: list[dict[str, Any]] = entry.options.get(
        CONF_LOGICS, entry.data.get(CONF_LOGICS, [])
    )

    entities = [
        DHDSwitch(
            coordinator=coordinator,
            logic_id=int(logic[CONF_LOGIC_ID]),
            logic_name=logic[CONF_LOGIC_NAME],
        )
        for logic in logics
        if logic[CONF_LOGIC_TYPE] == LOGIC_TYPE_SWITCH
    ]

    async_add_entities(entities)


class DHDSwitch(DHDEntity, SwitchEntity):
    """Represents a read/write DHD logic state as a switch."""

    def __init__(
        self,
        coordinator: DHDCoordinator,
        logic_id: int,
        logic_name: str,
    ) -> None:
        """Initialise the switch."""
        super().__init__(coordinator, logic_id, logic_name)
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{logic_id}_switch"
        )

    @property
    def is_on(self) -> bool | None:
        """Return True if the logic is active."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._logic_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the logic on."""
        await self.coordinator.client.set_logic_state(self._logic_id, True)
        self.coordinator.data[self._logic_id] = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the logic off."""
        await self.coordinator.client.set_logic_state(self._logic_id, False)
        self.coordinator.data[self._logic_id] = False
        self.async_write_ha_state()
