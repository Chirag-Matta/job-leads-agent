# Job Agent — Phase 1

Automated job discovery + outreach using GPT-4o, Proxycurl, Gmail, and Notion.

## How it works

```
Discovery Agent                     Outreach Agent
───────────────                     ──────────────
Search LinkedIn jobs (Proxycurl)    Read discovered companies from Notion
↓                                   ↓
Filter by role + company type       GPT-4o writes personalised email
↓                                   ↓
Find contacts (founder / HR)        Send via Gmail
↓                                   ↓
Save to Notion (status=discovered)  Update Notion (status=mail_sent)
```

## Project structure

```
job_agent/
├── config.py                  # API keys + your preferences
├── main.py                    # Orchestrator
├── requirements.txt
├── .env.example               # Copy to .env and fill in
├── agents/
│   ├── discovery_agent.py     # GPT-4o agent: find companies & contacts
│   └── outreach_agent.py      # GPT-4o agent: write & send emails
└── tools/
    ├── linkedin.py            # Proxycurl API calls
    ├── email.py               # Gmail SMTP
    └── tracker.py             # Notion database read/write
```

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your API keys
```

Load the .env in config.py (add this to the top of config.py if not already):
```python
from dotenv import load_dotenv
load_dotenv()
```

### 3. Set up Notion database

Create a Notion database with these columns:

| Column name       | Type     |
|-------------------|----------|
| Company           | Title    |
| Role              | Text     |
| Contact Name      | Text     |
| Contact Email     | Email    |
| Contact Title     | Text     |
| Status            | Select   |
| Job URL           | URL      |
| Company LinkedIn  | URL      |
| Date Added        | Date     |
| Last Updated      | Date     |
| Notes             | Text     |

Status options to add: `discovered`, `mail_sent`, `followup_sent`, `interview`, `rejected`, `recontact_later`

### 4. Personalise config.py

Edit the "Your Details" section in `config.py`:
```python
your_name = "Rahul Sharma"
your_role = "Backend Engineer"
your_linkedin = "https://linkedin.com/in/rahulsharma"
...
```

Also update `job_roles` and `target_company_types` to match what you're looking for.

## Running

```bash
# Full run: discovery + outreach
python main.py

# Discovery only (find companies, save to Notion)
python main.py --discover

# Outreach only (email companies already in Notion with status=discovered)
python main.py --outreach
```

## Phase 2 (coming next)

- Reply agent: reads inbox, classifies responses (interview / rejection / no reply)
- Auto follow-up after 2 days of no reply
- Slack notifications for interviews
- 60-day recontact reminders
