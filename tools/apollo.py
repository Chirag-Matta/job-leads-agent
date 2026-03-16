"""
tools/apollo.py

Uses Apollo.io API to find work emails.
Free tier uses /people/search which works without a paid plan.
"""

import logging
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

APOLLO_BASE = "https://api.apollo.io/v1"


def enrich_contacts(
    contacts: List[Dict],
    company: str,
    api_key: str,
) -> List[Dict]:
    """
    Enrich a list of contacts with emails via Apollo.
    Tries multiple strategies per contact.
    Modifies contacts in-place and returns them.
    """
    for contact in contacts:
        if contact.get("email"):
            continue

        name    = contact.get("name", "")
        li_url  = contact.get("linkedin_url", "")

        email = (
            _search_by_name_company(name, company, api_key)
            or _search_by_linkedin(li_url, api_key)
        )

        contact["email"] = email or ""
        status = f"found: {email}" if email else "not found"
        logger.info(f"Apollo [{name}] — {status}")

    return contacts


def enrich_email(
    linkedin_url: str,
    api_key: str,
    name: str = "",
    company: str = "",
) -> str:
    return (
        _search_by_name_company(name, company, api_key)
        or _search_by_linkedin(linkedin_url, api_key)
        or ""
    )


# ── Strategy 1: people/search by name + company (free tier) ──

def _search_by_name_company(name: str, company: str, api_key: str) -> Optional[str]:
    """
    Uses Apollo /people/search — works on free tier.
    Searches by person name + organization name.
    """
    if not name or not company:
        return None

    parts      = name.strip().split()
    first_name = parts[0] if parts else ""
    last_name  = " ".join(parts[1:]) if len(parts) > 1 else ""

    try:
        resp = requests.post(
            f"{APOLLO_BASE}/mixed_people/search",
            json={
                "q_organization_name": company,
                "q_keywords": name,
                "person_titles": [],
                "page": 1,
                "per_page": 5,
            },
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": api_key,
            },
            timeout=10,
        )

        if resp.status_code != 200:
            logger.warning(f"Apollo search failed ({resp.status_code}): {resp.text[:100]}")
            return None

        people = resp.json().get("people", [])
        for person in people:
            # Match by name similarity
            p_first = person.get("first_name", "").lower()
            p_last  = person.get("last_name", "").lower()
            if first_name.lower() in p_first or (last_name and last_name.lower() in p_last):
                email = person.get("email") or _reveal_email(person.get("id", ""), api_key)
                if email:
                    return email

    except Exception as e:
        logger.warning(f"Apollo people/search error: {e}")

    return None


# ── Strategy 2: people/match by LinkedIn URL ──────────────────

def _search_by_linkedin(linkedin_url: str, api_key: str) -> Optional[str]:
    """
    Uses Apollo /people/match by LinkedIn URL.
    May require paid plan for full email reveal,
    but returns partial data on free tier.
    """
    if not linkedin_url or "linkedin.com/in/" not in linkedin_url:
        return None

    try:
        resp = requests.post(
            f"{APOLLO_BASE}/people/match",
            json={
                "linkedin_url": linkedin_url,
                "reveal_personal_emails": False,
            },
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "X-Api-Key": api_key,
            },
            timeout=10,
        )

        if resp.status_code == 200:
            person = resp.json().get("person", {})
            return person.get("email") or None

    except Exception as e:
        logger.warning(f"Apollo people/match error: {e}")

    return None


# ── Strategy 3: reveal email by person ID ─────────────────────

def _reveal_email(person_id: str, api_key: str) -> Optional[str]:
    """Request email reveal for a known Apollo person ID."""
    if not person_id:
        return None
    try:
        resp = requests.post(
            f"{APOLLO_BASE}/people/bulk_match",
            json={"details": [{"id": person_id}]},
            headers={
                "Content-Type": "application/json",
                "X-Api-Key": api_key,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            matches = resp.json().get("matches", [])
            if matches:
                return matches[0].get("email") or None
    except Exception:
        pass
    return None