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
P2000_SOURCE_ONLINE = "online"
P2000_DEFAULT_SCAN_INTERVAL = 30

SERVICE_SEND_PAGER_MESSAGE = "send_pager_message"
SERVICE_BACKFILL_HISTORY_STAFFING = "backfill_history_staffing"
SERVICE_MARK_INCIDENT_CLOSED = "mark_incident_closed"
SERVICE_REOPEN_INCIDENT = "reopen_incident"

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