"""Environment-driven settings for the Rackner FDI backend.

One place to read configuration. Secrets come from the environment (a local
`.env` file in dev, real env vars in AWS) — never hard-coded. See `.env.example`.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Database ---
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg://localhost:5432/rackner_fdi"
)

# --- Auth mode: "local" (bcrypt demo) or "cognito" (Amazon Cognito) ---
# Default is "local" so the app runs with no AWS account wired up.
AUTH_MODE = os.getenv("AUTH_MODE", "local").lower()

# --- Local-mode JWT (only used when AUTH_MODE=local) ---
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.getenv("JWT_EXPIRY_MINUTES", "720"))  # 12h, short-lived

# --- Amazon Cognito (only used when AUTH_MODE=cognito) ---
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID = os.getenv("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = os.getenv("COGNITO_APP_CLIENT_ID", "")  # JWT audience

# Derived Cognito endpoints (issuer + JWKS) — empty until a pool is configured.
COGNITO_ISSUER = (
    f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{COGNITO_USER_POOL_ID}"
    if COGNITO_USER_POOL_ID
    else ""
)
COGNITO_JWKS_URL = f"{COGNITO_ISSUER}/.well-known/jwks.json" if COGNITO_ISSUER else ""

# --- CORS: the deployed frontend + local dev ---
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

# --- LLM gateway (Kaliza's extract/analyze) ---
# "mock"    → deterministic, schema-valid stand-in; no AWS, no cost. DEFAULT.
# "bedrock" → real Claude on Amazon Bedrock (needs AWS creds + model access).
LLM_MODE = os.getenv("LLM_MODE", "mock").lower()

# Bedrock model id. Use a US cross-region inference profile so inference stays
# in US regions (data-residency for federal work). AWS_REGION is set above.
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
)
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
