# Google Sheets setup

The agent reads and writes a spreadsheet through a Google Cloud service account, so it needs no interactive OAuth.

## 1. Create the spreadsheet

1. Create a new spreadsheet at https://sheets.google.com.
2. Copy its ID from the URL: `https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit`. This is `GOOGLE_SHEETS_ID`.

Don't create the tabs by hand. The adapter creates them with the right headers on first use.

## 2. Create a service account

1. In https://console.cloud.google.com/, create a project.
2. Go to **APIs & Services → Library**, search for **Google Sheets API** and click **Enable**.
3. Go to **APIs & Services → Credentials → Create credentials → Service account**. It needs no project role: access is granted by sharing the sheet.
4. Open the service account, then go to **Keys → Add key → JSON**.
5. Save the file as `creds/service-account.json`. The `creds/` folder is git-ignored.

## 3. Share the sheet with the service account

Share the spreadsheet with the service account's email (`<name>@<project>.iam.gserviceaccount.com`) as **Editor**. Untick "Notify people".

## 4. Try it

```bash
cp .env.example .env   # set GOOGLE_SHEETS_ID and ANTHROPIC_API_KEY
python -m scripts.chat_cli
```

Send `gasté 5000 en el super`. The agent asks for the payment method, and after you answer a new row appears in the sheet.
