# Job Agent 🤖

An end-to-end automated job application pipeline that finds relevant companies, discovers decision-maker contacts, enriches their emails, and sends personalised cold outreach — all with zero manual intervention.

---

## What It Does

Most job seekers spend hours manually searching job boards, finding recruiter emails, and writing cold emails. Job Agent automates the entire pipeline using two LLM-powered agents:

1. **Discovery Agent** — Searches multiple job boards, filters companies using an LLM, finds 5 targeted contacts per company (HR, SDE, Founder), and enriches their emails.
2. **Outreach Agent** — Reads discovered companies from Notion, writes a personalised cold email for each contact using an LLM, sends it via Gmail, and updates the tracker.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                              │
│                      Orchestrator                           │
└──────────────┬──────────────────────────┬───────────────────┘
               │                          │
               ▼                          ▼
  ┌────────────────────┐      ┌────────────────────────┐
  │  Discovery Agent   │      │    Outreach Agent      │
  │  (Groq LLM)        │      │    (Groq LLM)          │
  └────────┬───────────┘      └────────────┬───────────┘
           │                               │
    ┌──────▼──────┐                 ┌──────▼──────┐
    │  tools/     │                 │  tools/     │
    │  jobs.py    │                 │  gmail.py   │
    │  contacts.py│                 │  tracker.py │
    │  apollo.py  │                 └─────────────┘
    │  tracker.py │
    └─────────────┘

Job Sources          Contact Discovery     Email Enrichment    Tracker
────────────         ─────────────────     ────────────────    ───────
Wellfound            Google/Serper         Apollo.io           Notion
HN Who's Hiring      LinkedIn profiles     (name + company     (read/write
Naukri               (HR, SDE, Founder)     match strategy)     status)
LinkedIn Posts
```

---

## Agent Flow

### Discovery Agent

```
1. search_jobs()
   ├── Wellfound scraper
   ├── HN Who's Hiring (Algolia API → Firebase)
   ├── Naukri scraper
   └── LinkedIn Posts (Serper Google search)
           │
           ▼
2. Groq LLM filters results
   └── Picks top N companies by role, domain, size, location
           │
           ▼
3. find_and_save_company() — called once per company
   ├── find_contacts() via Serper
   │   ├── 2× HR / Recruiter
   │   ├── 2× SDE (same role as applicant)
   │   └── 1× Founder / CEO / CTO
   ├── enrich_contacts() via Apollo.io
   │   ├── Strategy 1: name + company search (/mixed_people/search)
   │   └── Strategy 2: LinkedIn URL match (/people/match)
   └── save_company_with_contacts() → Notion page
```

### Outreach Agent

```
1. get_discovered_companies() — reads Notion, returns contacts with status=discovered
           │
           ▼
2. For each contact:
   ├── Groq LLM writes personalised cold email (<120 words)
   ├── send_email() via Gmail SMTP
   └── update_contact_status() → Notion (discovered → mail_sent)
```

---

## Project Structure

```
job_agent/
├── main.py                    # Orchestrator — runs discovery, outreach, or both
├── config.py                  # All preferences and API keys
├── requirements.txt
├── .env.example
├── agents/
│   ├── discovery_agent.py     # Groq agent: search → filter → find contacts → save
│   └── outreach_agent.py      # Groq agent: read Notion → write email → send → update
└── tools/
    ├── jobs.py                # Wellfound, HN, Naukri, LinkedIn Post scrapers
    ├── contacts.py            # Serper-based LinkedIn contact discovery
    ├── apollo.py              # Apollo.io email enrichment (3 strategies)
    ├── gmail.py               # Gmail SMTP sender
    └── tracker.py             # Notion read/write with status lifecycle
```

---

## Setup

### 1. Clone & install dependencies

```bash
git clone https://github.com/Chirag-Matta/job-agent.git
cd job-agent
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Fill in your `.env`:

```env
GROQ_API_KEY=your_groq_api_key
SERPER_API_KEY=your_serper_api_key
APOLLO_API_KEY=your_apollo_api_key
NOTION_API_KEY=your_notion_integration_key
GMAIL_SENDER=you@gmail.com
GMAIL_APP_PASSWORD=your_gmail_app_password
```

### 3. Set up Gmail App Password

1. Enable 2FA on your Google account
2. Go to `myaccount.google.com → Security → App Passwords`
3. Generate a password for "Mail" and set it as `GMAIL_APP_PASSWORD`

### 4. Set up Notion

