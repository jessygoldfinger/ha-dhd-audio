"""Base entity for the HA DHD Audio integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DHDCoordinator


class DHDEntity(CoordinatorEntity[DHDCoordinator]):
    """Base class for DHD entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DHDCoordinator,
        logic_id: int,
        logic_name: str,
    ) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self._logic_id = logic_id
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{logic_id}"
        )
        self._attr_name = logic_name

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the DHD mixer."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name=self.coordinator.config_entry.title,
            manufacturer="Jessy Goldfinger",
            model="HA DHD Audio integration",
            configuration_url=(
                f"http://{self.coordinator.client.host}"
            ),
        )

    @property
    def available(self) -> bool:
        """Return True if the entity is available."""
        return (
            super().available
            and self.coordinator.client.connected
            and self._logic_id in (self.coordinator.data or {})
        )
