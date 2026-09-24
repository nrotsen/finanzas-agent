# Deploy to AWS

Deploy once the agent works locally (`python -m scripts.chat_cli`).

## Prerequisites

- AWS CLI configured for the target account
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
- Python 3.12 and `make` (SAM builds each function through the repo's `Makefile`)

The examples use `us-east-2`. Any region works; keep it consistent.

## 1. Create the secrets

The Lambdas don't read `.env`. On cold start they hydrate their configuration from Secrets Manager (`src/config/secrets.py`). The IAM policy only allows reading `finanzas-agent/*`.

| Secret | Required | Content |
|---|---|---|
| `finanzas-agent/anthropic-api-key` | yes | Anthropic API key |
| `finanzas-agent/google-sheets-creds` | yes | Full service-account JSON |
| `finanzas-agent/meta-verify-token` | yes | Random string, also pasted in Meta's webhook config |
| `finanzas-agent/allowed-senders` | yes | Comma-separated `wa_id`s allowed to talk to the agent. **Without it the webhook drops every message.** |
| `finanzas-agent/meta-access-token` | for replies | Meta access token (see [Meta setup](setup-meta-whatsapp.md)) |
| `finanzas-agent/meta-app-secret` | for POSTs | Meta app secret, used to verify webhook signatures |
| `finanzas-agent/agent-profile` | no | Owner profile JSON (see below). Without it a generic profile is used. |

```bash
REGION=us-east-2

aws secretsmanager create-secret --region $REGION \
  --name finanzas-agent/anthropic-api-key --secret-string "sk-ant-..."

aws secretsmanager create-secret --region $REGION \
  --name finanzas-agent/google-sheets-creds --secret-string file://creds/service-account.json

aws secretsmanager create-secret --region $REGION \
  --name finanzas-agent/meta-verify-token --secret-string "$(openssl rand -hex 32)"

aws secretsmanager create-secret --region $REGION \
  --name finanzas-agent/allowed-senders --secret-string "5491112345678"

aws secretsmanager create-secret --region $REGION \
  --name finanzas-agent/agent-profile --secret-string '{
    "owner_name": "Ana",
    "categorias_variables": ["comida", "transporte", "salud", "extra"],
    "categorias_fijas": ["alquiler", "tarjeta_visa", "internet"]
  }'
```

The owner profile keeps personal data (name, real spending categories) out of the repository. It is injected into the system prompt at cold start.

## 2. Build and deploy

```bash
cd infra
sam build

sam deploy \
  --stack-name finanzas-agent \
  --region us-east-2 \
  --capabilities CAPABILITY_IAM \
  --resolve-s3 \
  --parameter-overrides "GoogleSheetsId=<your-sheet-id>" "MetaPhoneNumberId=<your-phone-number-id>"
```

The stack outputs `WebhookUrl`. That is the callback URL for Meta.

`MetaPhoneNumberId` can be left empty on the first deploy. The runner still runs the agent and returns the reply in its payload, with `meta_skipped: true`, which is useful for testing before Meta is set up.

## 3. Connect Meta

In Meta for Developers → your app → WhatsApp → Configuration → Webhook:

- **Callback URL:** the `WebhookUrl` output
- **Verify token:** the value of `finanzas-agent/meta-verify-token`
- **Subscribe to:** `messages`

Meta verifies the endpoint with a GET. The webhook echoes `hub.challenge` only when the token matches.

## Operations

**Test the runner without WhatsApp**

```bash
echo '{"user_id":"5491100000000","message":"cuánto gasté este mes?","message_id":"test-1"}' > /tmp/event.json

aws lambda invoke --region us-east-2 \
  --function-name finanzas-agent-runner \
  --cli-binary-format raw-in-base64-out \
  --payload file:///tmp/event.json /tmp/out.json && cat /tmp/out.json
```

Reusing a `message_id` is a no-op (idempotency). Change it on every run.

**Logs**

```bash
aws logs tail /aws/lambda/finanzas-agent-webhook --region us-east-2 --follow
aws logs tail /aws/lambda/finanzas-agent-runner  --region us-east-2 --follow
```

**Reset a conversation**

```bash
aws dynamodb delete-item --region us-east-2 \
  --table-name finanzas-agent-conversation \
  --key '{"user_id":{"S":"5491100000000"}}'
```

**Rotate a secret.** Secrets are cached for the lifetime of a Lambda container. After `put-secret-value`, force a cold start:

```bash
aws lambda update-function-configuration --region us-east-2 \
  --function-name finanzas-agent-runner --description "rotate $(date +%s)"
```

## Troubleshooting

**`#131030 Recipient phone number not in allowed list`.** While the Meta app is in development mode, it can only message numbers added under WhatsApp → API Setup → *Manage phone number list*. For Argentine numbers, see the `wa_id` format note in the [README](../README.md#a-bug-worth-telling): `send_text()` already normalizes it.

**Replies stop overnight with a 401.** Meta's temporary access token lasts 24h. Create a System User token that never expires (see [Meta setup](setup-meta-whatsapp.md#permanent-token)) and store it in `finanzas-agent/meta-access-token`.

**Messages arrive but nothing happens.** Check the webhook logs for `remitente fuera de ALLOWED_SENDERS`: the sender is missing from `finanzas-agent/allowed-senders`.

## Cost

For personal use (≈100 messages/day), AWS costs about **US$2–3/month**. That is almost entirely Secrets Manager at $0.40/secret; Lambda, API Gateway and DynamoDB stay within the free tier. Anthropic usage is extra, depends on the model, and is typically a few dollars per month.
