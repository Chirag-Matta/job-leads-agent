"""
tools/contacts.py

Finds 5 targeted contacts per company using Serper (Google search):
  - 2 HR / Talent Acquisition / Recruiter
  - 2 Software Engineers (same role as applicant)
  - 1 Founder / Co-founder

Each contact is returned with name, title, and LinkedIn URL.
Apollo enriches emails separately.
"""

import re
import time
import logging
import requests
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

SERPER_URL = "https://google.serper.dev/search"

SEARCH_TEMPLATES = {
    "hr": [
        '{company} "talent acquisition" OR "HR" OR "recruiter" OR "human resources" site:linkedin.com/in',
        '{company} "people operations" OR "hiring manager" site:linkedin.com/in',
    ],
    "sde": [
        '{company} "{role}" OR "software engineer" OR "backend engineer" site:linkedin.com/in',
        '{company} "engineer" OR "developer" site:linkedin.com/in',
    ],
    "founder": [
        '{company} "founder" OR "co-founder" OR "CEO" OR "CTO" site:linkedin.com/in',
    ],
}


def find_contacts(
    company: str,
    applicant_role: str,
    serper_api_key: str,
    max_hr: int = 2,
    max_sde: int = 2,
    max_founder: int = 1,
) -> List[Dict[str, Any]]:
    """
    Find up to 5 contacts at a company via Google/Serper.
    Returns list of: {name, title, linkedin_url, contact_type, email}
    """
    contacts = []
    seen_urls = set()

    targets = [
        ("hr",      max_hr,      "HR / Recruiter"),
        ("sde",     max_sde,     applicant_role),
        ("founder", max_founder, "Founder"),
    ]

    for contact_type, limit, label in targets:
        found = 0
        for template in SEARCH_TEMPLATES[contact_type]:
            if found >= limit:
                break
            query = template.format(company=company, role=applicant_role)
            results = _serper_search(query, serper_api_key, num=5)

            for item in results:
                if found >= limit:
                    break
                url     = item.get("link", "")
                title   = item.get("title", "")
                snippet = item.get("snippet", "")

                if "linkedin.com/in/" not in url:
                    continue
                if url in seen_urls:
                    continue

                name      = _extract_name(title)
                job_title = _extract_job_title(title, snippet)

                if not name:
                    continue

                seen_urls.add(url)
                contacts.append({
                    "name":         name,
                    "title":        job_title or label,
                    "linkedin_url": url,
                    "contact_type": contact_type,   # hr | sde | founder
                    "email":        "",             # filled by Apollo
                })
                found += 1
                logger.info(f"  [{contact_type}] {name} — {url}")

            time.sleep(0.5)

    logger.info(f"Contacts found for '{company}': {len(contacts)}")
    return contacts


def _serper_search(query: str, api_key: str, num: int = 5) -> List[Dict]:
    try:
        resp = requests.post(
            SERPER_URL,
            json={"q": query, "num": num},
            headers={"X-API-KEY": api_key},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("organic", [])
    except Exception as e:
        logger.warning(f"Serper search failed for query: {e}")
        return []


def _extract_name(title: str) -> str:
    """
    LinkedIn titles: 'John Doe - SWE at XYZ | LinkedIn'
    Extract just the name part before the first dash/pipe.
    """
    title = re.sub(r"\s*[|\-]?\s*LinkedIn.*$", "", title, flags=re.IGNORECASE).strip()
    parts = re.split(r"\s+[-|]\s+", title)
    name  = parts[0].strip() if parts else ""
    if len(name) > 45 or not re.match(r"^[A-Za-z\s.''-]+$", name):
        return ""
    return name


def _extract_job_title(title: str, snippet: str) -> str:
    m = re.search(r"[-|]\s*([^|\-]+?)\s+(?:at|@)\s+", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()[:80]
    m = re.search(r"(?:Title|Position|Role)[:\s]+([^\n.]+)", snippet, re.IGNORECASE)
    if m:
        return m.group(1).strip()[:80]
    return ""