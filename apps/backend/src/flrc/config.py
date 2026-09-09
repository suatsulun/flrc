import re
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic_settings import BaseSettings, SettingsConfigDict

_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_PLACEHOLDER_SECRETS = {
    "change-me",
    "change-me-48-random-chars",
    "dev-ops-token",
    "dev-secret-change-me",
}
_LOCAL_SERVICE_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "redis", "db"}


def _is_local_service(hostname: str | None) -> bool:
    return hostname in _LOCAL_SERVICE_HOSTS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    env: str = "dev"
    database_url: str = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc"
    database_url_direct: str = "postgresql+asyncpg://flrc:flrc@localhost:5432/flrc"
    redis_url: str = "redis://localhost:6379/0"
    session_secret: str = "dev-secret-change-me"
    google_client_id: str = ""
    google_client_secret: str = ""
    allowed_google_domain: str = ""
    frontend_origin: str = "http://localhost:5173"
    admin_origin: str = "http://localhost:5174"
    trusted_hosts: str = "localhost,127.0.0.1,test,testserver"
    gateway_secret: str = ""
    session_ttl_seconds: int = 8 * 60 * 60
    max_request_body_bytes: int = 12 * 1024 * 1024
    worker_health_url: str = ""
    # Report-card branding. Normally left empty: the values come from the repo's
    # `branding/` folder, synced into the reports package by `pnpm brand`. Set
    # these only to override that per deployment. See branding/README.md.
    school_name: str = ""
    school_logo_path: str = ""
    # A deployment's branding overlay folder (brand.json, logo.svg). The same
    # folder the web image serves at /branding/, mounted into the API container
    # so reports and screens share one identity (ADR-054).
    school_branding_dir: str = ""
    # Renderer subprocesses used for a report set. 0 auto-sizes from the CPUs
    # this process may actually use (container quota included); set it when a
    # deployment wants a hard cap.
    report_render_workers: int = 0
    ops_token: str = "dev-ops-token"
    e2e_auth_secret: str = ""
    sentry_dsn: str = ""
    # Public demo only (ADR-051): any verified Google account becomes a
    # temporary administrator that lives at most 24 hours. Honoured solely
    # with ENV=demo and refused at startup everywhere else.
    demo_public_login: bool = False
    demo_visitor_limit_per_day: int = 500
    # Nightly demo reset (ADR-052): the demo runs on a Neon child branch that
    # is restored from its pristine parent every local midnight.
    neon_api_key: str = ""
    neon_project_id: str = ""
    neon_demo_branch_id: str = ""
    neon_golden_branch_id: str = ""
    demo_reset_timezone: str = "Europe/Istanbul"
    # School backups (ADR-056): nightly age-encrypted dumps to the school's
    # Shared Drive, a monthly restore test, and academic-year archives.
    backup_dir: str = "/srv/backups"
    backup_age_recipient: str = ""
    backup_age_identity: str = ""
    gdrive_service_account_json: str = ""
    gdrive_backup_folder_id: str = ""
    backup_at: str = "02:30"
    backup_retain: int = 7
    backup_restore_test_day: int = 1
    backup_timezone: str = "Europe/Istanbul"

    def trusted_host_list(self) -> list[str]:
        return [host.strip().casefold() for host in self.trusted_hosts.split(",") if host.strip()]

    def demo_visitors_enabled(self) -> bool:
        return self.env == "demo" and self.demo_public_login

    def demo_reset_enabled(self) -> bool:
        return self.env == "demo" and all(self._neon_settings().values())

    def _neon_settings(self) -> dict[str, str]:
        return {
            "NEON_API_KEY": self.neon_api_key.strip(),
            "NEON_PROJECT_ID": self.neon_project_id.strip(),
            "NEON_DEMO_BRANCH_ID": self.neon_demo_branch_id.strip(),
            "NEON_GOLDEN_BRANCH_ID": self.neon_golden_branch_id.strip(),
        }

    def validate_security_configuration(self) -> None:
        """Refuse to boot with a weakened security boundary."""
        self._validate_demo_configuration()
        if self.env != "school":
            return

        errors: list[str] = []
        origins = {
            "FRONTEND_ORIGIN": self.frontend_origin,
            "ADMIN_ORIGIN": self.admin_origin,
        }
        for name, value in origins.items():
            parsed = urlsplit(value)
            canonical = f"{parsed.scheme}://{parsed.netloc}"
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or value != canonical
            ):
                errors.append(f"{name} must be one exact HTTPS origin without a path")
        if self.frontend_origin != self.admin_origin:
            errors.append("FRONTEND_ORIGIN and ADMIN_ORIGIN must be the same public origin")

        domain = self.allowed_google_domain.casefold().strip().rstrip(".")
        if not _DOMAIN_RE.fullmatch(domain) or domain.startswith("yourschool."):
            errors.append("ALLOWED_GOOGLE_DOMAIN must be the real school Workspace domain")
        if not self.google_client_id.strip().endswith(".apps.googleusercontent.com"):
            errors.append("GOOGLE_CLIENT_ID must be a Google web client id")
        if len(self.google_client_secret.strip()) < 16:
            errors.append("GOOGLE_CLIENT_SECRET is missing or too short")

        for name, value, minimum in (
            ("SESSION_SECRET", self.session_secret, 48),
            ("GATEWAY_SECRET", self.gateway_secret, 32),
            ("OPS_TOKEN", self.ops_token, 32),
        ):
            if len(value) < minimum or value in _PLACEHOLDER_SECRETS or len(set(value)) < 12:
                errors.append(f"{name} must be a non-placeholder random secret ({minimum}+ chars)")
        secrets = {self.session_secret, self.gateway_secret, self.ops_token}
        if len(secrets) != 3:
            errors.append("SESSION_SECRET, GATEWAY_SECRET, and OPS_TOKEN must all be different")
        if self.e2e_auth_secret:
            errors.append("E2E_AUTH_SECRET must be empty in school mode")
        if not 15 * 60 <= self.session_ttl_seconds <= 8 * 60 * 60:
            errors.append("SESSION_TTL_SECONDS must be between 15 minutes and 8 hours")
        if not 1024 <= self.max_request_body_bytes <= 25 * 1024 * 1024:
            errors.append("MAX_REQUEST_BODY_BYTES must be between 1 KiB and 25 MiB")

        redis = urlsplit(self.redis_url)
        if not _is_local_service(redis.hostname) and (
            redis.scheme != "rediss" or not redis.password
        ):
            errors.append("remote REDIS_URL must use rediss:// with credentials")
        for name, value in (
            ("DATABASE_URL", self.database_url),
            ("DATABASE_URL_DIRECT", self.database_url_direct),
        ):
            database = urlsplit(value)
            query = parse_qs(database.query)
            ssl_value = (query.get("ssl") or query.get("sslmode") or [""])[0]
            if not _is_local_service(database.hostname) and ssl_value not in {
                "require",
                "verify-ca",
                "verify-full",
                "true",
            }:
                errors.append(f"remote {name} must require TLS")

        hosts = self.trusted_host_list()
        public_host = urlsplit(self.frontend_origin).hostname
        if not hosts or "*" in hosts:
            errors.append("TRUSTED_HOSTS must be an explicit comma-separated allowlist")
        elif public_host not in hosts:
            errors.append("TRUSTED_HOSTS must include the public frontend hostname")

        if errors:
            raise RuntimeError("Unsafe school configuration: " + "; ".join(errors))

    def _validate_demo_configuration(self) -> None:
        errors: list[str] = []
        neon = self._neon_settings()
        if any(neon.values()):
            if self.env != "demo":
                errors.append("NEON_* demo reset settings require ENV=demo")
            missing = [name for name, value in neon.items() if not value]
            if missing:
                errors.append("incomplete demo reset settings: set " + ", ".join(missing))
            try:
                ZoneInfo(self.demo_reset_timezone)
            except (ZoneInfoNotFoundError, ValueError):
                errors.append("DEMO_RESET_TIMEZONE must be a valid IANA timezone")
            if (
                len(self.ops_token) < 32
                or self.ops_token in _PLACEHOLDER_SECRETS
                or len(set(self.ops_token)) < 12
            ):
                errors.append("OPS_TOKEN must be a non-placeholder random secret (32+ chars)")
        if not self.demo_public_login:
            if errors:
                raise RuntimeError("Unsafe demo configuration: " + "; ".join(errors))
            return
        if self.env != "demo":
            errors.append("DEMO_PUBLIC_LOGIN requires ENV=demo")
        if not all(neon.values()):
            errors.append(
                "DEMO_PUBLIC_LOGIN requires the nightly reset: set NEON_API_KEY, "
                "NEON_PROJECT_ID, NEON_DEMO_BRANCH_ID, and NEON_GOLDEN_BRANCH_ID"
            )
        if not self.allowed_google_domain.strip():
            errors.append("ALLOWED_GOOGLE_DOMAIN must name the synthetic demo school domain")
        if not 15 * 60 <= self.session_ttl_seconds <= 24 * 60 * 60:
            errors.append(
                "SESSION_TTL_SECONDS must be between 15 minutes and 24 hours with DEMO_PUBLIC_LOGIN"
            )
        if self.demo_visitor_limit_per_day < 1:
            errors.append("DEMO_VISITOR_LIMIT_PER_DAY must be at least 1")
        if errors:
            raise RuntimeError("Unsafe demo configuration: " + "; ".join(errors))


settings = Settings()
