#!/usr/bin/env bash
# Safe CDK deploy wrapper for REGAIN.
#
# Guards against the credential-chain bug where an expired SSO session causes
# CDK to silently fall back to a long-lived IAM user in another account
# (205930636302) via ~/.aws/credentials, deploying infrastructure to the
# wrong place.
#
# This script:
#   1. Unsets any leaked AWS_* env vars that would poison the credential chain.
#   2. Refreshes SSO for the regain profile if needed.
#   3. Asserts the caller identity is the correct account (563170906428).
#   4. Runs cdk deploy with AWS_PROFILE=regain and pinned region.
#
# Usage: bash scripts/deploy.sh <StackName> [additional cdk args...]
#   e.g. bash scripts/deploy.sh RegainAgentStack --exclusively

set -euo pipefail

EXPECTED_ACCOUNT="563170906428"
EXPECTED_REGION="us-east-1"
PROFILE="regain"

if [ $# -eq 0 ]; then
  echo "Usage: bash scripts/deploy.sh <StackName> [cdk args...]" >&2
  exit 1
fi

# Strip any leaked credential env vars so the profile is the only source.
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_SECURITY_TOKEN
unset CDK_DEFAULT_ACCOUNT CDK_DEFAULT_REGION

echo "[deploy] Verifying SSO session for profile '$PROFILE'..."
if ! aws sts get-caller-identity --profile "$PROFILE" >/dev/null 2>&1; then
  echo "[deploy] SSO session not active. Launching 'aws sso login --profile $PROFILE'..."
  aws sso login --profile "$PROFILE"
fi

ACTUAL_ACCOUNT="$(aws sts get-caller-identity --profile "$PROFILE" --query 'Account' --output text)"
if [ "$ACTUAL_ACCOUNT" != "$EXPECTED_ACCOUNT" ]; then
  echo "[deploy] FAIL: profile '$PROFILE' resolved to account $ACTUAL_ACCOUNT, expected $EXPECTED_ACCOUNT." >&2
  echo "[deploy] Refusing to deploy." >&2
  exit 1
fi

echo "[deploy] Identity OK: account $ACTUAL_ACCOUNT. Running 'cdk deploy $*'..."

cd "$(dirname "$0")/../infra"

AWS_PROFILE="$PROFILE" AWS_DEFAULT_REGION="$EXPECTED_REGION" \
  npx cdk deploy "$@" --require-approval never
