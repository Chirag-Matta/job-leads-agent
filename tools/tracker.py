"""
tools/tracker.py

Writes job application records to your Notion page.

Structure per company:
  ─────────────────────────────────
  ### XYZ AI — Backend Engineer  |  discovered  |  2026-03-16
    📋 Job: <url>

  [HR]      Priya S.  |  priya@xyz.ai  |  mail_sent
  [HR]      Ankit M.  |  ankit@xyz.ai  |  discovered
  [SDE]     Rahul K.  |  rahul@xyz.ai  |  mail_sent
  [SDE]     Sneha R.  |  sneha@xyz.ai  |  discovered
  [Founder] Varun T.  |  varun@xyz.ai  |  mail_sent
"""

import requests
import logging
from datetime import date
from typing import Optional, List, Dict
from config import config

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
PAGE_ID    = "2e8b094e7717801d9192f6456308c5c2"

HEADERS = {
    "Authorization": f"Bearer {config.notion_api_key}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# Status values used across agents
STATUS_DISCOVERED = "discovered"
STATUS_MAIL_SENT  = "mail_sent"
STATUS_FOLLOWUP   = "followup_sent"
STATUS_INTERVIEW  = "interview"
STATUS_REJECTED   = "rejected"
STATUS_RECONTACT  = "recontact_later"

TYPE_LABELS = {
    "hr":      "HR",
    "sde":     "SDE",
    "founder": "Founder",
}


# ── Write ─────────────────────────────────────────────────────

def save_company_with_contacts(
    company: str,
    role: str,
    job_url: str,
    contacts: List[Dict],
) -> Optional[str]:
    """
    Append one company heading + one bullet per contact to the Notion page.
    Returns the heading block ID or None on failure.

    contacts: list of {name, title, linkedin_url, contact_type, email}
    """
    today = str(date.today())
    children = []

    # ── Divider ──
    children.append({"object": "block", "type": "divider", "divider": {}})

    # ── Company heading ──
    children.append({
        "object": "block",
        "type": "heading_3",
        "heading_3": {
            "rich_text": [{"type": "text", "text": {
                "content": f"{company} — {role}  |  {STATUS_DISCOVERED}  |  {today}"
            }}]
        }
    })

    # ── Job URL ──
    if job_url:
        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": "Job post: "}},
                    {"type": "text", "text": {"content": job_url, "link": {"url": job_url}}},
                ]
            }
        })

    # ── One block per contact ──
    for c in contacts:
        label    = TYPE_LABELS.get(c.get("contact_type", ""), "Contact")
        name     = c.get("name", "Unknown")
        title    = c.get("title", "")
        email    = c.get("email", "") or "No email"
        li_url   = c.get("linkedin_url", "")

        # Build rich text: [TYPE] Name (Title) | email
        rich = []

        # Type badge text
        rich.append({"type": "text", "text": {"content": f"[{label}]  "}})

        # Name as LinkedIn link if available
        if li_url:
            rich.append({"type": "text", "text": {
                "content": name, "link": {"url": li_url}
            }})
        else:
            rich.append({"type": "text", "text": {"content": name}})

        if title:
            rich.append({"type": "text", "text": {"content": f"  ({title})"}})

        rich.append({"type": "text", "text": {"content": f"  |  {email}  |  {STATUS_DISCOVERED}"}})

        children.append({
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich}
        })

    # ── Write to Notion (retry 3x) ──
    for attempt in range(3):
        try:
            resp = requests.patch(
                f"{NOTION_API}/blocks/{PAGE_ID}/children",
                json={"children": children},
                headers=HEADERS,
                timeout=20,
            )
            if resp.status_code == 200:
                heading_id = resp.json()["results"][1]["id"]  # [0]=divider, [1]=heading
                logger.info(f"Saved: {company} with {len(contacts)} contacts")
                return heading_id
            else:
                logger.error(f"Notion save failed ({resp.status_code}): {resp.text[:200]}")
                return None
        except requests.exceptions.Timeout:
            logger.warning(f"Notion timeout for {company} (attempt {attempt+1}/3)")
    return None


