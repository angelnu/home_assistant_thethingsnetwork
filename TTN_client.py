from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.const import CONTENT_TYPE_JSON, HTTP_NOT_FOUND
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

import asyncio
import aiohttp
import async_timeout
from datetime import timedelta
from aiohttp.hdrs import ACCEPT, AUTHORIZATION

from . import LOGGER
from .const import *

class TTN_client:
    __instances = {}
    @staticmethod
    def createInstance(hass: HomeAssistantType, entry: ConfigEntry):
        """ Static access method. """
        application_id = entry.data[CONF_APP_ID]

        if application_id not in TTN_client.__instances:
            TTN_client.__instances[application_id] = TTN_client(hass, entry)

        return TTN_client.__instances[application_id]

    @staticmethod
    def getInstance(entry: ConfigEntry):
        application_id = entry.data[CONF_APP_ID]
        return TTN_client.__instances[application_id]

    @staticmethod
    async def deleteInstance(hass: HomeAssistantType, entry: ConfigEntry):
        """ Static access method. """
        application_id = entry.data[CONF_APP_ID]

        unload_ok = all(
            await asyncio.gather(
                *[
                    hass.config_entries.async_forward_entry_unload(entry, component)
                    for component in COMPONENT_TYPES
                ]
            )
        )

        if unload_ok and application_id in TTN_client.__instances:
            del TTN_client.__instances[application_id]

        return unload_ok


    def get_device_ids(self):
        ids = []
        for entitiy in self.__entities.values():
            ids.append(entitiy.device_id)
        return list(set(ids))

    def get_field_ids(self):
        ids = []
        for entitiy in self.__entities.values():
            ids.append(entitiy.field_id)
        return list(set(ids))

    def get_options(self):
        return self.__entry.options


    @property
    def hass(self):
        return self.__hass

    @property
    def entry(self):
        return self.__entry


    def __init__(self, hass, entry):

        self.__entry = entry
        self.__hass = hass
        self.__application_id = entry.data[CONF_APP_ID]
        self.__access_key = entry.data[CONF_ACCESS_KEY]
        LOGGER.debug(f"Creating TTN_client with application_id {self.__application_id}")


        self.__entities = {}
        self.__is_connected = False
        self.__first_fetch = True

        #Register for entry update
        self.__update_listener_handler = entry.add_update_listener(TTN_client.__update_listener)

    def __del__(self):
        self.__disconnect()


    async def connect(self):
        #TBD connected

        async def fetch_data_from_ttn():
            await self.fetch_data_from_ttn()

        coordinator = DataUpdateCoordinator(
            self.__hass,
            LOGGER,
            # Name of the data. For logging purposes.
            name="The Things Network",
            update_method=fetch_data_from_ttn,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=API_REFRESH_PERIOD_S),
        )

        # Fetch initial data so we have data when entities subscribe
        await coordinator.async_refresh()

        self.__is_connected = True

    async def fetch_data_from_ttn(self):

        if self.__first_fetch :
            self.__first_fetch = False
            fetch_last = API_FIRST_FETCH_LAST
        else:
            fetch_last = f"{API_REFRESH_PERIOD_S+60}s"

        # Discover entities
        entities = []
        for device_id in await self.storage_api_call("api/v2/devices"):
            device = await self.storage_api_call(f"api/v2/query/{device_id}?last={fetch_last}")
            if not device:
                continue
            device = device[-1]
            for (field_id, value) in device.items():

                unique_id = TtnDataSensor(self, device_id, field_id, value)
                if TtnDataSensor.get_unique_id(device_id, field_id) not in self.__entities:
                    if not value:
                        continue
                    entities.append(unique_id)
                else:
                    devices[unique_id].state = value


        self.add_entities(entities)




    @staticmethod
    async def __update_listener(hass, entry):
        print(entry)
        return await TTN_client.getInstance(entry).__update(hass, entry)

    async def __update(self, hass, entry):
        self.__hass = hass
        self.__entry = entry
        LOGGER.debug(f"BBBB data: {entry.data} options: {entry.options}")
        for entitiy in self.__entities.values():
            await entitiy.refresh_options()

    def __disconnect(self):
        #TBD
        self.__is_connected = False

    def add_entities(self, entities=[]):
        for entity in entities:
            assert (entity.unique_id not in self.__entities)
            self.__entities[entity.unique_id] = entity

        """ Add entities to platforms """
        for component in COMPONENT_TYPES:
            self.__hass.async_add_job(
                self.__hass.config_entries.async_forward_entry_setup(self.__entry, component)
            )

    def add_sensors(self, async_add_entities):
        to_be_added = []
        for entity in self.__entities.values():
            if entity.to_be_added:
                to_be_added.append(entity)
                entity.to_be_added = False
        async_add_entities(to_be_added, True)

    async def remove_all_entities(self):
        for entity in self.__entities.values():
            entity.to_be_removed = True
        return await self.remove_entities()

    async def remove_entitiy(self):
        LOGGER.debug("DELETING remove_entities")
        unload_ok = True
        for (application_id, entitiy) in self.__entities.items():
            if entitiy.to_be_removed:
                unload_ok = await entitiy.async_remove() and unload_ok
        return unload_ok

    async def storage_api_call(self, endpoint):

        url = TTN_DATA_STORAGE_URL.format(app_id=self.__application_id, endpoint=endpoint)
        headers = {ACCEPT: CONTENT_TYPE_JSON, AUTHORIZATION: f"key {self.__access_key}"}

        try:
            session = async_get_clientsession(self.__hass)
            with async_timeout.timeout(DEFAULT_TIMEOUT):
                response = await session.get(url, headers=headers)

        except (asyncio.TimeoutError, aiohttp.ClientError):
            _LOGGER.error("Error while accessing: %s", url)
            return None

        status = response.status

        if status == 401:
            _LOGGER.error("Not authorized for Application ID: %s", app_id)
            return None

        if status == HTTP_NOT_FOUND:
            _LOGGER.error("Application ID is not available: %s", app_id)
            return None

        return await response.json()



