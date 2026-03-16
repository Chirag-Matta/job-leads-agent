import json
import logging
from openai import OpenAI
from config import config
from tools.jobs import search_jobs
from tools.tracker import save_company_record

logger = logging.getLogger(__name__)

# Use Groq via OpenAI-compatible endpoint
client = OpenAI(
    api_key=config.groq_api_key,
    base_url="https://api.groq.com/openai/v1",
)

# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_jobs",
            "description": "Search multiple job boards and LinkedIn posts for jobs matching keywords. Returns a list of real job listings with company name, description, job URL, and source.",
            "parameters": {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of job role keywords to search for.",
                    },
                },
                "required": ["keywords"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_company_record",
            "description": "Save a discovered company to the Notion tracker. Only use REAL data from search results — never invent company names, contacts, or emails.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string", "description": "Real company name from search results"},
                    "role": {"type": "string", "description": "Job role title"},
                    "contact_name": {"type": "string", "description": "Contact name if found in the listing, otherwise 'Unknown'"},
                    "contact_email": {"type": "string", "description": "Contact email if found in the listing, otherwise 'Unknown'"},
                    "contact_title": {"type": "string", "description": "Contact's job title if found, otherwise 'Unknown'"},
                    "job_url": {"type": "string", "description": "URL to the job posting or LinkedIn post"},
                    "company_linkedin": {"type": "string", "description": "Company LinkedIn URL if available"},
                },
                "required": ["company", "role", "contact_name", "contact_email", "contact_title"],
            },
        },
    },
]

# ── Tool dispatcher ───────────────────────────────────────────────────────────

def dispatch_tool(name: str, args: dict) -> str:
    if name == "search_jobs":
        locations = ", ".join(config.preferred_locations)
        results = search_jobs(
            keywords=args["keywords"],
            location=locations,
            serper_api_key=config.serper_api_key,
        )
        return json.dumps(results)

    elif name == "save_company_record":
        page_id = save_company_record(**args)
        return json.dumps({"page_id": page_id, "status": "saved" if page_id else "failed"})

    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_discovery_agent() -> None:
    """
    Runs the discovery agent.
    Searches job boards and LinkedIn posts, filters to preferences,
    and saves real results to Notion.
    """
    locations_str = ', '.join(config.preferred_locations)
    remote_note = ' (also open to remote)' if config.open_to_remote else ''

    system_prompt = f"""You are a job discovery agent. Your job is to find relevant companies and roles for a job seeker.

Job seeker preferences:
- Roles: {', '.join(config.job_roles)}
- Company types: {', '.join(config.target_company_types)}
- Domains / industries: {', '.join(config.target_domains)}
- Company size: {', '.join(config.preferred_company_size)}
- Locations: {locations_str}{remote_note}
- Work mode: {config.work_mode}
- Experience level: {config.experience_level}
- Max companies to process: {config.max_companies_per_run}
{'- EXCLUDE these companies: ' + ', '.join(config.excluded_companies) if config.excluded_companies else ''}

CRITICAL RULES:
- You may ONLY use data that comes from the search_jobs results. 
- NEVER invent or fabricate company names, contact names, emails, or URLs.
- If a search result does not include a contact name or email, use "Unknown" for those fields.
- Use the REAL company name and job_url exactly as returned by search_jobs.
- Do NOT use placeholder names like "Example Startup" or "johndoe@example.com".

Your workflow:
1. Call search_jobs with the job roles as keywords.
2. Review the REAL results returned. Pick the top {config.max_companies_per_run} most relevant companies.
3. SKIP any company in the exclusion list.
4. Prefer companies that match the target domains, company type, and size.
5. For each selected company, call save_company_record using ONLY the data from the search results.
6. Use the poster_name field (if available) as contact_name, and set contact_email to "Unknown" if not found.
7. Summarise what you saved at the end.

Be selective — only pick companies that closely match the preferences."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Run the job discovery flow now."},
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

        # No more tool calls — agent is done
        if not message.tool_calls:
            logger.info(f"Discovery agent finished:\n{message.content}")
            print(f"\n[Discovery Agent] Done:\n{message.content}\n")
            break

        # Execute each tool call
        for tc in message.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)
            logger.info(f"Tool call: {name}({args})")

            result = dispatch_tool(name, args)

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })
