from homeassistant.helpers.typing import HomeAssistantType
from homeassistant.helpers.entity import Entity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.const import (
    CONTENT_TYPE_JSON,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    STATE_HOME,
    STATE_NOT_HOME,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components import zone

import asyncio
import aiohttp
import async_timeout
from datetime import timedelta
from aiohttp.hdrs import ACCEPT, AUTHORIZATION
import re
import json
from typing import Any, Awaitable, Dict, Iterable, List, Optional

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
        return sorted(list(set(ids)))

    def get_field_ids(self):
        ids = []
        for entitiy in self.__entities.values():
            ids.append(entitiy.field_id)
        return sorted(list(set(ids)))

    def get_options(self):
        return self.__entry.options

    def get_device_options(self, device_id):
        devices = self.get_options().get(OPTIONS_MENU_EDIT_DEVICES, {})
        return devices.get(device_id, {})

    def get_field_options(self, device_id, field_id):
        fields = self.get_options().get(OPTIONS_MENU_EDIT_FIELDS, {})
        field_opts = fields.get(field_id, {})
        if (field_opts.get(OPTIONS_FIELD_DEVICE_SCOPE, device_id) == device_id):
            return field_opts
        else:
            return {}

    def get_first_fetch_last_h(self):
        integration_settings = self.get_options().get(OPTIONS_MENU_EDIT_INTEGRATION, {})
        return integration_settings.get(
            OPTIONS_MENU_INTEGRATION_FIRST_FETCH_TIME_H, DEFAULT_FIRST_FETCH_LAST_H
        )

    def get_refresh_period_s(self):
        integration_settings = self.get_options().get(OPTIONS_MENU_EDIT_INTEGRATION, {})
        return integration_settings.get(
            OPTIONS_MENU_INTEGRATION_REFRESH_TIME_S, DEFAULT_API_REFRESH_PERIOD_S
        )

    @property
    def hass(self):
        return self.__hass

    @property
    def entry(self):
        return self.__entry

    def __init__(self, hass, entry):

        self.__entry = entry
        self.__hass = hass
        self.__hostname = entry.data.get(CONF_HOSTNAME, TTN_API_HOSTNAME)
        self.__application_id = entry.data[CONF_APP_ID]
        self.__access_key = entry.data[CONF_ACCESS_KEY]
        LOGGER.debug(f"Creating TTN_client with application_id {self.__application_id}")

        self.__entities = {}
        self.__is_connected = False
        self.__first_fetch = True
        self.__coordinator = None
        self.__async_add_sensor_entities = None
        self.__async_add_binary_sensor_entities = None
        self.__async_add_device_tracker_entities = None

        # Register for entry update
        self.__update_listener_handler = entry.add_update_listener(
            TTN_client.__update_listener
        )

    def __del__(self):
        self.__disconnect()

    async def connect(self):
        # TBD connected

        # Init components
        for component in COMPONENT_TYPES:
            self.__hass.async_add_job(
                self.__hass.config_entries.async_forward_entry_setup(
                    self.__entry, component
                )
            )

        async def fetch_data_from_ttn():
            await self.__fetch_data_from_ttn()

        # Init global settings
        self.__coordinator = DataUpdateCoordinator(
            self.__hass,
            LOGGER,
            # Name of the data. For logging purposes.
            name="The Things Network",
            update_method=fetch_data_from_ttn,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=self.get_refresh_period_s()),
        )

        # Add dummy listener -> might change later to use it...
        def coordinator_update():
            pass

        self.__coordinator.async_add_listener(coordinator_update)

        # Fetch initial data so we have data when entities subscribe
        await self.__coordinator.async_refresh()

        self.__is_connected = True

    async def __fetch_data_from_ttn(self):

        if self.__first_fetch:
            self.__first_fetch = False
            fetch_last = f"{self.get_first_fetch_last_h()}h"
            LOGGER.info(f"First fetch of tth data: {fetch_last}")
        else:
            #Fetch new measurements since last time (with an extra minute margin)
            fetch_last = f"{self.get_refresh_period_s()+60}s"
            LOGGER.debug(f"Fetch of ttn data: {fetch_last}")

        # Discover entities
        new_entities = {}
        updated_entities = {}
        measurements = await self.storage_api_call(f"?last={fetch_last}")
        async for measurement_raw in measurements:
            #Skip empty lines not containing a result
            if len(measurement_raw) < len("result"):
                continue
            
            #Parse line with json dictionary
            measurement = json.loads(measurement_raw)["result"]

            # Get device_id and uplink_message from measurement
            device_id = measurement["end_device_ids"]["device_id"]
            uplink_message = measurement["uplink_message"]

            # Skip not decoded measurements
            if not "decoded_payload" in uplink_message:
                continue
            
            for (field_id, value) in uplink_message["decoded_payload"].items():

                if value is None:
                    continue
                async def process(field_id, value):
                    unique_id = TtnDataSensor.get_unique_id(device_id, field_id)
                    if unique_id not in self.__entities:
                        # Create
                        if type(value) == bool:
                            # Binary Sensor
                            new_entities[unique_id] = TtnDataBinarySensor(
                                self, device_id, field_id, value
                            )
                        elif type(value) == dict:
                            # GPS
                            new_entities[unique_id] = TtnDataDeviceTracker(
                                self, device_id, field_id, value
                            )
                        else:
                            # Sensor
                            new_entities[unique_id] = TtnDataSensor(
                                self, device_id, field_id, value
                            )
                    else:
                        if unique_id not in updated_entities:
                            # Update value in existing entitity
                            await self.__entities[unique_id].async_set_state(value)
                            updated_entities[unique_id] = self.__entities[unique_id]
                        else:
                            # Ignore multiple measurements - we use first (=latest)
                            pass

                async def process_gps(field_id, value):
                    #position = {}
                    #map_value = map_value_re.findall(value)
                    #for (key,value) in map_value:
                    #    position[key] = float(value)
                    #await process(field_id, position)
                    await process(field_id, value)


                entity_type = self.get_field_options(device_id, field_id).get(OPTIONS_FIELD_ENTITY_TYPE, None)
                if entity_type == OPTIONS_FIELD_ENTITY_TYPE_SENSOR:
                    await process(field_id, value)
                elif entity_type == OPTIONS_FIELD_ENTITY_TYPE_BINARY_SENSOR:
                    await process(field_id, bool(value))
                elif entity_type == OPTIONS_FIELD_ENTITY_TYPE_DEVICE_TRACKER:
                    await process_gps(field_id, value)
                else:
                    if (type(value) is dict):
                        if "gps" in field_id:
                            #GPS
                            await process_gps(field_id, value)
                        else:
                            #Other - such as accelerator
                            for (key, value_item) in value.items():
                                await process(f"{field_id}_{key}", value_item)
                    else:
                        # Regular sensor
                        await process(field_id, value)

        self.__add_entities(new_entities.values())

    @staticmethod
    async def __update_listener(hass, entry):
        return await TTN_client.getInstance(entry).__update(hass, entry)

    async def __update(self, hass, entry):
        self.__hass = hass
        self.__entry = entry

        if self.__coordinator:
            self.__coordinator.update_interval = timedelta(seconds=self.get_refresh_period_s())

        for entitiy in self.__entities.values():
            await entitiy.refresh_options()

        # Refresh data
        self.__first_fetch = True
        await self.__coordinator.async_request_refresh()

    def __disconnect(self):
        # TBD
        self.__is_connected = False

    def __add_entities(self, entities=[]):

        for entity in entities:
            assert entity.unique_id not in self.__entities
            self.__entities[entity.unique_id] = entity

        self.add_entities()

    def add_entities(self,
                     async_add_sensor_entities=None,
                     async_add_binary_sensor_entities=None,
                     async_add_device_tracker_entities=None):
        if async_add_sensor_entities:
            # Remember handling for dynamic adds later
            self.__async_add_sensor_entities = async_add_sensor_entities

        if async_add_binary_sensor_entities:
            # Remember handling for dynamic adds later
            self.__async_add_binary_sensor_entities = async_add_binary_sensor_entities

        if async_add_device_tracker_entities:
            # Remember handling for dynamic adds later
            self.__async_add_device_tracker_entities = async_add_device_tracker_entities

        sensors_to_be_added = []
        binary_sensors_to_be_added = []
        device_tracker_to_be_added = []
        for entity in self.__entities.values():
            if entity.to_be_added:
                if self.__async_add_sensor_entities       and (type(entity) == TtnDataSensor):
                        sensors_to_be_added.append(entity)
                        entity.to_be_added = False
                if self.__async_add_binary_sensor_entities       and (type(entity) == TtnDataBinarySensor):
                        binary_sensors_to_be_added.append(entity)
                        entity.to_be_added = False
                if self.__async_add_device_tracker_entities and (type(entity) == TtnDataDeviceTracker):
                    device_tracker_to_be_added.append(entity)
                    entity.to_be_added = False

        if self.__async_add_sensor_entities:
            self.__async_add_sensor_entities(sensors_to_be_added, True)

        if self.__async_add_binary_sensor_entities:
            self.__async_add_binary_sensor_entities(binary_sensors_to_be_added, True)

        if self.__async_add_device_tracker_entities:
            self.__async_add_device_tracker_entities(device_tracker_to_be_added, True)

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

    async def storage_api_call(self, options):

        url = TTN_DATA_STORAGE_URL.format(
            app_id=self.__application_id, hostname=self.__hostname, options=options
        )
        LOGGER.info(f"URL: {url}")
        headers = {ACCEPT: "text/event-stream", AUTHORIZATION: f"Bearer {self.__access_key}"}

        try:
            session = async_get_clientsession(self.__hass)
            with async_timeout.timeout(DEFAULT_TIMEOUT):
                response = await session.get(url, headers=headers)

        except (asyncio.TimeoutError, aiohttp.ClientError):
            LOGGER.error("Error while accessing: %s", url)
            return None

        status = response.status

        if status == 401:
            LOGGER.error("Not authorized for Application ID: %s", self.__application_id)
            return None

        if status == 404:
            LOGGER.error("Application ID is not available: %s", self.__application_id)
            return None
        
        return response.content


