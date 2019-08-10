"""
Support for interfacing with Avior 4x4 HDMI Matrix Switch.

"""
import logging

import voluptuous as vol

from homeassistant.components.media_player import (
    DOMAIN, PLATFORM_SCHEMA, SUPPORT_SELECT_SOURCE,
    MediaPlayerDevice)
from homeassistant.const import (
    ATTR_ENTITY_ID, CONF_NAME, CONF_PORT, STATE_OFF, STATE_ON)
import homeassistant.helpers.config_validation as cv

# MVK add this requirement again later when fetched from proper location
# REQUIREMENTS = ['pyavior==0.5']

_LOGGER = logging.getLogger(__name__)

SUPPORT_AVIOR = SUPPORT_SELECT_SOURCE

ZONE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
})

SOURCE_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
})

CONF_ZONES = 'zones'
CONF_SOURCES = 'sources'
CONF_TYPE = 'type'

DATA_AVIOR = 'avior'

# set all zones service and attribute constants
SERVICE_SETALLZONES = 'avior_set_all_zones'
ATTR_SOURCE = 'source'

MEDIA_PLAYER_SCHEMA = vol.Schema({
    ATTR_ENTITY_ID: cv.comp_entity_ids,
})

# set all zones takes source string argument
AVIOR_SETALLZONES_SCHEMA = MEDIA_PLAYER_SCHEMA.extend({
    vol.Required(ATTR_SOURCE): cv.string
})

# set EDID mode service and attribute constants
SERVICE_EDID = 'avior_set_edid_mode'
ATTR_MODE = 'mode'

# set edid mode takes mode argument
AVIOR_SETEDIDMODE_SCHEMA = MEDIA_PLAYER_SCHEMA.extend({
    vol.Required(ATTR_MODE): cv.string
})

# Valid zone ids: 1-4
ZONE_IDS = vol.All(vol.Coerce(int), vol.Range(min=1, max=4))

# Valid source ids: 1-4
SOURCE_IDS = vol.All(vol.Coerce(int), vol.Range(min=1, max=4))

PLATFORM_SCHEMA = vol.All(
    PLATFORM_SCHEMA.extend({
        vol.Exclusive(CONF_PORT, CONF_TYPE): cv.string,
        vol.Required(CONF_ZONES): vol.Schema({ZONE_IDS: ZONE_SCHEMA}),
        vol.Required(CONF_SOURCES): vol.Schema({SOURCE_IDS: SOURCE_SCHEMA}),
    }))


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Avior 4x4 HDMI Matrix Switch."""
    if DATA_AVIOR not in hass.data:
        hass.data[DATA_AVIOR] = {}

    port = config.get(CONF_PORT)

# MVK remove dot when importing pyavoir properly
#    from pyavior import get_avior
    from .pyavior import get_avior
    from serial import SerialException

    connection = None
    if port is not None:
        try:
            avior = get_avior(port)
            connection = port
        except SerialException:
            _LOGGER.error("Error connecting to the Avior controller")
            return

    sources = {source_id: extra[CONF_NAME] for source_id, extra
               in config[CONF_SOURCES].items()}

    devices = []
    for zone_id, extra in config[CONF_ZONES].items():
        _LOGGER.info("Adding zone %d - %s", zone_id, extra[CONF_NAME])
        unique_id = "{}-{}".format(connection, zone_id)
        device = AviorZone(avior, sources, zone_id, extra[CONF_NAME])
        hass.data[DATA_AVIOR][unique_id] = device
        devices.append(device)

    add_entities(devices, True)

    def service_handle(service):
        """Handle for set_all_zones and set_edid_mode services."""
        entity_ids = service.data.get(ATTR_ENTITY_ID)
        if entity_ids:
            devices = [device for device in hass.data[DATA_AVIOR].values()
                       if device.entity_id in entity_ids]

        else:
            devices = hass.data[DATA_AVIOR].values()

        #   set_all_zones and set_edid_mode services affect all zones
        #   only need to send message to one zone object
        # for device in devices:
        if len(devices) > 0:
            firstdevice = list(devices)[0]
            if service.service == SERVICE_SETALLZONES:
                source = service.data.get(ATTR_SOURCE)
                firstdevice.set_all_zones(source)
            if service.service == SERVICE_EDID:
                mode = service.data.get(ATTR_MODE)
                firstdevice.set_edid_mode(mode)

    hass.services.register(DOMAIN, SERVICE_SETALLZONES, service_handle,
                           schema=AVIOR_SETALLZONES_SCHEMA)
    hass.services.register(DOMAIN, SERVICE_EDID, service_handle,
                           schema=AVIOR_SETEDIDMODE_SCHEMA)


class AviorZone(MediaPlayerDevice):
    """Representation of a Avior matrix zone."""

    def __init__(self, avior, sources, zone_id, zone_name):
        """Initialize new zone."""
        self._avior = avior
        # dict source_id -> source name
        self._source_id_name = sources
        # dict source name -> source_id
        self._source_name_id = {v: k for k, v in sources.items()}
        # ordered list of all source names
        self._source_names = sorted(self._source_name_id.keys(),
                                    key=lambda v: self._source_name_id[v])
        self._zone_id = zone_id
        self._name = zone_name
        self._state = None
        self._source = None

    @property
    def name(self):
        """Return the name of the zone."""
        return self._name

    @property
    def state(self):
        """Return the state of the zone."""
        return self._state

    @property
    def should_poll(self):
        """Don't poll."""
        return False

    @property
    def assumed_state(self):
        """We can't read the actual state, so assume it matches."""
        return True

    @property
    def supported_features(self):
        """Return flag of media commands that are supported."""
        return SUPPORT_AVIOR

    @property
    def media_title(self):
        """Return the current source as media title."""
        return self._source

    @property
    def source(self):
        """Return the current input source of the device."""
        return self._source

    @property
    def source_list(self):
        """List of available input sources."""
        return self._source_names

    def set_all_zones(self, source):
        """Set all zones to one source."""
        if source not in self._source_name_id:
            _LOGGER.error("Bad source name %s", source)
            return
        idx = self._source_name_id[source]
        _LOGGER.debug("Setting all zones source to %s", idx)
        result = self._avior.set_all_zone_source(idx)
        # if successful
        if "OK" in result:
            self._source = source

    def select_source(self, source):
        """Set input source."""
        if source not in self._source_name_id:
            _LOGGER.error("Bad source name %s", source)
            return
        idx = self._source_name_id[source]
        _LOGGER.debug("Setting zone %d source to %s", self._zone_id, idx)
        result = self._avior.set_zone_source(self._zone_id, idx)
        # if successful
        #   we would prefer to update the state of all zones here
        #   but zones don't share data.  No good solution right now.
        if "OK" in result:
            self._source = source

    def set_edid_mode(self, mode: str):
        """Set EDID mode to port1, remix, or default"""
        if mode not in ['port1', 'remix', 'default']:
            _LOGGER.error("Bad EDID mode")
            return
        result = self._avior.set_edid_mode(mode)
        if "OK" in result:
            pass
        else:
            _LOGGER.error("Set EDID mode error: {}".format(result))
