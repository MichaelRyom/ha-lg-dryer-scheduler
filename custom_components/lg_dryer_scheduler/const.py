"""Constants for the LG Dryer Scheduler integration."""

DOMAIN = "lg_dryer_scheduler"

CONF_PAT = "pat"
CONF_COUNTRY_CODE = "country_code"
CONF_CLIENT_ID = "client_id"
CONF_DEVICE_ID = "device_id"

DEFAULT_POLL_INTERVAL = 30  # seconds

# Operation mode values understood by the integration. The actual list of
# values supported by a given dryer is determined at runtime from its profile.
OP_START = "START"
OP_STOP = "STOP"
OP_POWER_OFF = "POWER_OFF"
OP_WAKE_UP = "WAKE_UP"

# Service names
SERVICE_DELAY_END = "delay_end"
SERVICE_DELAY_START = "delay_start"
SERVICE_REFRESH = "refresh"
SERVICE_GET_ENERGY_USAGE = "get_energy_usage"

# Capability flags exposed via coordinator data
CAP_DELAY_END = "delay_end"
CAP_DELAY_START = "delay_start"
CAP_DELAY_END_MINUTES = "delay_end_minutes"
CAP_DELAY_START_MINUTES = "delay_start_minutes"
CAP_OPERATIONS = "operations"  # set of allowed dryerOperationMode values
CAP_DELAY_END_RANGE = "delay_end_range"  # (min, max) hours
CAP_DELAY_START_RANGE = "delay_start_range"
