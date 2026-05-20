"""Free domain-level enrichment for a scraped business.

Two free public sources:
- RDAP (rdap.org) — modern WHOIS over HTTPS. No key, no rate-limit on
  reasonable use. Returns registration date + registrar.
- DNS MX records via dnspython — tells us what mail provider the business
  is using (Google Workspace, Microsoft 365, self-hosted, none).

Both stable enough to cache results for months. The bot stores enrichment
in a side-table on GitHub keyed by domain, so subsequent runs reuse the
data without re-querying.
"""

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import requests


# ── domain extraction ────────────────────────────────────────

_STRIP_WWW = re.compile(r"^www\.", re.I)


def extract_domain(website: str) -> str:
    """Best-effort: 'https://www.biz.com/about?x=1' → 'biz.com'."""
    if not website:
        return ""
    website = website.strip()
    if not website:
        return ""
    if not website.startswith(("http://", "https://")):
        website = "http://" + website
    try:
        host = urlparse(website).hostname or ""
    except ValueError:
        return ""
    host = _STRIP_WWW.sub("", host).lower()
    # Sanity-check: must look like at least 'x.y'
    if "." not in host or len(host) < 4:
        return ""
    return host


# ── RDAP ─────────────────────────────────────────────────────

def get_rdap(domain: str, timeout: float = 10.0) -> Optional[dict]:
    """Query rdap.org. Returns a dict with 'registration_date' and 'registrar'
    (both strings, possibly empty), or None on failure."""
    if not domain:
        return None
    try:
        resp = requests.get(
            f"https://rdap.org/domain/{domain}",
            headers={"Accept": "application/rdap+json", "User-Agent": "dotco-bot"},
            timeout=timeout,
        )
    except requests.RequestException:
        return None
    if not resp.ok:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None

    # Registration date
    reg_date = ""
    for e in data.get("events", []):
        if e.get("eventAction") == "registration":
            reg_date = e.get("eventDate", "") or ""
            break

    # Registrar — RDAP nests it inside entities with role=registrar
    registrar = ""
    for ent in data.get("entities", []):
        roles = ent.get("roles") or []
        if "registrar" in roles:
            # vcard-style array: [["fn", {}, "text", "GoDaddy.com, LLC"], ...]
            for v in (ent.get("vcardArray") or [None, []])[1]:
                if isinstance(v, list) and len(v) >= 4 and v[0] == "fn":
                    registrar = str(v[3])
                    break
            if registrar:
                break

    return {"registration_date": reg_date, "registrar": registrar}


def years_since(iso_date: str) -> Optional[int]:
    """RDAP dates look like '2014-03-22T16:14:32Z'. Return whole years; None on bad input."""
    if not iso_date:
        return None
    try:
        # Handle the 'Z' suffix manually for older Python compatibility.
        when = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - when
    return max(0, delta.days // 365)


# ── DNS MX ───────────────────────────────────────────────────

def get_mx_hosts(domain: str, timeout: float = 5.0) -> list[str]:
    """Return MX exchange hostnames (lowercase, trailing dot stripped). Empty on failure."""
    if not domain:
        return []
    try:
        import dns.resolver
    except ImportError:
        return []
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        answers = resolver.resolve(domain, "MX")
    except Exception:
        return []
    out = []
    for r in answers:
        host = str(r.exchange).rstrip(".").lower()
        if host:
            out.append(host)
    return out


_GOOGLE_PATTERNS = ("google.com", "googlemail.com", "gmail-smtp", "aspmx.l.google.com")
_MS_PATTERNS = ("outlook.com", "protection.outlook.com", "mail.protection.outlook.com",
                "office365.com", "microsoft.com")


def classify_mx_provider(mx_hosts: list[str]) -> str:
    """Map a list of MX hostnames to a coarse 'provider' label."""
    if not mx_hosts:
        return "none"
    joined = " ".join(mx_hosts)
    if any(p in joined for p in _GOOGLE_PATTERNS):
        return "google_workspace"
    if any(p in joined for p in _MS_PATTERNS):
        return "microsoft365"
    return "other"


# ── high-level ───────────────────────────────────────────────

def enrich_domain(domain: str) -> dict:
    """Combine RDAP + DNS into one row of enrichment data. Always returns a dict
    with all expected keys (empty values when a lookup failed)."""
    rdap = get_rdap(domain) or {}
    mx_hosts = get_mx_hosts(domain)
    age = years_since(rdap.get("registration_date", "")) if rdap else None
    return {
        "domain": domain,
        "domain_age_years": str(age) if age is not None else "",
        "registrar": rdap.get("registrar", "") or "",
        "mx_provider": classify_mx_provider(mx_hosts),
        "mx_hosts": " | ".join(mx_hosts[:3]),  # cap at 3 for CSV cleanliness
        "last_checked_iso": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
