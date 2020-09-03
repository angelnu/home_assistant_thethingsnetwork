from collections import OrderedDict
import voluptuous as vol
import copy
from homeassistant import data_entry_flow
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry

from .const import *
from .TTN_client import TTN_client


@config_entries.HANDLERS.register(DOMAIN)
class FlowHandler(config_entries.ConfigFlow):
    """Handle a config flow."""

    VERSION = 1

    @property
    def schema(self):
        """Return current schema."""
        channel = vol.Schema({"unit": str, "name": str})

        return vol.Schema(
            {
                vol.Required(CONF_APP_ID): str,
                vol.Required(CONF_ACCESS_KEY): str
            }
        )

    async def _create_entry(self, data):
        """Register new entry."""
        app_id = data[CONF_APP_ID]
        if not self.unique_id:
            await self.async_set_unique_id(app_id)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=app_id,
            data=data,
        )

    async def async_step_user(self, user_input=None):
        """User initiated config flow."""
        if user_input is not None:
            return await self._create_entry(user_input)

        return self.async_show_form(step_id="user", data_schema=self.schema)

    async def async_step_import(self, user_input):
        """Import a config entry."""
        return await self._create_entry(user_input)

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle MQTT options."""

    def __init__(self, entry: ConfigEntry):
        """Initialize MQTT options flow."""
        self.entry = entry
        self.options = copy.deepcopy(dict(entry.options))
        self.client = TTN_client.getInstance(entry)

    def get_device_ids(self):
        return self.client.get_device_ids()

    def get_field_ids(self):
        return self.client.get_field_ids()

    def _create_entry(self, title=""):
        """Register new entry."""
        # self.hass.config_entries.async_update_entry(
        #             self.entry, data=self.options
        #         )
        return self.async_create_entry(
            title=title,
            data=self.options
        )

    async def async_step_init(self, user_input=None):

        if user_input is not None:
            selected_next_step = user_input[OPTIONS_SELECTED_MENU]
            if selected_next_step == OPTIONS_MENU_EDIT_DEVICES:
                return await self.async_step_device_select()
            if selected_next_step == OPTIONS_MENU_EDIT_FIELDS:
                return await self.async_step_field_select()

        fields = OrderedDict()
        fields[vol.Required(OPTIONS_SELECTED_MENU, default=OPTIONS_MENU_EDIT_DEVICES)] = vol.In([OPTIONS_MENU_EDIT_DEVICES, OPTIONS_MENU_EDIT_FIELDS])

        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))

    async def async_step_device_select(self, user_input=None):
        """Device selection form."""
        if user_input is not None:
            self.selected_device = user_input[OPTIONS_SELECTED_DEVICE]
            return await self.async_step_device_edit()

        #Get detected devices
        device_names = self.get_device_ids()

        if len(device_names) == 0:
            return self.async_abort(reason="no_devices")
        fields = OrderedDict()
        fields[vol.Required(OPTIONS_SELECTED_DEVICE, default=device_names[0])] = vol.In(device_names)
        return self.async_show_form(
            step_id="device_select",
            data_schema=vol.Schema(fields)
        )

    async def async_step_device_edit(self, user_input=None):
        """Device selection form."""
        if user_input is not None:
            #Update options
            self.options[OPTIONS_CONFIG_DEVICES][self.selected_device][OPTIONS_CONFIG_DEVICE_ALIAS] = user_input[OPTIONS_DEVICE_FRIENDLY_NAME]

            #Return update
            return self._create_entry(self.options)

        #Get config for device
        self.options.setdefault(OPTIONS_CONFIG_DEVICES, {})
        self.options[OPTIONS_CONFIG_DEVICES].setdefault(self.selected_device, {})
        self.options[OPTIONS_CONFIG_DEVICES][self.selected_device].setdefault(OPTIONS_CONFIG_DEVICE_ALIAS, self.selected_device)

        friendly_name = self.options[OPTIONS_CONFIG_DEVICES][self.selected_device][OPTIONS_CONFIG_DEVICE_ALIAS]


        fields = OrderedDict()
        fields[vol.Required(OPTIONS_DEVICE_FRIENDLY_NAME, default=friendly_name)] = str
        return self.async_show_form(
            step_id="device_edit",
            description_placeholders={OPTIONS_SELECTED_DEVICE: self.selected_device},
            data_schema=vol.Schema(fields)
        )

    async def async_step_field_select(self, user_input=None):
        """Device selection form."""
        if user_input is not None:
            self.selected_field = user_input[OPTIONS_SELECTED_FIELD]
            return await self.async_step_field_edit()

        #Get detected devices
        field_ids = self.get_field_ids()

        if len(field_ids) == 0:
            return self.async_abort(reason="no_fields")
        fields = OrderedDict()
        fields[vol.Required(OPTIONS_SELECTED_FIELD, default=field_ids[0])] = vol.In(field_ids)
        return self.async_show_form(
            step_id="field_select",
            data_schema=vol.Schema(fields)
        )

    async def async_step_field_edit(self, user_input=None):
        """Device selection form."""
        if user_input is not None:
            #Update options
            field_options = self.options[OPTIONS_CONFIG_FIELDS][self.selected_field]
            field_options[OPTIONS_CONFIG_FIELD_ALIAS]     = user_input[OPTIONS_FIELD_FRIENDLY_NAME]
            field_options[OPTIONS_FIELD_UNIT_MEASUREMENT] = user_input[OPTIONS_CONFIG_FIELD_UNIT_MEASUREMENT]
            field_options[OPTIONS_FIELD_DEVICE_SCOPE]     = user_input[OPTIONS_CONFIG_FIELD_DEVICE_SCOPE]

            if (field_options[OPTIONS_FIELD_DEVICE_SCOPE] == OPTIONS_CONFIG_FIELD_DEVICE_SCOPE_GLOBAL):
                del field_options[OPTIONS_FIELD_DEVICE_SCOPE]

            #Return update
            return self._create_entry(self.options)

        #Get config for field
        field_options = self.options.setdefault(OPTIONS_CONFIG_FIELDS, {}).setdefault(self.selected_field, {})
        friendly_name       = field_options.setdefault(OPTIONS_CONFIG_FIELD_ALIAS, self.selected_field)
        unit_of_measurement = field_options.setdefault(OPTIONS_FIELD_UNIT_MEASUREMENT, "C")
        field_device_scope  = field_options.setdefault(OPTIONS_FIELD_DEVICE_SCOPE, OPTIONS_CONFIG_FIELD_DEVICE_SCOPE_GLOBAL)

        fields = OrderedDict()
        fields[vol.Required(OPTIONS_FIELD_FRIENDLY_NAME, default=friendly_name)] = str
        fields[vol.Required(OPTIONS_CONFIG_FIELD_UNIT_MEASUREMENT, default=unit_of_measurement)] = str
        fields[vol.Required(OPTIONS_CONFIG_FIELD_DEVICE_SCOPE, default=field_device_scope)] = vol.In([OPTIONS_CONFIG_FIELD_DEVICE_SCOPE_GLOBAL]+self.get_device_ids())
        return self.async_show_form(
            step_id="field_edit",
            description_placeholders={OPTIONS_SELECTED_FIELD: self.selected_field},
            data_schema=vol.Schema(fields)
        )

async def async_step_init(self, user_input=None):
    """Manage the options."""
    if user_input is not None:
        return self.async_create_entry(title="", data=user_input)

    fields = OrderedDict()
    fields["prueba"] = vol.In(["foooooooo", "dos"])
    fields[vol.Optional("prueba2")] = cv.multi_select(
        {"default": "Default", "other": "Other"}
    )
    fields[vol.Optional("birth_topic", description={"suggested_value": "uno"})] = str
    fields[vol.Optional("birth_payload", description={"suggested_value": "otro"})] = str

    return self.async_show_form(step_id="init", data_schema=fields)
