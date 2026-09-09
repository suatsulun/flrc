from flrc.config import settings
from flrc.modules.administration.names import normalize_email


def allowed_google_domain() -> str:
    return settings.allowed_google_domain.casefold().strip().rstrip(".")


def email_is_in_school_domain(email: str) -> bool:
    domain = allowed_google_domain()
    normalized = normalize_email(email)
    local, separator, email_domain = normalized.rpartition("@")
    return bool(domain and local and separator and email_domain == domain)
