import os
import re
import logging
from typing import Optional
import requests

logger = logging.getLogger(__name__)

PROFICIENCY_MAP = {
    "NATIVE_OR_BILINGUAL": "Native or Bilingual",
    "FULL_PROFESSIONAL": "Full Professional",
    "PROFESSIONAL_WORKING": "Professional Working",
    "LIMITED_WORKING": "Limited Working",
    "ELEMENTARY": "Elementary",
}

DASH_DECORATIONS = [
    "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-93",
    "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-91",
    "com.linkedin.voyager.dash.deco.identity.profile.FullProfileWithEntities-95",
]


class LinkedInAuthError(Exception):
    pass


class LinkedInRateLimitError(Exception):
    pass


class LinkedInProfileNotFoundError(Exception):
    pass


class LinkedInClient:
    BASE_URL = "https://www.linkedin.com"
    VOYAGER = "https://www.linkedin.com/voyager/api"

    def __init__(self):
        self.li_at = os.environ.get("LI_AT", "")
        if not self.li_at:
            raise LinkedInAuthError("LI_AT environment variable is not set")
        self.session = self._build_session()

    # ── Session ───────────────────────────────────────────────────────────────

    def _build_session(self) -> requests.Session:
        s = requests.Session()
        s.max_redirects = 5
        s.cookies.set("li_at", self.li_at, domain=".linkedin.com")
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "X-Li-Lang": "en_US",
            "X-RestLi-Protocol-Version": "2.0.0",
            "Accept": "application/vnd.linkedin.normalized+json+2.1",
        })
        csrf = self._fetch_csrf(s)
        s.headers["csrf-token"] = csrf
        s.cookies.set("JSESSIONID", f'"{csrf}"', domain=".linkedin.com")
        return s

    def _fetch_csrf(self, session: requests.Session) -> str:
        try:
            resp = session.get(f"{self.BASE_URL}/feed/", timeout=15)
        except requests.TooManyRedirects:
            raise LinkedInAuthError(
                "Too many redirects — your LI_AT cookie is likely expired. "
                "Copy a fresh one from your browser."
            )
        for c in list(resp.cookies) + list(session.cookies):
            if c.name == "JSESSIONID":
                return c.value.strip('"')
        raise LinkedInAuthError(
            "Could not obtain CSRF token. Ensure LI_AT is valid and not expired."
        )

    # ── HTTP ──────────────────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> Optional[requests.Response]:
        url = f"{self.VOYAGER}{path}"
        resp = self.session.get(url, params=params, timeout=20)
        if resp.status_code in (401, 403):
            raise LinkedInAuthError("Session expired — refresh your LI_AT cookie.")
        if resp.status_code == 404:
            raise LinkedInProfileNotFoundError("Profile not found.")
        if resp.status_code in (429, 999):
            raise LinkedInRateLimitError("Rate limited by LinkedIn. Wait and retry.")
        if resp.status_code != 200:
            logger.debug("GET %s → %s", path, resp.status_code)
            return None
        return resp

    # ── Public ────────────────────────────────────────────────────────────────

    def get_profile(self, profile_url: str) -> dict:
        username = self._extract_username(profile_url)

        for decoration in DASH_DECORATIONS:
            resp = self._get(
                "/identity/dash/profiles",
                params={
                    "q": "memberIdentity",
                    "memberIdentity": username,
                    "decorationId": decoration,
                },
            )
            if resp is None:
                continue
            data = resp.json()
            included = data.get("included", [])
            if not included:
                continue
            result = self._parse(included, username)
            if result["name"] and result["name"] != username:
                return result

        raise RuntimeError(
            "Could not retrieve profile data. "
            "The profile may be private or LinkedIn's API may have changed."
        )

    # ── Parser ────────────────────────────────────────────────────────────────

    def _parse(self, entities: list, username: str) -> dict:
        # Index all entities by URN for cross-referencing
        by_urn: dict = {e["entityUrn"]: e for e in entities if e.get("entityUrn")}

        # Find entities by their exact type name (last segment of $type)
        profile    = self._by_type(entities, "Profile")
        positions  = self._all_by_type(entities, "Position")
        educations = self._all_by_type(entities, "Education")
        skills     = self._all_by_type(entities, "Skill")
        certs      = self._all_by_type(entities, "Certification")
        langs      = self._all_by_type(entities, "Language")

        return {
            "username": username,
            "profile_url": f"https://www.linkedin.com/in/{username}",
            "name": f"{profile.get('firstName','')} {profile.get('lastName','')}".strip() or username,
            "headline": profile.get("headline"),
            "location": self._resolve_location(profile, by_urn),
            "about": profile.get("summary"),
            "industry": self._resolve_industry(profile, by_urn),
            "profile_image": self._resolve_image(profile),
            "followers": None,
            "connections": None,
            "experience": [self._parse_position(p, by_urn) for p in positions],
            "education": [self._parse_education(e) for e in educations],
            "skills": [{"name": s["name"]} for s in skills if s.get("name")],
            "certifications": [self._parse_cert(c) for c in certs],
            "languages": [self._parse_lang(la) for la in langs],
        }

    # ── Entity finders ────────────────────────────────────────────────────────

    @staticmethod
    def _type_name(entity: dict) -> str:
        """Return the final segment of $type, e.g. 'Profile', 'Position'."""
        return entity.get("$type", "").rsplit(".", 1)[-1]

    def _by_type(self, entities: list, name: str) -> dict:
        return next((e for e in entities if self._type_name(e) == name), {})

    def _all_by_type(self, entities: list, name: str) -> list:
        return [e for e in entities if self._type_name(e) == name]

    # ── Field resolvers ───────────────────────────────────────────────────────

    @staticmethod
    def _resolve_location(profile: dict, by_urn: dict) -> Optional[str]:
        if profile.get("locationName"):
            return profile["locationName"]
        # geoLocation.*geo is a URN reference to a Geo entity
        geo_urn = (profile.get("geoLocation") or {}).get("*geo")
        if geo_urn and geo_urn in by_urn:
            return by_urn[geo_urn].get("defaultLocalizedName")
        return None

    @staticmethod
    def _resolve_industry(profile: dict, by_urn: dict) -> Optional[str]:
        ind_urn = profile.get("industryUrn") or (profile.get("*industry"))
        if ind_urn and ind_urn in by_urn:
            return by_urn[ind_urn].get("name")
        return None

    @staticmethod
    def _resolve_image(profile: dict) -> Optional[str]:
        try:
            vec = (
                (profile.get("profilePicture") or {})
                .get("displayImageReference", {})
                .get("vectorImage", {})
            )
            root = vec.get("rootUrl", "")
            arts = vec.get("artifacts", [])
            if root and arts:
                largest = max(arts, key=lambda a: a.get("width", 0))
                return root + largest["fileIdentifyingUrlPathSegment"]
        except Exception:
            pass
        return None

    @staticmethod
    def _fmt_date(d: Optional[dict]) -> Optional[str]:
        """Parse {year, month} dict → 'YYYY-MM' or 'YYYY'."""
        if not d:
            return None
        year = d.get("year")
        month = d.get("month")
        if year and month:
            return f"{year}-{int(month):02d}"
        return str(year) if year else None

    # ── Section parsers ───────────────────────────────────────────────────────

    def _parse_position(self, pos: dict, by_urn: dict) -> dict:
        dr = pos.get("dateRange") or {}
        start = dr.get("start") or {}
        end = dr.get("end")

        # Resolve company LinkedIn URL from URN
        company_urn = pos.get("companyUrn")
        company_entity = by_urn.get(company_urn, {})
        company_url = company_entity.get("url")

        return {
            "title": pos.get("title"),
            "company": pos.get("companyName"),
            "company_linkedin_url": company_url,
            "location": pos.get("locationName"),
            "description": pos.get("description"),
            "start_date": self._fmt_date(start),
            "end_date": self._fmt_date(end),
            "is_current": not bool(end),
        }

    def _parse_education(self, edu: dict) -> dict:
        dr = edu.get("dateRange") or {}
        return {
            "school": edu.get("schoolName"),
            "degree": edu.get("degreeName"),
            "field_of_study": edu.get("fieldOfStudy"),
            "description": edu.get("description") or edu.get("activities"),
            "start_date": self._fmt_date(dr.get("start")),
            "end_date": self._fmt_date(dr.get("end")),
        }

    def _parse_cert(self, c: dict) -> dict:
        dr = c.get("dateRange") or {}
        return {
            "name": c.get("name"),
            "issuing_organization": c.get("authority"),
            "credential_id": c.get("licenseNumber"),
            "credential_url": c.get("url"),
            "issue_date": self._fmt_date(dr.get("start")),
            "expiry_date": self._fmt_date(dr.get("end")),
        }

    @staticmethod
    def _parse_lang(la: dict) -> dict:
        p = la.get("proficiency", "")
        return {"name": la.get("name"), "proficiency": PROFICIENCY_MAP.get(p, p) or None}

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_username(url: str) -> str:
        m = re.search(r"linkedin\.com/in/([^/?#\s]+)", url.strip())
        if not m:
            raise ValueError(f"Invalid LinkedIn profile URL: {url!r}")
        return m.group(1).rstrip("/")
