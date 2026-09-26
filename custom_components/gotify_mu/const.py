"""Constants for the Gotify MU integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "gotify_mu"

CONF_SERVER_URL = "server_url"
CONF_APP_TOKEN = "app_token"
CONF_CLIENT_TOKEN = "client_token"
CONF_CHANNEL_ID = "channel_id"
CONF_CHANNEL_NAME = "channel_name"
CONF_VERIFY_SSL = "verify_ssl"
CONF_DEFAULT_PRIORITY = "default_priority"
CONF_INBOUND_ENABLED = "inbound_enabled"
CONF_REMOVE_CLIENT_TOKEN = "remove_client_token"

DEFAULT_NAME = "Gotify MU"
DEFAULT_PRIORITY = 5
DEFAULT_VERIFY_SSL = True
DEFAULT_INBOUND_ENABLED = True

PLATFORMS = [Platform.NOTIFY, Platform.EVENT, Platform.BINARY_SENSOR]

SERVICE_SEND = "send"
EVENT_TYPE_MESSAGE = "message"

INTEGRATION_ORIGIN_EXTRA = "homeassistant::gotify_mu"
REQUEST_TIMEOUT_SECONDS = 10
STREAM_RECONNECT_MAX_SECONDS = 60
