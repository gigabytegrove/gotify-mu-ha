"""Constants for the Monita integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "gotify_mu"  # Legacy Home Assistant config-entry domain retained for in-place upgrades.
SERVICE_DOMAIN = "monita"
LEGACY_SERVICE_DOMAIN = DOMAIN

CONF_SERVER_URL = "server_url"
CONF_APP_TOKEN = "app_token"
CONF_CLIENT_TOKEN = "client_token"
CONF_CHANNEL_ID = "channel_id"
CONF_CHANNEL_IDS = "channel_ids"
CONF_CHANNEL_NAME = "channel_name"
CONF_VERIFY_SSL = "verify_ssl"
CONF_DEFAULT_PRIORITY = "default_priority"
CONF_INBOUND_ENABLED = "inbound_enabled"
CONF_REMOVE_CLIENT_TOKEN = "remove_client_token"

CONF_NATIVE_INTEGRATION_ID = "native_integration_id"
CONF_NATIVE_SECRET = "native_secret"
CONF_NATIVE_EVENT_PATH = "native_event_path"
CONF_NATIVE_WEBHOOK_ID = "native_webhook_id"
CONF_NATIVE_WEBHOOK_URL = "native_webhook_url"
CONF_NATIVE_PAIRING_CODE = "native_pairing_code"
CONF_HOME_ASSISTANT_URL = "home_assistant_url"
CONF_FORCE_LOCAL_REMOVE = "force_local_remove"

DEFAULT_NAME = "Monita"
DEFAULT_PRIORITY = 5
DEFAULT_VERIFY_SSL = True
DEFAULT_INBOUND_ENABLED = True

PLATFORMS = [Platform.NOTIFY, Platform.EVENT, Platform.BINARY_SENSOR]

SERVICE_SEND = "send"
EVENT_TYPE_MESSAGE = "message"

INTEGRATION_ORIGIN_EXTRA = "homeassistant::monita"
LEGACY_INTEGRATION_ORIGIN_EXTRA = "homeassistant::gotify_mu"
REQUEST_TIMEOUT_SECONDS = 10
STREAM_RECONNECT_MAX_SECONDS = 60
