"""Constants for the FireServiceRota integration."""

DOMAIN = "fireservicerota"

URL_LIST = {
    "www.brandweerrooster.nl": "BrandweerRooster",
    "www.fireservicerota.co.uk": "FireServiceRota",
}
WSS_BWRURL = "wss://{0}/cable?access_token={1}"

DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
DATA_INCIDENT_STORE = "incident_store"
DATA_P2000_MANAGER = "p2000_manager"

CONF_P2000_ENABLED = "p2000_enabled"
CONF_P2000_SOURCE = "p2000_source"
CONF_P2000_SCAN_INTERVAL = "p2000_scan_interval"
CONF_P2000_RTL_TOPIC = "p2000_rtl_topic"
P2000_SOURCE_ONLINE = "online"
P2000_SOURCE_RTL = "rtl"
P2000_SOURCE_BOTH = "both"
P2000_DEFAULT_SCAN_INTERVAL = 30
P2000_DEFAULT_RTL_TOPIC = "homeassistant/sensor/p2000_rtlsdr/2005/attributes"

SERVICE_SEND_PAGER_MESSAGE = "send_pager_message"
SERVICE_BACKFILL_HISTORY_STAFFING = "backfill_history_staffing"
SERVICE_MARK_INCIDENT_CLOSED = "mark_incident_closed"
SERVICE_REOPEN_INCIDENT = "reopen_incident"
SERVICE_SET_STATION_AVAILABILITY = "set_station_availability"

ATTR_ENTRY_ID = "entry_id"
ATTR_INCIDENT_ID = "incident_id"
ATTR_LIMIT = "limit"
ATTR_SCOPE = "scope"
ATTR_PAGER_ID = "pager_id"
ATTR_MESSAGE = "message"
ATTR_ADDRESS = "address"
ATTR_ADDRESSES = "addresses"
ATTR_CONFIRMATION = "confirmation"
ATTR_WEBHOOK_URL = "webhook_url"
ATTR_MEMBERSHIP_ID = "membership_id"
ATTR_STATION_ID = "station_id"
ATTR_AVAILABLE = "available"
ATTR_MODE = "mode"
ATTR_START_TIME = "start_time"
ATTR_END_TIME = "end_time"
ATTR_COMMENTS = "comments"
ATTR_IGNORE_SCHEDULE_WARNINGS = "ignore_schedule_warnings"

AVAILABILITY_MODE_NEXT_SCHEDULE = "next_schedule_change"
AVAILABILITY_MODE_1H = "1h"
AVAILABILITY_MODE_2H = "2h"
AVAILABILITY_MODE_4H = "4h"
AVAILABILITY_MODE_8H = "8h"
AVAILABILITY_MODE_CUSTOM = "custom"
AVAILABILITY_MODE_DURATIONS = {
    AVAILABILITY_MODE_1H: 60,
    AVAILABILITY_MODE_2H: 120,
    AVAILABILITY_MODE_4H: 240,
    AVAILABILITY_MODE_8H: 480,
}
