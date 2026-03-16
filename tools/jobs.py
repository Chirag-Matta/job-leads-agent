"""
tools/jobs.py

Job discovery from multiple free sources:
  1. Wellfound (wellfound.com) — startup-focused job board
  2. Hacker News "Who's Hiring" monthly thread — high quality dev roles
  3. Naukri.com — India-specific job board
  4. LinkedIn Posts (via SerperDev) — hiring posts from founders/recruiters
"""

import re
import time
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


# ─────────────────────────────────────────────────────────────
#  1. WELLFOUND  (startup jobs)
# ─────────────────────────────────────────────────────────────

def search_wellfound(keywords: List[str], location: str = "india") -> List[Dict[str, Any]]:
    """
    Scrape Wellfound job listings for each keyword.
    Returns a list of job dicts.
    """
    results = []
    loc_slug = location.lower().replace(" ", "-")

    for keyword in keywords:
        kw_slug = keyword.lower().replace(" ", "-")
        url = f"https://wellfound.com/jobs?q={kw_slug}&l={loc_slug}"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Wellfound fetch failed for '{keyword}': {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Each job card has a data-test or class pattern — adapt if Wellfound updates HTML
        job_cards = soup.select("div[class*='JobListing']") or soup.select("div[class*='job-listing']")

        if not job_cards:
            # Fallback: find all <a> links that look like job pages
            job_cards = soup.find_all("a", href=re.compile(r"/jobs/\d+"))

        for card in job_cards[:10]:  # cap at 10 per keyword
            title = _text(card.select_one("[class*='title'], h2, h3"))
            company = _text(card.select_one("[class*='company'], [class*='startup']"))
            job_url = _href(card, base="https://wellfound.com")
            description = _text(card.select_one("[class*='description'], p"))

            if not title and not company:
                continue

            results.append({
                "source": "wellfound",
                "title": title or keyword,
                "company": company or "",
                "company_linkedin_url": "",
                "location": location,
                "description": description[:400] if description else "",
                "job_url": job_url or url,
            })

        logger.info(f"Wellfound: found {len(job_cards)} cards for '{keyword}'")
        time.sleep(1)  # be polite

    return results


# ─────────────────────────────────────────────────────────────
#  2. HACKER NEWS — "Who's Hiring" monthly thread
# ─────────────────────────────────────────────────────────────

def get_hn_whos_hiring(keywords: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch the latest HN "Who's Hiring" thread and filter comments
    by keywords. Returns matching job posts.

    HN thread IDs are posted the first weekday of each month.
    We search the Algolia HN API to find the latest thread automatically.
    """
    thread_id = _find_latest_hn_hiring_thread()
    if not thread_id:
        logger.warning("Could not find HN Who's Hiring thread.")
        return []

    url = f"https://hacker-news.firebaseio.com/v0/item/{thread_id}.json"
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        thread = resp.json()
    except Exception as e:
        logger.warning(f"HN thread fetch failed: {e}")
        return []

    comment_ids = thread.get("kids", [])[:50]  # check first 50 comments (was 300 — too slow)
    results = []
    kw_lower = [k.lower() for k in keywords]
    consecutive_failures = 0

    for cid in comment_ids:
        comment = _fetch_hn_comment(cid)
        if not comment:
            consecutive_failures += 1
            if consecutive_failures >= 5:
                logger.warning("HN: 5 consecutive fetch failures, stopping early.")
                break
            continue
        consecutive_failures = 0

        text = comment.get("text", "")
        if not text:
            continue

        text_clean = BeautifulSoup(text, "html.parser").get_text(" ")

        # Filter: must mention at least one keyword
        if not any(kw in text_clean.lower() for kw in kw_lower):
            continue

        # Extract company name (usually the first line / bold text)
        company = _extract_hn_company(text)
        description = text_clean[:500]

        results.append({
            "source": "hn_hiring",
            "title": _best_matching_keyword(text_clean, keywords),
            "company": company,
            "company_linkedin_url": "",
            "location": _extract_location(text_clean),
            "description": description,
            "job_url": f"https://news.ycombinator.com/item?id={cid}",
        })

        if len(results) >= 15:
            break

    logger.info(f"HN Who's Hiring: found {len(results)} matching posts")
    return results


def _find_latest_hn_hiring_thread() -> str | None:
    """Use Algolia HN search API to find the latest Who's Hiring thread ID."""
    try:
        resp = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query": "Ask HN: Who is hiring",
                "tags": "story,ask_hn",
                "hitsPerPage": 5,
            },
            timeout=10,
        )
        hits = resp.json().get("hits", [])
        for hit in hits:
            if "who is hiring" in hit.get("title", "").lower():
                return hit["objectID"]
    except Exception as e:
        logger.warning(f"Algolia search failed: {e}")
    return None


