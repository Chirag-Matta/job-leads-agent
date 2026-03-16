"""
tools/tracker.py

Uses Notion Page + Blocks API to append job application records
as table rows directly into your Job Application Tracker page.

Page ID: 2e8b094e7717801d9192f6456308c5c2
"""

import requests
import logging
from datetime import date
from typing import Optional
from config import config

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
PAGE_ID    = "2e8b094e7717801d9192f6456308c5c2"

HEADERS = {
    "Authorization": f"Bearer {config.notion_api_key}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# Status values
STATUS_DISCOVERED = "discovered"
STATUS_MAIL_SENT  = "mail_sent"
STATUS_FOLLOWUP   = "followup_sent"
STATUS_INTERVIEW  = "interview"
STATUS_REJECTED   = "rejected"
STATUS_RECONTACT  = "recontact_later"


def save_company_record(
    company: str,
    role: str,
    contact_name: str,
    contact_email: str,
    contact_title: str,
    job_url: str = "",
    company_linkedin: str = "",
) -> Optional[str]:
    """
    Appends a new job application entry as a styled text block
    to your Notion tracker page.
    Returns the block ID on success, None on failure.
    """
    today = str(date.today())
    
    # Build a readable text block for the entry
    lines = [
        f"🏢  {company}  |  {role}  |  {today}  |  {STATUS_DISCOVERED}",
        f"👤  {contact_name or 'Unknown'}  —  {contact_title or 'Unknown'}  —  {contact_email or 'No email'}",
    ]
    if job_url:
        lines.append(f"🔗  {job_url}")

    children = []

    # Divider before each entry
    children.append({"object": "block", "type": "divider", "divider": {}})

    # Heading: company + role
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {"content": f"{company} — {role}"}}]
        }
    })

    # Contact info
    children.append({
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {
                "content": f"Contact: {contact_name or 'Unknown'} ({contact_title or 'Unknown'}) — {contact_email or 'No email found'}"
            }}]
        }
    })

    # Status + date
    children.append({
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {
                "content": f"Status: {STATUS_DISCOVERED}  |  Date: {today}"
            }}]
        }
    })

    # Job URL
    if job_url:
        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{
                    "type": "text",
                    "text": {"content": "Job post: ", "link": None},
                }, {
                    "type": "text",
                    "text": {"content": job_url, "link": {"url": job_url}},
                }]
            }
        })

    # Retry up to 3 times on timeout/failure
    for attempt in range(3):
        try:
            resp = requests.patch(
                f"{NOTION_API}/blocks/{PAGE_ID}/children",
                json={"children": children},
                headers=HEADERS,
                timeout=20,
            )

            if resp.status_code == 200:
                block_id = resp.json()["results"][0]["id"]
                logger.info(f"Saved to Notion page: {company} | block={block_id}")
                return block_id
            else:
                logger.error(f"Notion append failed for {company}: {resp.status_code} {resp.text}")
                return None
        except requests.exceptions.Timeout:
            logger.warning(f"Notion timeout for {company} (attempt {attempt + 1}/3)")
            if attempt == 2:
                logger.error(f"Notion save failed for {company} after 3 retries")
                return None
        except Exception as e:
            logger.error(f"Notion save failed for {company}: {e}")
            return None


def update_application_status(page_id: str, status: str, notes: str = "") -> bool:
    """
    Appends a status-update note block under an existing entry.
    (page_id here is actually the block_id of the heading block)
    """
    today = str(date.today())
    content = f"→ Status updated: {status}  |  {today}"
    if notes:
        content += f"  |  {notes}"

    children = [{
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": content}}],
            "icon": {"emoji": "📬"},
            "color": "blue_background",
        }
    }]

    resp = requests.patch(
        f"{NOTION_API}/blocks/{page_id}/children",
        json={"children": children},
        headers=HEADERS,
        timeout=10,
    )
    return resp.status_code == 200


def get_discovered_companies() -> list:
    """
    Reads all blocks from the tracker page and extracts
    entries that contain 'status: discovered'.
    Returns list of dicts for the outreach agent.
    """
    resp = requests.get(
        f"{NOTION_API}/blocks/{PAGE_ID}/children?page_size=100",
        headers=HEADERS,
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error(f"Could not read Notion page: {resp.text}")
        return []

    blocks = resp.json().get("results", [])
    records = []
    current = {}

    for block in blocks:
        btype = block.get("type")
        text  = _block_text(block)

        # Heading_3 = new company entry
        if btype == "heading_3" and "—" in text:
            if current:
                records.append(current)
            parts = text.split("—", 1)
            current = {
                "page_id":       block["id"],
                "company":       parts[0].strip(),
                "role":          parts[1].strip() if len(parts) > 1 else "",
                "contact_name":  "",
                "contact_email": "",
                "contact_title": "",
                "job_url":       "",
                "status":        "",
            }

        elif btype == "bulleted_list_item" and current:
            if text.startswith("Contact:"):
                # "Contact: Name (Title) — email"
                rest = text.replace("Contact:", "").strip()
                email_part = rest.split("—")[-1].strip() if "—" in rest else ""
                name_title = rest.split("—")[0].strip() if "—" in rest else rest
                current["contact_email"] = email_part if "@" in email_part else ""
                if "(" in name_title:
                    current["contact_name"]  = name_title.split("(")[0].strip()
                    current["contact_title"] = name_title.split("(")[1].rstrip(")").strip()

            elif text.startswith("Status:"):
                status_part = text.split("|")[0].replace("Status:", "").strip()
                current["status"] = status_part

            elif text.startswith("Job post:"):
                current["job_url"] = text.replace("Job post:", "").strip()

    if current:
        records.append(current)

    # Filter to only discovered ones
    discovered = [r for r in records if r.get("status") == STATUS_DISCOVERED]
    logger.info(f"Found {len(discovered)} discovered companies on Notion page")
    return discovered


def _block_text(block: dict) -> str:
    btype = block.get("type", "")
    rich  = block.get(btype, {}).get("rich_text", [])
    return "".join(rt.get("plain_text", "") for rt in rich)