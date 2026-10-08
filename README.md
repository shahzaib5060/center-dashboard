# Center Repository – Live Dashboard

Streamlit dashboard that reads the **Center Repository – Master** Google Sheet live
(`Centers` + `Repository` tabs) and refreshes every 5 minutes, or instantly with **Refresh now**.

All numbers are recalculated from the raw rows, so they don't depend on the `Progress` tab's formulas.

## What's inside

| Tab | What it shows |
|---|---|
| **Overview** | Coverage by region, condition mix by region, model / layout / condition breakdown, region scorecard |
| **Renovation Priority** | 0–100 priority score per center, Urgent/High/Medium/Low bands, downloadable Excel list with photo-folder links |
| **Issues** | The free-text *Key Issues* grouped into themes (paint, seepage, signboard, washroom…), themes × region heatmap, searchable comments |
| **Survey Tracker** | Area-lead coverage, list of pending centers, submissions per day |
| **Data Quality** | Unreadable renovation years, blank years, re-submissions, codes not in the master list, missing photo links |
| **Center Lookup** | One center's full record and a button to open its photo folder |

Sidebar filters: Region → Regional Lead → Area Lead (cascading), Model, Condition.

**Priority score:** condition up to 50 pts · Older V6 20 / V6 10 / V7 0 · signboard issues up to 15 ·
no back-lit logo 5 · years since renovation up to 10 (unknown = 5).
Bands: Urgent ≥ 60, High 45–59, Medium 31–44, Low ≤ 30. Change the weights in `prepare()` in `app.py`.

## 1. Run it on your laptop

```bash
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501. Without the Google connection set up, use **Or load an exported .xlsx**
in the sidebar (File → Download → Microsoft Excel from the sheet).

## 2. Connect it to the live sheet (one-time, ~10 minutes)

The sheet sits in the `cll.edu.pk` Workspace, so use a **service account**. It keeps the sheet private.

1. Go to <https://console.cloud.google.com> → create a project (e.g. `cll-dashboards`).
2. **APIs & Services → Library** → enable **Google Sheets API** and **Google Drive API**.
3. **IAM & Admin → Service Accounts → Create** → name it `center-dashboard` → Done.
4. Open it → **Keys → Add key → JSON** → a `.json` file downloads.
5. In the Google Sheet, click **Share** and add the service account's email
   (`center-dashboard@…iam.gserviceaccount.com`) as **Viewer**.
6. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and paste the values from the JSON file.

   Tip: if your Workspace admin blocks sharing with outside accounts, ask IT to allow the service account,
   or use option B below.

Restart the app. The sidebar will say **Source: Google Sheet (service account)**.

**Option B (simpler, less private):** set the sheet to *Anyone with the link → Viewer*. With no secrets file,
the app reads it through the public CSV export. Only do this if the data can be seen by anyone holding the link.

## 3. Put it online for the team (Streamlit Community Cloud, free)

1. Push this folder to a **private** GitHub repo (`secrets.toml` is git-ignored – never commit it).
2. <https://share.streamlit.io> → **New app** → pick the repo, `app.py`.
3. **Advanced settings → Secrets** → paste the contents of your `secrets.toml`.
4. Deploy, then in the app's **Settings → Sharing** restrict viewers to `@cll.edu.pk` emails.

## Notes

- If a center was submitted more than once, the **latest** submission is used.
- "Last Renovation (Year)" is only used when it reads as a real year (e.g. `2024`, or `8.2023` → 2023).
  Entries like `0`, `-4`, `22025`, `2027` are listed in **Data Quality** and scored as "unknown".
- Changing the sheet's column names or tab names will break the reader. Keep `Centers` and `Repository` as they are.