Create a Notion page and a Notion integration at [notion.so/my-integrations](https://notion.so/my-integrations). Share the page with your integration, then copy the page ID into `tracker.py`:

```python
PAGE_ID = "your-notion-page-id"
```

The agent writes structured content directly to the page — no database required.

### 5. Personalise config.py

```python
your_name        = "Your Name"
your_role        = "Backend Engineer"
your_linkedin    = "https://linkedin.com/in/yourprofile"
your_github      = "https://github.com/yourusername"
your_resume_link = "https://drive.google.com/..."

job_roles              = ["Backend Engineer", "Software Engineer"]
target_company_types   = ["startup", "product-based"]
target_domains         = ["AI / ML", "Fintech"]
preferred_company_size = ["early-stage"]
preferred_locations    = ["Bangalore", "Hyderabad"]
open_to_remote         = True
max_companies_per_run  = 5
```

---

## Running

```bash
# Full run: discovery + outreach
python main.py

# Discovery only (find companies, save to Notion)
python main.py --discover

# Outreach only (email companies already in Notion with status=discovered)
python main.py --outreach
```

---

## Notion Tracker Format

Each company is written to Notion as:

```
─────────────────────────────────────────────────────
### XYZ AI — Backend Engineer  |  discovered  |  2026-03-16
  📋 Job: https://wellfound.com/jobs/...

  [HR]      Priya S.  (Talent Acquisition)  |  priya@xyz.ai       |  discovered
  [HR]      Ankit M.  (HR Manager)          |  ankit@xyz.ai       |  mail_sent
  [SDE]     Rahul K.  (Backend Engineer)    |  rahul@xyz.ai       |  mail_sent
  [SDE]     Sneha R.  (Software Engineer)   |  No email           |  discovered
  [Founder] Varun T.  (Co-founder & CTO)    |  varun@xyz.ai       |  mail_sent
```

**Status lifecycle:**

| Status | Meaning |
|---|---|
| `discovered` | Found, not yet contacted |
| `mail_sent` | Cold email sent |
| `followup_sent` | Follow-up sent |
| `interview` | Interview scheduled |
| `rejected` | Rejected or no fit |
| `recontact_later` | Revisit in 60 days |

---

## Tech Stack

| Layer | Technology |
|---|---|
| LLM | Groq — Llama 3.3-70B (primary), Llama 3.1-8B (fallback) |
| Job Discovery | Wellfound scraper, HN Algolia API, Naukri scraper, Serper |
| Contact Discovery | Serper (Google search → LinkedIn profiles) |
| Email Enrichment | Apollo.io (`/mixed_people/search`, `/people/match`) |
| Email Sending | Gmail SMTP (App Password) |
| Tracker | Notion API (block-level read/write) |
| LLM Interface | OpenAI-compatible client pointed at Groq base URL |

---

## Key Design Decisions

**Why Groq over OpenAI?**
Groq's inference is significantly faster and cheaper for agentic loops that make many sequential LLM calls. The OpenAI-compatible client means swapping providers requires changing one line.

**Why block-level Notion instead of a database?**
A Notion database requires a fixed schema and a paid plan for some API features. Writing directly to a page as structured blocks gives full flexibility — the agent can append, read, and update individual contact lines without any schema setup.

**Why 5 contacts per company (2 HR + 2 SDE + 1 Founder)?**
Sending to multiple contact types at the same company significantly increases reply rates. HR routes you through process; SDEs can give referrals; founders at early-stage startups often hire directly.

**Why Apollo.io for email enrichment?**
Apollo's free tier supports `/mixed_people/search` by name + company, which covers most cases. The agent falls back to LinkedIn URL matching as a second strategy, maximising email find rate without a paid plan.

---

## Limitations & Known Issues

- **Wellfound / Naukri scraping** — these sites update their HTML structure periodically; selectors in `jobs.py` may need updating if scraping breaks.
- **Apollo free tier** — email reveal is rate-limited; expect ~40–60% email find rate on free tier.
- **Serper contact discovery** — relies on Google indexing LinkedIn profiles, which can miss recently updated profiles.
- **No deduplication across runs** — running discovery twice may save the same company again; add a check against existing Notion entries if running frequently.

---

## Roadmap — Phase 2

- [ ] **Reply Agent** — reads Gmail inbox, classifies responses (interview / rejection / no reply)
- [ ] **Auto follow-up** — sends a follow-up after 2 days of no reply
- [ ] **Slack notifications** — pings a channel when an interview is booked
- [ ] **60-day recontact reminders** — surfaces `recontact_later` entries automatically
- [ ] **Resume tailoring** — rewrites resume bullet points per job description using LLM

---