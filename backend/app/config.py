import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Read KEY=value lines from backend/.env into the environment, without overriding what is already set.

    Keys (Pinecone, the answering model) live there so they never go on a command line or into git — .env
    is gitignored. Tests set WARD_NO_DOTENV so a developer's real keys are never used by the suite.
    """
    if os.getenv('WARD_NO_DOTENV') or not path.is_file():
        return
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parents[1] / '.env')


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
    # Which compiler turns English into policies: templates (default, no model needed), hybrid (templates
    # first, the fine-tuned model for sentences they can't read), or llm (the model writes every policy).
    compiler: str = field(default_factory=lambda: _env('WARD_COMPILER', 'templates'))
    # Any OpenAI-compatible server: finetune/scripts/07_serve.py by default; Ollama is
    # http://127.0.0.1:11434/v1 with WARD_LLM_MODEL set to the name given to `ollama create`.
    llm_url: str = field(default_factory=lambda: _env('WARD_LLM_URL', 'http://127.0.0.1:8001/v1'))
    llm_model: str = field(default_factory=lambda: _env('WARD_LLM_MODEL', 'ward-compiler'))
    llm_timeout: float = field(default_factory=lambda: float(_env('WARD_LLM_TIMEOUT', '120')))
    # Cost Explorer bills most accounts in USD; the app speaks rupees. Set to the rate you budget at.
    usd_to_inr: float = field(default_factory=lambda: float(_env('WARD_USD_TO_INR', '83')))
    # Search (RAG over the inventory). Pinecone embeds and stores the resource documents with a hosted
    # model, so nothing is embedded on this machine. Unset: a local keyword index stands in.
    pinecone_api_key: str | None = field(default_factory=lambda: os.getenv('WARD_PINECONE_API_KEY') or None)
    pinecone_index: str = field(default_factory=lambda: _env('WARD_PINECONE_INDEX', 'ward-resources'))
    pinecone_cloud: str = field(default_factory=lambda: _env('WARD_PINECONE_CLOUD', 'aws'))
    pinecone_region: str = field(default_factory=lambda: _env('WARD_PINECONE_REGION', 'us-east-1'))
    pinecone_embed_model: str = field(default_factory=lambda: _env('WARD_PINECONE_EMBED_MODEL', 'llama-text-embed-v2'))
    # Reranking is a second hosted model; off saves quota, on puts the best match first more reliably.
    pinecone_rerank_model: str | None = field(default_factory=lambda: _env('WARD_PINECONE_RERANK_MODEL', 'bge-reranker-v2-m3') or None)
    # The model that writes the answer from what was retrieved. Any OpenAI-compatible chat API.
    # Unset key: the answer is the retrieved resources, listed, with no model involved.
    rag_llm_url: str = field(default_factory=lambda: _env('WARD_RAG_LLM_URL', 'https://api.openai.com/v1'))
    rag_llm_key: str | None = field(default_factory=lambda: os.getenv('WARD_RAG_LLM_KEY') or None)
    rag_llm_model: str = field(default_factory=lambda: _env('WARD_RAG_LLM_MODEL', 'gpt-4o-mini'))
    telegram_token: str | None = field(default_factory=lambda: os.getenv('WARD_TELEGRAM_TOKEN'))
    telegram_chat_id: str | None = field(default_factory=lambda: os.getenv('WARD_TELEGRAM_CHAT_ID'))
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(_env('WARD_CORS_ORIGINS', 'http://localhost:5173').split(','))
    )


settings = Settings()
