"""
Validator A source allowlist.
Permitted: company own domain, SEC EDGAR, official regulators, Wikipedia.
"""

ALLOWED_DOMAINS_A: set[str] = {
    "sec.gov",
    "efts.sec.gov",
    "www.sec.gov",
    "en.wikipedia.org",
    # Major regulators
    "fca.org.uk",
    "dnb.nl",
    "afm.nl",
    "eba.europa.eu",
    "esma.europa.eu",
    "bafin.de",
    "finra.org",
    "occ.gov",
    "federalreserve.gov",
    "fdic.gov",
    "ftc.gov",
    "mas.gov.sg",
    "apra.gov.au",
}

SEARCH_GUIDANCE_A = (
    "Only use information from the company's official website, SEC EDGAR filings, "
    "official government regulator websites, or Wikipedia for non-disputable facts. "
    "Do not use social media, blogs, or unverified third-party sources."
)
