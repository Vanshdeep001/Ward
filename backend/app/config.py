import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    region: str = field(default_factory=lambda: _env('WARD_REGION', 'ap-south-1'))
    # "sample" serves a built-in demo account; "aws" polls the account with read-only boto3 calls.
    inventory_source: str = field(default_factory=lambda: _env('WARD_INVENTORY_SOURCE', 'sample'))
    database_url: str = field(default_factory=lambda: _env('WARD_DATABASE_URL', 'sqlite:///./ward.db'))
    # Cross-account access (SRS §7). The principal each customer's role trusts, and where the
    # CloudFormation template is hosted for one-click onboarding.
    # Unset: Ward trusts whichever identity its own credentials resolve to (see AwsConnection.principal).
    ward_principal: str | None = field(default_factory=lambda: os.getenv('WARD_PRINCIPAL'))
    cfn_template_url: str | None = field(default_factory=lambda: os.getenv('WARD_CFN_TEMPLATE_URL'))
    # Encryption for stored ExternalIds. Unset in development: a key file is generated instead.
    secret_key: str | None = field(default_factory=lambda: os.getenv('WARD_SECRET_KEY'))
    secret_key_file: str = field(default_factory=lambda: _env('WARD_SECRET_KEY_FILE', '.ward-secret'))
    # How often the watcher sweeps. 0 disables the background loop (sweeps can still be triggered by API).
    poll_minutes: float = field(default_factory=lambda: float(_env('WARD_POLL_MINUTES', '15')))
    budget_inr: float = field(default_factory=lambda: float(_env('WARD_BUDGET_INR', '30000')))
    # Cost Explorer bills most accounts in USD; the app speaks rupees. Set to the rate you budget at.
    usd_to_inr: float = field(default_factory=lambda: float(_env('WARD_USD_TO_INR', '83')))
    telegram_token: str | None = field(default_factory=lambda: os.getenv('WARD_TELEGRAM_TOKEN'))
    telegram_chat_id: str | None = field(default_factory=lambda: os.getenv('WARD_TELEGRAM_CHAT_ID'))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(_env('WARD_CORS_ORIGINS', 'http://localhost:5173').split(','))
    )


settings = Settings()
