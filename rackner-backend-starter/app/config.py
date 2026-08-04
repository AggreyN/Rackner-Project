"""Environment-driven settings for the Rackner FDI backend.

One place to read configuration. Secret-bearing values go through
services/secrets.get_secret(): the environment in dev, AWS Secrets Manager in
prod (APP_ENV=prod). Never hard-coded. See `.env.example`.
"""

import os

from dotenv import load_dotenv

load_dotenv()

from app.services.secrets import get_secret  # noqa: E402  (needs dotenv first)

# --- Environment: "dev" reads .env; "prod" reads AWS Secrets Manager ---
APP_ENV = os.getenv("APP_ENV", "dev").lower()

# --- Database ---
DATABASE_URL = get_secret(
    "DATABASE_URL", "postgresql+psycopg://localhost:5432/rackner_fdi"
)

# --- Auth mode: "local" (bcrypt demo) or "cognito" (Amazon Cognito) ---
# Default is "local" so the app runs with no AWS account wired up.
AUTH_MODE = os.getenv("AUTH_MODE", "local").lower()

# --- Local-mode JWT (only used when AUTH_MODE=local) ---
JWT_SECRET = get_secret("JWT_SECRET", "dev-secret-change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.getenv("JWT_EXPIRY_MINUTES", "720"))  # 12h, short-lived

# --- Amazon Cognito (only used when AUTH_MODE=cognito) ---
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
COGNITO_USER_POOL_ID = get_secret("COGNITO_USER_POOL_ID", "")
COGNITO_APP_CLIENT_ID = get_secret("COGNITO_APP_CLIENT_ID", "")  # JWT audience

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

# Pre-generate the analysis in the background when an opportunity detail is
# opened, so GET /analysis is a cache hit instead of a 30s+ synchronous model
# call (SCHEMA_v2 open question 3, option (a)). Costs one model call per
# detail view in bedrock mode — set false to only generate on explicit demand.
ANALYSIS_PREWARM = os.getenv("ANALYSIS_PREWARM", "true").lower() == "true"

# --- External government data ---
# SAM.gov Get Opportunities (data.gov key). Unset → those routes 503 cleanly.
SAM_GOV_API_KEY = get_secret("SAM_GOV_API_KEY", "")

# --- OCR for scanned/image-only PDFs: "off" (default) or "textract" ---
# Two of the five committed sample solicitations are image-only and extract to
# nothing without this. "textract" renders text-less pages locally (PyMuPDF)
# and OCRs them with the SYNCHRONOUS DetectDocumentText API — no S3 bucket, no
# async job polling. Needs AWS credentials with textract:DetectDocumentText.
OCR_MODE = os.getenv("OCR_MODE", "off").lower()

# --- File storage: "local" filesystem or "s3" ---
STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "local").lower()
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "data/uploads")
S3_BUCKET = os.getenv("S3_BUCKET", "")
KMS_KEY_ID = os.getenv("KMS_KEY_ID", "")
