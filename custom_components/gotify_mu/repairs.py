"""Home Assistant repair issue helpers for Gotify MU."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

NATIVE_BRIDGE_AUTH_ISSUE = "native_bridge_auth_failed"


def native_bridge_issue_id(entry_id: str) -> str:
    """Return the repair issue ID for one config entry."""
    return f"{NATIVE_BRIDGE_AUTH_ISSUE}_{entry_id}"


@callback
def async_create_native_bridge_repair_issue(
    hass: HomeAssistant,
    *,
    entry_id: str,
    name: str,
) -> None:
    """Create an actionable repair issue for a rejected native bridge secret."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        native_bridge_issue_id(entry_id),
        is_fixable=False,
        is_persistent=True,
        issue_domain=DOMAIN,
        severity=ir.IssueSeverity.ERROR,
        translation_key=NATIVE_BRIDGE_AUTH_ISSUE,
        translation_placeholders={"name": name},
        learn_more_url=(
            "https://github.com/gigabytegrove/gotify-mu-ha"
            "#native-gotify-mu-pairing"
        ),
    )


@callback
def async_delete_native_bridge_repair_issue(
    hass: HomeAssistant,
    entry_id: str,
) -> None:
    """Delete a native bridge repair issue if it exists."""
    ir.async_delete_issue(hass, DOMAIN, native_bridge_issue_id(entry_id))