class TtnDataEntity(Entity):
    """Representation of a The Things Network Data Storage sensor."""

    @staticmethod
    def get_unique_id(device_id, field_id):
        return f"{device_id}_{field_id}"

    def __init__(self, client: TTN_client, device_id, field_id, state=None):
        """Initialize a The Things Network Data Storage sensor."""
        self.__client = client
        self.__device_id = device_id
        self.__field_id = field_id
        self._state = state

        self.__unique_id = self.get_unique_id(self.__device_id, self.__field_id)
        self.to_be_added = True
        self.to_be_removed = False

        #Values from options
        self._unit_of_measurement = None
        self.__device_class = None
        self.__icon = None
        self.__picture = None
        self.__supported_features = None
        self.__context_recent_time_s = 5

        self.__refresh_names()

    #---------------
    # standard Entity propertiess
    #---------------
    @property
    def should_poll(self) -> bool:
        """Return True if entity has to be polled for state.

        False if entity pushes its state to HA.
        """
        return False

    @property
    def unique_id(self) -> Optional[str]:
        """Return a unique ID."""
        return self.__unique_id

    @property
    def name(self) -> Optional[str]:
        """Return the name of the entity."""
        return self.__name

    @property
    def state(self):
        """Return the state of the entity."""
        return self._state

    @property
    def entitiy_state_attributes(self):
        """Return the state attributes of the sensor."""
        # if self._ttn_data_storage.data is not None:
        return {
            ATTR_entitiy_ID: self.__entitiy_id,
            # ATTR_RAW: self._state["raw"],
            # ATTR_TIME: self._state["time"],
        }

    @property
    def capability_attributes(self) -> Optional[Dict[str, Any]]:
        """Return the capability attributes.

        Attributes that explain the capabilities of an entity.

        Implemented by component base class. Convention for attribute names
        is lowercase snake_case.
        """
        return {}

    @property
    def state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return the state attributes.

        Implemented by component base class. Convention for attribute names
        is lowercase snake_case.
        """
        return {}

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        """Return device specific state attributes.

        Implemented by platform classes. Convention for attribute names
        is lowercase snake_case.
        """
        return {}

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        """Return device specific attributes.

        Implemented by platform classes.
        """

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
    def device_class(self) -> Optional[str]:
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self.__device_class

    @property
    def icon(self) -> Optional[str]:
        """Return the icon to use in the frontend, if any."""
        return self.__icon

    @property
    def entity_picture(self) -> Optional[str]:
        """Return the entity picture to use in the frontend, if any."""
        return self.__picture

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return True

    @property
    def assumed_state(self) -> bool:
        """Return True if unable to access real state of the entity."""
        return False

    @property
    def force_update(self) -> bool:
        """Return True if state updates should be forced.

        If True, a state change will be triggered anytime the state property is
        updated, not just when the value changes.
        """
        return False

    @property
    def supported_features(self) -> Optional[int]:
        """Flag supported features."""
        return self.__supported_features

    @property
    def context_recent_time(self) -> timedelta:
        """Time that a context is considered recent."""
        return timedelta(seconds=self.__context_recent_time_s)

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return True


    #---------------
    # TTN integration additional methods
    #---------------
    @property
    def device_id(self):
        return self.__device_id

    @property
    def device_name(self):
        return self.__device_name

    @property
    def field_id(self):
        return self.__field_id

    async def async_set_state(self, value):
        self._state = value
        await self.async_update_ha_state()

    def __refresh_names(self):
        device_name = self.__device_id
        field_name = self.__field_id

        #Device options
        device_opts = self.__client.get_device_options(self.__device_id)
        device_name                  = device_opts.get(OPTIONS_DEVICE_NAME,                device_name)

        #Field options
        field_opts = self.__client.get_field_options(self.__device_id, self.__field_id)
        field_name                   = field_opts.get(OPTIONS_FIELD_NAME,                  field_name)
        self._unit_of_measurement    = field_opts.get(OPTIONS_FIELD_UNIT_MEASUREMENT,      None)
        self.__device_class          = field_opts.get(OPTIONS_FIELD_DEVICE_CLASS,          None)
        self.__icon                  = field_opts.get(OPTIONS_FIELD_ICON,                  None)
        self.__picture               = field_opts.get(OPTIONS_FIELD_PICTURE,               None)
        self.__supported_features    = field_opts.get(OPTIONS_FIELD_SUPPORTED_FEATURES,    None)
        self.__context_recent_time_s = field_opts.get(OPTIONS_FIELD_CONTEXT_RECENT_TIME_S, 5)

        self.__device_name = device_name
        self.__field_name = field_name
        self.__name = f"{device_name} {field_name}"

    async def refresh_options(self):
        self.__refresh_names()

        await self.async_update_ha_state()

        device_registry = await dr.async_get_registry(self.__client.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.__client.entry.entry_id, **self.device_info
        )

class TtnDataSensor(TtnDataEntity):
    @property
    def unit_of_measurement(self) -> Optional[str]:
        """Return the unit of measurement of this entity, if any."""
        return self._unit_of_measurement


class TtnDataBinarySensor(TtnDataEntity):
    """Represent a binary sensor."""

    @property
    def is_on(self):
        """Return true if the binary sensor is on."""
        return bool(self._state)

    @property
    def state(self):
        """Return the state of the binary sensor."""
        return STATE_ON if self.is_on else STATE_OFF


class TtnDataDeviceTracker(TtnDataSensor):

    @property
    def location_accuracy(self):
        """Return the location accuracy of the device.

        Value in meters.
        """
        return 0

    @property
    def location_name(self) -> str:
        """Return a location name for the current location of the device."""
        return None

    @property
    def latitude(self) -> float:
        """Return latitude value of the device."""
        return self._state["latitude"]

    @property
    def longitude(self) -> float:
        """Return longitude value of the device."""
        return self._state["longitude"]

    @property
    def altitude(self) -> float:
        """Return altitude value of the device."""
        return self._state["altitude"]

    @property
    def state(self):
        """Return the state of the device."""
        if self.location_name:
            return self.location_name

        if self._state["latitude"] > 0:
            zone_state = zone.async_active_zone(
                self.hass, self.latitude, self.longitude, self.location_accuracy
            )
            if zone_state is None:
                state = STATE_NOT_HOME
            elif zone_state.entity_id == zone.ENTITY_ID_HOME:
                state = STATE_HOME
            else:
                state = zone_state.name
            return state

        return None

    @property
    def state_attributes(self):
        """Return the device state attributes."""
        attr = {}
        attr.update(super().state_attributes)
        if self.latitude is not None:
            attr[ATTR_LATITUDE] = self.latitude
            attr[ATTR_LONGITUDE] = self.longitude
            attr[ATTR_GPS_ACCURACY] = self.location_accuracy
            attr["altitude"] = self.altitude

        return attr

    @property
    def entitiy_state_attributes(self):
        """Return the state attributes of the sensor."""
        # if self._ttn_data_storage.data is not None:
        return {
            ATTR_entitiy_ID: self.__entitiy_id,
            # ATTR_RAW: self._state["raw"],
            # ATTR_TIME: self._state["time"],
        }