def _fetch_hn_comment(comment_id: int) -> dict:
    try:
        url = f"https://hacker-news.firebaseio.com/v0/item/{comment_id}.json"
        resp = requests.get(url, timeout=3)
        return resp.json() or {}
    except Exception:
        return {}


def _extract_hn_company(html_text: str) -> str:
    """First line of an HN hiring comment is usually 'Company | Location | ...'"""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text(" ").strip()
    first_line = text.split("\n")[0].split("|")[0].strip()
    return first_line[:60] if first_line else "Unknown"


def _extract_location(text: str) -> str:
    patterns = [
        r"\b(remote|onsite|hybrid)\b",
        r"\b(bangalore|mumbai|delhi|hyderabad|pune|chennai|india)\b",
        r"\b(san francisco|new york|london|berlin|singapore)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, text.lower())
        if m:
            return m.group(0).title()
    return "Not specified"


def _best_matching_keyword(text: str, keywords: List[str]) -> str:
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return kw
    return keywords[0] if keywords else "Engineer"


# ─────────────────────────────────────────────────────────────
#  4. LINKEDIN POSTS (via SerperDev Google Search)
# ─────────────────────────────────────────────────────────────

def search_linkedin_posts(
    keywords: List[str],
    locations: List[str],
    serper_api_key: str = "",
) -> List[Dict[str, Any]]:
    """
    Search Google for recent LinkedIn posts about hiring.
    Uses SerperDev API to query: site:linkedin.com/posts "hiring" keyword location
    Returns a list of job dicts.
    """
    if not serper_api_key:
        logger.warning("SERPER_API_KEY not set — skipping LinkedIn post search.")
        return []

    results = []
    locations_str = " OR ".join(f'"{loc}"' for loc in locations)

    for keyword in keywords:
        query = f'site:linkedin.com/posts "hiring" "{keyword}" ({locations_str})'

        try:
            resp = requests.post(
                "https://google.serper.dev/search",
                json={"q": query, "num": 10},
                headers={"X-API-KEY": serper_api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"SerperDev search failed for '{keyword}': {e}")
            continue

        for item in data.get("organic", []):
            title = item.get("title", "")
            snippet = item.get("snippet", "")
            link = item.get("link", "")

            # Extract poster name from title (usually "Name on LinkedIn: ...")
            poster_name = ""
            if " on LinkedIn" in title:
                poster_name = title.split(" on LinkedIn")[0].strip()
            elif " - LinkedIn" in title:
                poster_name = title.split(" - LinkedIn")[0].strip()

            # Try to extract company from snippet
            company = _extract_company_from_snippet(snippet)

            results.append({
                "source": "linkedin_post",
                "title": keyword,
                "company": company or poster_name or "Unknown",
                "company_linkedin_url": "",
                "location": ", ".join(locations),
                "description": snippet[:500] if snippet else title,
                "job_url": link,
                "poster_name": poster_name,
            })

        logger.info(f"LinkedIn Posts: found {len(data.get('organic', []))} results for '{keyword}'")
        time.sleep(0.5)

    return results


def _extract_company_from_snippet(snippet: str) -> str:
    """Try to extract a company name from a LinkedIn post snippet."""
    # Common patterns: "at CompanyName", "@CompanyName", "CompanyName is hiring"
    patterns = [
        r'at\s+([A-Z][A-Za-z0-9\s&.]+?)(?:\s+is|\s+we|\.|,|\s+\-)',
        r'@([A-Z][A-Za-z0-9\s&.]+?)(?:\s|\.|,)',
        r'([A-Z][A-Za-z0-9\s&.]+?)\s+is\s+hiring',
    ]
    for pattern in patterns:
        m = re.search(pattern, snippet)
        if m:
            return m.group(1).strip()[:40]
    return ""


# ─────────────────────────────────────────────────────────────
#  COMBINED SEARCH (called by discovery agent)
# ─────────────────────────────────────────────────────────────

def search_jobs(keywords: List[str], location: str = "india", serper_api_key: str = "") -> List[Dict[str, Any]]:
    """
    Search Wellfound, HN Who's Hiring, Naukri, and LinkedIn Posts.
    Supports comma-separated locations (e.g. "Bangalore, Hyderabad").
    Returns combined, deduplicated results.
    """
    locations = [loc.strip() for loc in location.split(",")]

    wellfound_jobs = []
    naukri_jobs = []

    for loc in locations:
        print(f"  [jobs] Searching Wellfound for '{loc}'...")
        wellfound_jobs.extend(search_wellfound(keywords, loc))

        print(f"  [jobs] Searching Naukri for '{loc}'...")
        naukri_jobs.extend(search_naukri(keywords, loc))

    print("  [jobs] Searching HN Who's Hiring...")
    hn_jobs = get_hn_whos_hiring(keywords)

    print("  [jobs] Searching LinkedIn Posts...")
    linkedin_jobs = search_linkedin_posts(keywords, locations, serper_api_key)

    all_jobs = wellfound_jobs + hn_jobs + naukri_jobs + linkedin_jobs

    # Deduplicate by company name
    seen = set()
    unique = []
    for job in all_jobs:
        key = job["company"].lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(job)

    print(f"  [jobs] Total unique companies found: {len(unique)}")
    return unique


# ─────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────

def _text(el) -> str:
    return el.get_text(strip=True) if el else ""

def _href(el, base: str = "") -> str:
    href = el.get("href", "") if el else ""
    if href and not href.startswith("http"):
        href = base + href
    return href


# ─────────────────────────────────────────────────────────────
#  3. NAUKRI  (India-specific, high volume)
# ─────────────────────────────────────────────────────────────

def search_naukri(keywords: List[str], location: str = "india") -> List[Dict[str, Any]]:
    """
    Scrape Naukri.com job listings for each keyword.
    Naukri URL format: naukri.com/{keyword-slug}-jobs-in-{location-slug}
    Returns a list of job dicts.
    """
    results = []
    loc_slug = location.lower().replace(" ", "-")

    # Naukri needs slightly different headers to avoid blocks
    naukri_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.naukri.com/",
    }

    for keyword in keywords:
        kw_slug = keyword.lower().replace(" ", "-")
        url = f"https://www.naukri.com/{kw_slug}-jobs-in-{loc_slug}"

        try:
            resp = requests.get(url, headers=naukri_headers, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"Naukri fetch failed for '{keyword}': {e}")
            continue

        soup = BeautifulSoup(resp.text, "html.parser")

        # Naukri job cards use article tags or specific class patterns
        job_cards = (
            soup.select("article.jobTuple") or
            soup.select("div.jobTuple") or
            soup.select("div[class*='job-card']") or
            soup.select("div[class*='srp-jobtuple']")
        )

        if not job_cards:
            # Fallback: find job title links
            job_cards = soup.find_all("a", {"class": re.compile(r"title|jobTitle", re.I)})

        for card in job_cards[:10]:
            title   = _text(card.select_one("a.title, a[class*='title'], h2"))
            company = _text(card.select_one("a.subTitle, a[class*='company'], [class*='comp-name']"))
            loc     = _text(card.select_one("li.location, span[class*='location'], [class*='loc']"))
            exp     = _text(card.select_one("li.experience, span[class*='experience']"))
            job_url = _href(card.select_one("a.title, a[class*='title']"), base="https://www.naukri.com")

            if not title and not company:
                continue

            results.append({
                "source":              "naukri",
                "title":               title or keyword,
                "company":             company or "",
                "company_linkedin_url": "",
                "location":            loc or location,
                "description":         f"Experience: {exp}" if exp else "",
                "job_url":             job_url or url,
            })

        logger.info(f"Naukri: found {len(job_cards)} cards for '{keyword}'")
        time.sleep(1.5)  # Naukri rate-limits aggressively — be polite

    return results