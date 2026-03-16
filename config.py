from dotenv import load_dotenv
load_dotenv()

import os
from dataclasses import dataclass, field
from typing import List

@dataclass
class Config:
    # ── API Keys ───────────────────────────────────────────
    groq_api_key: str       = os.getenv("GROQ_API_KEY", "")
    serper_api_key: str     = os.getenv("SERPER_API_KEY", "")
    apollo_api_key: str     = os.getenv("APOLLO_API_KEY", "")
    notion_api_key: str     = os.getenv("NOTION_API_KEY", "")
    gmail_sender: str       = os.getenv("GMAIL_SENDER", "")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")

    # ── LLM ───────────────────────────────────────────────
    model: str = "llama-3.3-70b-versatile"

    # ── Job Search Preferences ─────────────────────────────
    job_roles: List[str] = field(default_factory=lambda: [
        "Backend Engineer",
        "Software Engineer",
    ])
    target_company_types: List[str] = field(default_factory=lambda: [
        "startup",
        "product-based",
    ])
    target_domains: List[str] = field(default_factory=lambda: [
        "AI / ML",
        "Fintech",
    ])
    preferred_company_size: List[str] = field(default_factory=lambda: [
        "early-stage",
        "mid-size",
    ])
    preferred_locations: List[str] = field(default_factory=lambda: [
        "Bangalore",
        "Hyderabad",
    ])
    open_to_remote: bool = True
    work_mode: str = "any"
    experience_level: str = "junior"
    excluded_companies: List[str] = field(default_factory=lambda: [])
    max_companies_per_run: int = 5

    # ── Your Details ───────────────────────────────────────
    your_name: str        = "Chirag Matta"
    your_role: str        = "Backend Engineer"
    your_linkedin: str    = "https://www.linkedin.com/in/chirag-matta-a2aa30232/"
    your_github: str      = "https://github.com/Chirag-Matta"
    your_resume_link: str = "https://drive.google.com/file/d/1K5cabX_ovP4GHqCyI6GbKjGPY8hE9UFe/view?usp=sharing"

config = Config()