def update_contact_status(block_id: str, new_status: str) -> bool:
    """
    Update a single contact bullet block — replace its status text.
    block_id: the ID of the bulleted_list_item block for that contact.
    """
    # Fetch current block text first
    try:
        resp = requests.get(
            f"{NOTION_API}/blocks/{block_id}",
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code != 200:
            return False

        block = resp.json()
        rich  = block.get("bulleted_list_item", {}).get("rich_text", [])

        # Update the last text segment that contains the old status
        for rt in reversed(rich):
            text = rt.get("text", {}).get("content", "")
            for old_status in [STATUS_DISCOVERED, STATUS_MAIL_SENT,
                               STATUS_FOLLOWUP, STATUS_INTERVIEW,
                               STATUS_REJECTED, STATUS_RECONTACT]:
                if old_status in text:
                    rt["text"]["content"] = text.replace(old_status, new_status)
                    break

        # Write back
        update_resp = requests.patch(
            f"{NOTION_API}/blocks/{block_id}",
            json={"bulleted_list_item": {"rich_text": rich}},
            headers=HEADERS,
            timeout=10,
        )
        return update_resp.status_code == 200

    except Exception as e:
        logger.error(f"update_contact_status failed: {e}")
        return False


# ── Read ──────────────────────────────────────────────────────

def get_discovered_companies() -> List[Dict]:
    """
    Read the Notion page and return companies that have at least
    one contact with status=discovered.

    Returns a list of company dicts, each with a 'contacts' list:
    {
      page_id, company, role, job_url,
      contacts: [{block_id, name, title, email, contact_type, status}]
    }
    """
    resp = requests.get(
        f"{NOTION_API}/blocks/{PAGE_ID}/children?page_size=100",
        headers=HEADERS,
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error(f"Could not read Notion page: {resp.text}")
        return []

    blocks  = resp.json().get("results", [])
    records = []
    current = None

    for block in blocks:
        btype = block.get("type")
        text  = _block_text(block)

        # New company heading
        if btype == "heading_3" and "—" in text and "|" in text:
            if current and current["contacts"]:
                records.append(current)
            parts  = text.split("—", 1)
            company = parts[0].strip()
            rest    = parts[1].split("|")[0].strip() if len(parts) > 1 else ""
            current = {
                "page_id":  block["id"],
                "company":  company,
                "role":     rest,
                "job_url":  "",
                "contacts": [],
            }

        elif current and btype == "bulleted_list_item":
            # Job URL line
            if text.startswith("Job post:"):
                current["job_url"] = text.replace("Job post:", "").strip()
                continue

            # Contact line: [HR]  Name (Title)  |  email  |  status
            contact = _parse_contact_block(block, text)
            if contact:
                current["contacts"].append(contact)

    if current and current["contacts"]:
        records.append(current)

    # Filter: only companies that have at least one undiscovered contact
    result = []
    for r in records:
        undiscovered = [c for c in r["contacts"] if c["status"] == STATUS_DISCOVERED]
        if undiscovered:
            r["contacts"] = undiscovered
            result.append(r)

    logger.info(f"Found {len(result)} companies with undiscovered contacts")
    return result


def _parse_contact_block(block: dict, text: str) -> Optional[Dict]:
    """Parse a contact bullet block into a structured dict."""
    # Must start with [TYPE]
    m = re.match(r"\[(\w+)\]\s+(.+)", text)
    if not m:
        return None

    contact_type_label = m.group(1).lower()  # hr | sde | founder
    rest = m.group(2)

    # Split on ' | '
    parts = [p.strip() for p in rest.split("|")]
    if len(parts) < 3:
        return None

    # Name (Title) part
    name_part = parts[0]
    name_m = re.match(r"(.+?)\s*\((.+?)\)", name_part)
    name  = name_m.group(1).strip() if name_m else name_part.strip()
    title = name_m.group(2).strip() if name_m else ""

    email  = parts[1].strip() if len(parts) > 1 else ""
    status = parts[2].strip() if len(parts) > 2 else STATUS_DISCOVERED

    # Get LinkedIn URL from rich text link if present
    linkedin_url = ""
    for rt in block.get("bulleted_list_item", {}).get("rich_text", []):
        link = rt.get("text", {}).get("link")
        if link and "linkedin.com" in link.get("url", ""):
            linkedin_url = link["url"]
            break

    return {
        "block_id":     block["id"],
        "name":         name,
        "title":        title,
        "email":        email if email != "No email" else "",
        "contact_type": contact_type_label,
        "linkedin_url": linkedin_url,
        "status":       status,
    }


def _block_text(block: dict) -> str:
    btype = block.get("type", "")
    rich  = block.get(btype, {}).get("rich_text", [])
    return "".join(rt.get("plain_text", "") for rt in rich)


import re  # needed for _parse_contact_block