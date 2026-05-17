"""
Validator B source allowlist — A's allowlist plus industry reports and news archives.
"""
from app.validation.sources.allowlist_a import ALLOWED_DOMAINS_A

ADDITIONAL_DOMAINS_B: set[str] = {
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "techcrunch.com",
    "crunchbase.com",
    "pitchbook.com",
    "statista.com",
    "mckinsey.com",
    "gartner.com",
    "forrester.com",
}

ALLOWED_DOMAINS_B: set[str] = ALLOWED_DOMAINS_A | ADDITIONAL_DOMAINS_B

SEARCH_GUIDANCE_B = (
    "You may use official sources, SEC filings, Wikipedia, reputable news outlets (Reuters, "
    "Bloomberg, FT, WSJ), industry reports (Gartner, McKinsey), and Crunchbase/PitchBook for "
    "private companies. Challenge the seeded value — look for contradicting evidence."
)
