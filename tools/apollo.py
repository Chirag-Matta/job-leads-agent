"""
tools/apollo.py

Uses Apollo.io API to find work emails for LinkedIn profiles.
Apollo free tier: 50 email credits/month.

Docs: https://apolloio.github.io/apollo-api-docs/
"""

import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)

APOLLO_BASE = "https://api.apollo.io/v1"


def enrich_email(
    linkedin_url: str,
    api_key: str,
    name: str = "",
    company: str = "",
) -> str:
    """
    Given a LinkedIn profile URL, return the work email via Apollo.
    Falls back to name + company search if LinkedIn lookup fails.
    Returns email string or "" if not found.
    """
    # Strategy 1: direct LinkedIn URL lookup
    email = _lookup_by_linkedin(linkedin_url, api_key)
    if email:
        return email

    # Strategy 2: name + company search
    if name and company:
        email = _lookup_by_name_company(name, company, api_key)
        if email:
            return email

    logger.info(f"Apollo: no email found for {name or linkedin_url}")
    return ""


def enrich_contacts(
    contacts: list,
    company: str,
    api_key: str,
) -> list:
    """
    Enrich a list of contacts with emails via Apollo.
    Modifies contacts in-place and returns them.
    """
    for contact in contacts:
        if contact.get("email"):
            continue  # already has email

        email = enrich_email(
            linkedin_url=contact.get("linkedin_url", ""),
            api_key=api_key,
            name=contact.get("name", ""),
            company=company,
        )
        contact["email"] = email
        if email:
            logger.info(f"Apollo enriched: {contact['name']} → {email}")

    return contacts


def _lookup_by_linkedin(linkedin_url: str, api_key: str) -> Optional[str]:
    """Search Apollo by LinkedIn profile URL."""
    if not linkedin_url:
        return None
    try:
        resp = requests.post(
            f"{APOLLO_BASE}/people/match",
            json={
                "linkedin_url": linkedin_url,
                "reveal_personal_emails": False,
                "reveal_phone_number": False,
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
            return person.get("email") or ""
        elif resp.status_code == 422:
            # Not found — expected, not an error
            return None
        else:
            logger.warning(f"Apollo LinkedIn lookup failed: {resp.status_code} {resp.text[:100]}")
            return None
    except Exception as e:
        logger.warning(f"Apollo LinkedIn lookup error: {e}")
        return None


def _lookup_by_name_company(name: str, company: str, api_key: str) -> Optional[str]:
    """Search Apollo by person name + company name."""
    first, *rest = name.strip().split()
    last = " ".join(rest) if rest else ""
    try:
        resp = requests.post(
            f"{APOLLO_BASE}/people/match",
            json={
                "first_name": first,
                "last_name": last,
                "organization_name": company,
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
            return person.get("email") or ""
        return None
    except Exception as e:
        logger.warning(f"Apollo name/company lookup error: {e}")
        return None