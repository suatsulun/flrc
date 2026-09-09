from typing import Any

import sentry_sdk

from flrc.config import settings

SENSITIVE_KEYS = {
    "full_name",
    "email",
    "school_number",
    "score",
    "scale",
    "text_value",
    "old_score",
    "new_score",
    "old_text",
    "new_text",
    "cookie",
    "set-cookie",
    "authorization",
    "x-flrc-gateway",
    "x-e2e-secret",
    "x-ops-token",
    "neon_api_key",
    "backup_age_identity",
    "gdrive_service_account_json",
    "gateway_secret",
    "session_secret",
    "ops_token",
    "google_client_secret",
    "client_secret",
    "access_token",
    "refresh_token",
    "id_token",
    "url",
    "query_string",
    "data",
}


def scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[Filtered]" if str(key).casefold() in SENSITIVE_KEYS else scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def before_send(event: Any, hint: dict[str, Any]) -> Any:
    del hint
    return scrub(event)


def before_breadcrumb(crumb: Any, hint: dict[str, Any]) -> Any:
    del hint
    return scrub(crumb)


def configure_telemetry() -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=before_send,
        before_breadcrumb=before_breadcrumb,
        traces_sample_rate=0.0,
    )
