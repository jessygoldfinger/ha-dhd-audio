"""Constants for the HA DHD Audio integration."""

DOMAIN = "dhd_audio"

DEFAULT_PORT = 2008

CONF_LOGICS = "logics"
CONF_LOGIC_ID = "logic_id"
CONF_LOGIC_NAME = "name"
CONF_LOGIC_TYPE = "entity_type"

LOGIC_TYPE_SENSOR = "sensor"
LOGIC_TYPE_SWITCH = "switch"

# ECP Protocol constants
ECP_BLOCK_SIZE = 16
ECP_CMD_SET_LOGIC = 0x110E0000
