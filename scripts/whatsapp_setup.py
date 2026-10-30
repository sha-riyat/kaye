"""Check WhatsApp credentials from .env and wire the webhook. Never prints secrets.

Usage: uv run python -m scripts.whatsapp_setup https://<modal-url>/webhook

1. Validates the access token and its scopes (app id comes from the token itself).
2. Subscribes the app's webhook to the `messages` field (Meta calls GET /webhook to verify).
3. Subscribes the app to the WhatsApp Business Account so its messages reach the webhook.
4. Prints the phone number and the account health (payment, verification, blocks).
"""

import string
import sys

import httpx

from app.config import get_settings

REQUIRED_SCOPES = {"whatsapp_business_messaging", "whatsapp_business_management"}


def main(callback_url: str) -> int:
    s = get_settings()
    graph = f"{s.whatsapp_graph_base_url}/{s.whatsapp_api_version}"
    user = {"Authorization": f"Bearer {s.whatsapp_access_token}"}
    ok = True

    secret = s.whatsapp_app_secret
    if len(secret) != 32 or not all(c in string.hexdigits for c in secret):
        print("✗ WHATSAPP_APP_SECRET does not look like an app secret (expected 32 hex chars)")
        return 1

    debug = httpx.get(f"{graph}/debug_token", params={"input_token": s.whatsapp_access_token}, headers=user)
    data = debug.json().get("data", {}) if debug.is_success else {}
    app_id = data.get("app_id")
    if not data.get("is_valid") or not app_id:
        print(f"✗ access token invalid: {debug.text[:200]}")
        return 1
    missing = REQUIRED_SCOPES - set(data.get("scopes", []))
    print(f"✓ token valid for app {app_id} ({data.get('type')}), expires_at={data.get('expires_at')}")
    if missing:
        print(f"✗ token is missing scopes: {sorted(missing)}")
        ok = False

    app_token = {"access_token": f"{app_id}|{secret}"}
    sub = httpx.post(
        f"{graph}/{app_id}/subscriptions",
        data={
            "object": "whatsapp_business_account",
            "callback_url": callback_url,
            "verify_token": s.whatsapp_verify_token,
            "fields": "messages",
            **app_token,
        },
        timeout=90,
    )
    if sub.is_success:
        print(f"✓ webhook subscribed: {callback_url} (messages)")
    else:
        print(f"✗ webhook subscription failed (wrong app secret, or verify call failed): {sub.text[:300]}")
        ok = False

    waba = s.whatsapp_business_account_id
    r = httpx.post(f"{graph}/{waba}/subscribed_apps", headers=user)
    print(f"{'✓' if r.is_success else '✗'} app subscribed to WABA {waba}: {r.text[:200]}")
    ok &= r.is_success

    phone = httpx.get(
        f"{graph}/{s.whatsapp_phone_number_id}",
        params={"fields": "display_phone_number,verified_name,status"},
        headers=user,
    )
    print(f"{'✓' if phone.is_success else '✗'} phone number: {phone.text[:200]}")
    ok &= phone.is_success

    health = httpx.get(f"{graph}/{waba}", params={"fields": "health_status"}, headers=user)
    if health.is_success:
        hs = health.json()["health_status"]
        status = hs["can_send_message"]
        print(f"{'✓' if status == 'AVAILABLE' else '!'} can_send_message: {status}")
        for entity in hs["entities"]:
            errors = [(e["error_code"], e["error_description"]) for e in entity.get("errors", [])]
            print(f"    {entity['entity_type']}: {entity['can_send_message']} {errors or ''}")
    else:
        print(f"✗ health check failed: {health.text[:200]}")
        ok = False

    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
