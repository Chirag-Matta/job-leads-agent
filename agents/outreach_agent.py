import json
import logging
from openai import OpenAI
from config import config
from tools.gmail import send_email
from tools.tracker import get_discovered_companies, update_application_status, STATUS_MAIL_SENT

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
            "name": "send_email",
            "description": "Send a cold outreach email to a contact at a company.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject line."},
                    "body": {"type": "string", "description": "Plain text email body."},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_application_status",
            "description": "Update the status of a company record in the Notion tracker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "page_id": {"type": "string"},
                    "status": {"type": "string", "description": "New status value."},
                    "notes": {"type": "string", "description": "Optional notes to add."},
                },
                "required": ["page_id", "status"],
            },
        },
    },
]

# ── Tool dispatcher ───────────────────────────────────────────────────────────

def dispatch_tool(name: str, args: dict) -> str:
    if name == "send_email":
        success = send_email(
            to=args["to"],
            subject=args["subject"],
            body=args["body"],
        )
        return json.dumps({"success": success})

    elif name == "update_application_status":
        success = update_application_status(
            page_id=args["page_id"],
            status=args["status"],
            notes=args.get("notes", ""),
        )
        return json.dumps({"success": success})

    return json.dumps({"error": f"Unknown tool: {name}"})


# ── Agent loop ────────────────────────────────────────────────────────────────

def run_outreach_agent() -> None:
    """
    Runs the outreach agent.
    For each company with status=discovered, GPT-4o will:
      1. Write a personalised cold email
      2. Send it via Gmail
      3. Update Notion status to mail_sent
    """
    companies = get_discovered_companies()
    if not companies:
        logger.info("No discovered companies to process.")
        print("[Outreach Agent] No discovered companies found. Run discovery first.")
        return

    print(f"[Outreach Agent] Found {len(companies)} companies to reach out to.\n")

    system_prompt = f"""You are a professional job outreach agent. 
You write concise, warm, and personalised cold emails on behalf of a job seeker.

About the job seeker:
- Name: {config.your_name}
- Role they're looking for: {config.your_role}
- LinkedIn: {config.your_linkedin}
- GitHub: {config.your_github}
- Resume: {config.your_resume_link}

Email writing guidelines:
- Keep it under 120 words.
- Open with a specific reason you're interested in THIS company.
- Mention the role clearly.
- One call to action: ask for a 15-minute chat or to review the resume.
- No generic phrases like "I hope this email finds you well."
- Sign off with name, LinkedIn, and resume link.
- Subject line: short and specific, e.g. "Backend engineer interested in [Company]"

After sending each email, update the tracker status to "{STATUS_MAIL_SENT}"."""

    for company in companies:
        if not company["contact_email"]:
            logger.warning(f"No email for {company['company']} — skipping.")
            print(f"  [skip] {company['company']} — no email address found.")
            continue

        print(f"  → Reaching out to {company['company']} ({company['contact_name']})...")

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Write and send an outreach email for this opportunity:\n"
                    f"Company: {company['company']}\n"
                    f"Role: {company['role']}\n"
                    f"Contact: {company['contact_name']} ({company['contact_title']})\n"
                    f"Email: {company['contact_email']}\n"
                    f"Job URL: {company.get('job_url', 'N/A')}\n"
                    f"Notion page ID: {company['page_id']}\n\n"
                    f"Send the email, then update the tracker."
                ),
            },
        ]

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
                logger.info(f"Outreach done for {company['company']}: {message.content}")
                break

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

    print("\n[Outreach Agent] All done.")
