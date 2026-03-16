"""
agents/discovery_agent.py

Full discovery flow:
  1. Search job boards (Wellfound, HN, Naukri, LinkedIn via Serper)
  2. LLM filters by role + company preferences
  3. For each matched company → find 5 contacts via Serper
     (2 HR, 2 SDE, 1 Founder)
  4. Enrich each contact's email via Apollo
  5. Save company + contacts to Notion
"""

import json
import logging
from openai import OpenAI
from config import config
from tools.jobs import search_jobs
from tools.contacts import find_contacts
from tools.apollo import enrich_contacts
from tools.tracker import save_company_with_contacts

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=config.groq_api_key,
    base_url="https://api.groq.com/openai/v1",
)

# ── Tool schemas ──────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": (
                "Search job boards for relevant openings. "
                "Returns list of jobs with company, title, description, job_url, source."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Job role keywords to search for.",
                    },
                    "location": {
                        "type": "string",
                        "description": "Location filter e.g. 'Bangalore'.",
                    },
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_and_save_company",
            "description": (
                "For a single matched company: find 5 contacts (2 HR, 2 SDE, 1 Founder) "
                "via Google/Serper, enrich their emails via Apollo, then save everything "
                "to the Notion tracker. Call this once per company."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "Exact company name from search results.",
                    },
                    "role": {
                        "type": "string",
                        "description": "Job role title for this position.",
                    },
                    "job_url": {
                        "type": "string",
                        "description": "URL of the job posting.",
                    },
                },
                "required": ["company", "role", "job_url"],
            },
        },
    },
]

# ── Tool dispatcher ───────────────────────────────────────────

def dispatch_tool(name: str, args: dict) -> str:
    if name == "search_jobs":
        results = search_jobs(
            keywords=args["keywords"],
            location=args.get("location", ",".join(config.preferred_locations)),
            serper_api_key=config.serper_api_key,
        )
        return json.dumps(results)

    elif name == "find_and_save_company":
        company = args["company"]
        role    = args["role"]
        job_url = args.get("job_url", "")

        print(f"\n  → Processing: {company}")

        # Step 1: Find 5 contacts via Serper
        print(f"    [1/3] Finding contacts...")
        contacts = find_contacts(
            company=company,
            applicant_role=config.your_role,
            serper_api_key=config.serper_api_key,
        )

        if not contacts:
            logger.warning(f"No contacts found for {company} — skipping.")
            return json.dumps({"status": "skipped", "reason": "no contacts found"})

        # Step 2: Enrich emails via Apollo
        print(f"    [2/3] Enriching emails for {len(contacts)} contacts via Apollo...")
        contacts = enrich_contacts(
            contacts=contacts,
            company=company,
            api_key=config.apollo_api_key,
        )

        emails_found = sum(1 for c in contacts if c.get("email"))
        print(f"    [2/3] Emails found: {emails_found}/{len(contacts)}")

        # Step 3: Save to Notion
        print(f"    [3/3] Saving to Notion...")
        page_id = save_company_with_contacts(
            company=company,
            role=role,
            job_url=job_url,
            contacts=contacts,
        )

        if page_id:
            print(f"    ✓ Saved {company} — {len(contacts)} contacts")
            return json.dumps({
                "status": "saved",
                "company": company,
                "contacts_saved": len(contacts),
                "emails_found": emails_found,
                "page_id": page_id,
            })
        else:
            return json.dumps({"status": "failed", "reason": "Notion save error"})

    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Agent loop ────────────────────────────────────────────────

def run_discovery_agent() -> None:
    """
    Runs the full discovery agent:
      search → filter → find contacts → enrich emails → save to Notion
    """
    locations_str = ", ".join(config.preferred_locations)
    remote_note   = " (also open to remote)" if config.open_to_remote else ""

    system_prompt = f"""You are a job discovery agent. Find the best companies for a job seeker and save them to Notion.

Job seeker profile:
- Target roles: {", ".join(config.job_roles)}
- Company types: {", ".join(config.target_company_types)}
- Domains: {", ".join(config.target_domains)}
- Company size: {", ".join(config.preferred_company_size)}
- Locations: {locations_str}{remote_note}
- Experience: {config.experience_level}
- Max companies this run: {config.max_companies_per_run}
- Exclude: {", ".join(config.excluded_companies) if config.excluded_companies else "none"}

STRICT RULES:
- Only use REAL company names from search results — never invent any.
- Never invent contact names, emails, or URLs.
- Skip any company in the exclusion list.

Your workflow:
1. Call search_jobs with the target roles as keywords and the preferred location.
2. Review ALL returned results. Pick the top {config.max_companies_per_run} companies that best match:
   - Company type, domain, size
   - Role relevance
   - Location
3. For EACH selected company, call find_and_save_company once.
4. After processing all companies, give a summary of what was saved."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": "Run the job discovery flow now."},
    ]

    logger.info("Starting discovery agent...")

    while True:
        response = client.chat.completions.create(
            model=config.model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        message = response.choices[0].message
        messages.append(message)

        if not message.tool_calls:
            print(f"\n[Discovery Agent] Done:\n{message.content}\n")
            logger.info(f"Discovery agent finished: {message.content}")
            break

        for tc in message.tool_calls:
            name   = tc.function.name
            args   = json.loads(tc.function.arguments)
            logger.info(f"Tool call → {name}({list(args.keys())})")
            result = dispatch_tool(name, args)
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      result,
            })