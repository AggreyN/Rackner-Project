#!/usr/bin/env bash
# Set a user's display name ("Welcome, {username}") in the Cognito pool.
# The backend mirrors the pool's `name` attribute from ID-token claims on the
# user's next request — no redeploy needed.
#
#   ./scripts/set_cognito_username.sh user@rackner.com "Display Name"
set -euo pipefail
POOL="${COGNITO_USER_POOL_ID:-us-east-2_ayUv1m7Et}"
REGION="${AWS_REGION:-us-east-2}"
EMAIL="${1:?usage: set_cognito_username.sh <email> <display name>}"
NAME="${2:?usage: set_cognito_username.sh <email> <display name>}"
aws cognito-idp admin-update-user-attributes \
  --user-pool-id "$POOL" --region "$REGION" \
  --username "$EMAIL" \
  --user-attributes Name=name,Value="$NAME"
echo "✅ $EMAIL -> \"$NAME\" (takes effect on their next login/token refresh)"
