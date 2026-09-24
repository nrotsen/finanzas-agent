# Meta WhatsApp Cloud API setup

Do this once the agent works locally. The first 1,000 service conversations per month are free; a personal bot you message first stays within them.

## 1. Create the app

1. At https://developers.facebook.com/ go to **My Apps → Create App → Business**.
2. On the app dashboard, add the **WhatsApp** product.

Meta provisions a **test number**, a **temporary access token** (valid for 24h) and a **Phone Number ID**. The Phone Number ID is the `MetaPhoneNumberId` stack parameter; it is not a secret.

## 2. Allow your own number

While the app is in development mode, the test number can only message verified recipients (up to 5). Go to **WhatsApp → API Setup → Manage phone number list**, add your number and enter the code Meta sends you.

Add the same number to the `finanzas-agent/allowed-senders` secret, so the agent accepts messages from it.

## 3. Store the Meta secrets

```bash
aws secretsmanager create-secret --region us-east-2 \
  --name finanzas-agent/meta-access-token --secret-string "EAA..."

# App settings → Basic → App secret
aws secretsmanager create-secret --region us-east-2 \
  --name finanzas-agent/meta-app-secret --secret-string "<app-secret>"
```

## 4. Register the webhook

After [deploying](deploy.md), set the callback URL, verify token and the `messages` subscription as described in [Connect Meta](deploy.md#3-connect-meta).

## Permanent token

The 24h token is fine for a first test. For a bot that keeps working:

1. In Meta Business Manager, go to **Settings → Users → System Users** and create one.
2. Give it access to the WhatsApp Business Account.
3. Generate a token with `whatsapp_business_messaging` and `whatsapp_business_management`, set to **never expire**.
4. Replace the secret with `put-secret-value`, then force a cold start (see [Rotate a secret](deploy.md#operations)).

## Going beyond the test number

Test numbers expire after about 90 days and keep the recipient whitelist. The options are:

- **Your own number with Business Verification.** No whitelist, but verification can take days or weeks, and the number moves off regular WhatsApp.
- **A provider such as Twilio.** Faster to set up, but it costs per message and means replacing `src/whatsapp/meta_client.py`.