class TtnDataSensor(Entity):
    """Representation of a The Things Network Data Storage sensor."""

    @staticmethod
    def get_unique_id(device_id, field_id):
        return f"{device_id}-{field_id}"

    def __init__(
        self, client:TTN_client, device_id, field_id, state=None
    ):
        """Initialize a The Things Network Data Storage sensor."""
        self.__client = client
        self.__device_id = device_id
        self.__field_id = field_id
        self.__state = state

        self.__unique_id = self.get_unique_id(self.__device_id, self.__field_id)
        self.__unit_of_measurement = None
        self.to_be_added = True
        self.to_be_removed = False

        self.__refresh_names()

    @property
    def unique_id(self):
        return self.__unique_id

    @property
    def device_id(self):
        return self.__device_id

    @property
    def device_name(self):
        return self.__device_name

    @property
    def field_id(self):
        return self.__field_id

    @property
    def device_info(self):
        return {
            "identifiers": {
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self.device_id)
            },
            "name": self.device_name
            # "manufacturer": self.light.manufacturername,
            # "model": self.light.productname,
            # "sw_version": self.light.swversion,
            # "via_entitiy": (hue.DOMAIN, self.api.bridgeid),
        }

    @property
    def name(self):
        """Return the name of the sensor."""
        return self.__name

    @property
    def state(self):
        """Return the state of the entity."""
        return self.__state

    @state.setter
    def state(self, value):
        self.__state = value

    @property
    def unit_of_measurement(self):
        """Return the unit this state is expressed in."""
        return self.__unit_of_measurement

    @property
    def entitiy_state_attributes(self):
        """Return the state attributes of the sensor."""
        #if self._ttn_data_storage.data is not None:
        return {
            ATTR_entitiy_ID: self.__entitiy_id,
            #ATTR_RAW: self._state["raw"],
            #ATTR_TIME: self._state["time"],
        }

    #async def async_update(self):
    #    """Get the current state."""
    #    await self._ttn_data_storage.async_update()
    #    self._state = self._ttn_data_storage.data

    def __refresh_names(self):
        device_name = self.__device_id
        field_name = self.__field_id
        options = self.__client.get_options()

        devices = options.get(OPTIONS_CONFIG_DEVICES, {})
        if self.__device_id in devices:
            device_name                = devices[self.__device_id][OPTIONS_CONFIG_DEVICE_ALIAS]

        fields = options.get(OPTIONS_CONFIG_FIELDS, {})
        if self.__field_id in fields:
            field_name                 = fields[self.__field_id][OPTIONS_CONFIG_FIELD_ALIAS]
            self.__unit_of_measurement = fields[self.__field_id][OPTIONS_CONFIG_FIELD_UNIT_MEASUREMENT]

        self.__device_name = device_name
        self.__field_name = field_name
        self.__name      = f"{device_name} {field_name}"

    async def refresh_options(self):
        self.__refresh_names()

        await self.async_update_ha_state()

        device_registry = await dr.async_get_registry(self.__client.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.__client.entry.entry_id,
            **self.device_info
        )