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
            {vol.Required(CONF_APP_ID): str, vol.Required(CONF_ACCESS_KEY): str}
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
    """Handle integration options."""

    def __init__(self, entry: ConfigEntry):
        """Initialize options flow."""
        self.entry = entry
        self.options = copy.deepcopy(dict(entry.options))
        self.client = TTN_client.getInstance(entry)

    def get_device_ids(self):
        return self.client.get_device_ids()

    def get_field_ids(self):
        return self.client.get_field_ids()

    def _update_entry(self, title="", data=None):
        """Update entry."""
        if data:
            self.hass.config_entries.async_update_entry(self.entry, data=data)
        return self.async_create_entry(title=title, data=self.options)

    async def async_step_init(self, user_input=None):
        """ Menu selection form."""
        if user_input is not None:
            # Go to next flow step
            selected_next_step = user_input[OPTIONS_SELECTED_MENU]
            if selected_next_step == OPTIONS_MENU_EDIT_INTEGRATION:
                return await self.async_step_integration_settings()
            if selected_next_step == OPTIONS_MENU_EDIT_DEVICES:
                return await self.async_step_device_select()
            if selected_next_step == OPTIONS_MENU_EDIT_FIELDS:
                return await self.async_step_field_select()

        # Return form
        fields = OrderedDict()
        menu_options = vol.In(
            [
                OPTIONS_MENU_EDIT_INTEGRATION,
                OPTIONS_MENU_EDIT_DEVICES,
                OPTIONS_MENU_EDIT_FIELDS,
            ]
        )
        fields[
            vol.Required(OPTIONS_SELECTED_MENU, default=OPTIONS_MENU_EDIT_INTEGRATION)
        ] = menu_options
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))

    async def async_step_integration_settings(self, user_input=None):
        """Global settings form."""

        # Get global settings
        integration_settings = self.options.setdefault(
            OPTIONS_MENU_EDIT_INTEGRATION, {}
        )

        if user_input is not None:
            # Update options
            integration_settings[OPTIONS_MENU_INTEGRATION_REFRESH_TIME_S] = user_input[
                OPTIONS_MENU_INTEGRATION_REFRESH_TIME_S
            ]

            # Return update
            return self._update_entry(self.options)

        # Get config for device
        refresh_time_s = integration_settings.setdefault(
            OPTIONS_MENU_INTEGRATION_REFRESH_TIME_S, DEFAULT_API_REFRESH_PERIOD_S
        )

        # Return form
        fields = OrderedDict()
        fields[
            vol.Required(
                OPTIONS_MENU_INTEGRATION_REFRESH_TIME_S, default=refresh_time_s
            )
        ] = int
        return self.async_show_form(
            step_id="integration_settings",
            data_schema=vol.Schema(fields),
        )

    async def async_step_device_select(self, user_input=None):
        """Device selection form."""

        if user_input is not None:
            # Go to next flow step
            self.selected_device = user_input[OPTIONS_SELECTED_DEVICE]
            return await self.async_step_device_edit()

        # Get detected devices
        device_names = self.get_device_ids()

        # Abort if no devices available yet
        if len(device_names) == 0:
            return self.async_abort(reason="no_devices")

        # Return form
        fields = OrderedDict()
        fields[vol.Required(OPTIONS_SELECTED_DEVICE, default=device_names[0])] = vol.In(
            device_names
        )
        return self.async_show_form(
            step_id="device_select", data_schema=vol.Schema(fields)
        )

    async def async_step_device_edit(self, user_input=None):
        """Device edit form."""
        # Get device options
        device_options = self.options.setdefault(
            OPTIONS_MENU_EDIT_DEVICES, {}
        ).setdefault(self.selected_device, {})

        if user_input is not None:
            # Update options
            device_options[OPTIONS_DEVICE_NAME] = user_input[OPTIONS_DEVICE_NAME]

            # Return update
            return self._update_entry(self.options)

        # Get config for device
        name = device_options.setdefault(OPTIONS_DEVICE_NAME, self.selected_device)

        # Return form
        fields = OrderedDict()
        fields[vol.Required(OPTIONS_DEVICE_NAME, default=name)] = str
        return self.async_show_form(
            step_id="device_edit",
            description_placeholders={OPTIONS_SELECTED_DEVICE: self.selected_device},
            data_schema=vol.Schema(fields),
        )

    async def async_step_field_select(self, user_input=None):
        """Field selection form."""

        if user_input is not None:
            # Go to next step
            self.selected_field = user_input[OPTIONS_SELECTED_FIELD]
            return await self.async_step_field_edit()

        # Get detected devices
        field_ids = self.get_field_ids()

        # Abort if no devices found yet
        if len(field_ids) == 0:
            return self.async_abort(reason="no_fields")

        # Return form
        fields = OrderedDict()
        fields[vol.Required(OPTIONS_SELECTED_FIELD, default=field_ids[0])] = vol.In(
            field_ids
        )
        return self.async_show_form(
            step_id="field_select", data_schema=vol.Schema(fields)
        )

    async def async_step_field_edit(self, user_input=None):
        """Field edit form."""

        # Get field options
        field_options = self.options.setdefault(OPTIONS_MENU_EDIT_FIELDS, {}).setdefault(self.selected_field, {})

        if user_input is not None:
            #Set empty
            field_options = self.options[OPTIONS_MENU_EDIT_FIELDS][self.selected_field] = {}

            # Update options
            field_options[OPTIONS_FIELD_NAME]                  = user_input.get(OPTIONS_FIELD_NAME)
            field_options[OPTIONS_FIELD_DEVICE_SCOPE]          = user_input.get(OPTIONS_FIELD_DEVICE_SCOPE)
            field_options[OPTIONS_FIELD_UNIT_MEASUREMENT]      = user_input.get(OPTIONS_FIELD_UNIT_MEASUREMENT, None)
            field_options[OPTIONS_FIELD_DEVICE_CLASS]          = user_input.get(OPTIONS_FIELD_DEVICE_CLASS, None)
            field_options[OPTIONS_FIELD_ICON]                  = user_input.get(OPTIONS_FIELD_ICON, None)
            field_options[OPTIONS_FIELD_PICTURE]               = user_input.get(OPTIONS_FIELD_PICTURE, None)
            field_options[OPTIONS_FIELD_SUPPORTED_FEATURES]    = user_input.get(OPTIONS_FIELD_SUPPORTED_FEATURES, None)
            field_options[OPTIONS_FIELD_CONTEXT_RECENT_TIME_S] = user_input.get(OPTIONS_FIELD_CONTEXT_RECENT_TIME_S)

            # For global scope remove option
            if (field_options[OPTIONS_FIELD_DEVICE_SCOPE] == OPTIONS_FIELD_DEVICE_SCOPE_GLOBAL):
                del field_options[OPTIONS_FIELD_DEVICE_SCOPE]

            # Return update
            return self._update_entry(self.options)

        # Get options
        name                  = field_options.setdefault(OPTIONS_FIELD_NAME,                  self.selected_field)
        device_scope          = field_options.setdefault(OPTIONS_FIELD_DEVICE_SCOPE,          OPTIONS_FIELD_DEVICE_SCOPE_GLOBAL)
        unit_of_measurement   = field_options.setdefault(OPTIONS_FIELD_UNIT_MEASUREMENT,      None)
        device_class          = field_options.setdefault(OPTIONS_FIELD_DEVICE_CLASS,          None)
        icon                  = field_options.setdefault(OPTIONS_FIELD_ICON,                  None)
        picture               = field_options.setdefault(OPTIONS_FIELD_PICTURE,               None)
        supported_features    = field_options.setdefault(OPTIONS_FIELD_SUPPORTED_FEATURES,    None)
        context_recent_time_s = field_options.setdefault(OPTIONS_FIELD_CONTEXT_RECENT_TIME_S, 5)

        device_options      = vol.In([OPTIONS_FIELD_DEVICE_SCOPE_GLOBAL] + self.get_device_ids())

        # Return form
        fields = OrderedDict()
        fields[vol.Required(OPTIONS_FIELD_NAME,                  default=name                                         )] = str
        fields[vol.Required(OPTIONS_FIELD_DEVICE_SCOPE,          default=device_scope                                 )] = device_options
        fields[vol.Optional(OPTIONS_FIELD_UNIT_MEASUREMENT,      description={"suggested_value": unit_of_measurement} )] = str
        fields[vol.Optional(OPTIONS_FIELD_DEVICE_CLASS,          description={"suggested_value": device_class}        )] = str
        fields[vol.Optional(OPTIONS_FIELD_ICON,                  description={"suggested_value": icon}                )] = str
        fields[vol.Optional(OPTIONS_FIELD_PICTURE,               description={"suggested_value": picture}             )] = str
        fields[vol.Optional(OPTIONS_FIELD_SUPPORTED_FEATURES,    description={"suggested_value": supported_features}  )] = str
        fields[vol.Required(OPTIONS_FIELD_CONTEXT_RECENT_TIME_S, default=context_recent_time_s                        )] = int
        return self.async_show_form(
            step_id="field_edit",
            description_placeholders={OPTIONS_SELECTED_FIELD: self.selected_field},
            data_schema=vol.Schema(fields),
        )
