"""Constants for the FireServiceRota integration."""

DOMAIN = "fireservicerota"

URL_LIST = {
    "www.brandweerrooster.nl": "BrandweerRooster",
    "www.fireservicerota.co.uk": "FireServiceRota",
}
WSS_BWRURL = "wss://{0}/cable?access_token={1}"

DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"

SERVICE_SEND_PAGER_MESSAGE = "send_pager_message"

ATTR_ENTRY_ID = "entry_id"
ATTR_PAGER_ID = "pager_id"
ATTR_MESSAGE = "message"
ATTR_ADDRESS = "address"
ATTR_ADDRESSES = "addresses"
ATTR_CONFIRMATION = "confirmation"
ATTR_WEBHOOK_URL = "webhook_url"
