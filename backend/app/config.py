import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    region: str = field(default_factory=lambda: os.getenv('WARD_REGION', 'ap-south-1'))
    # "sample" serves a built-in demo account; "aws" polls the account with read-only boto3 calls.
    inventory_source: str = field(default_factory=lambda: os.getenv('WARD_INVENTORY_SOURCE', 'sample'))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(os.getenv('WARD_CORS_ORIGINS', 'http://localhost:5173').split(','))
    )


settings = Settings()
