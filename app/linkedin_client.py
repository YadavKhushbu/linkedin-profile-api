import os
import re
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

PROFICIENCY_MAP = {
    "NATIVE_OR_BILINGUAL": "Native or Bilingual",
    "FULL_PROFESSIONAL": "Full Professional",
    "PROFESSIONAL_WORKING": "Professional Working",
    "LIMITED_WORKING": "Limited Working",
    "ELEMENTARY": "Elementary",
}


class LinkedInAuthError(Exception):
    pass


class LinkedInRateLimitError(Exception):
    pass


class LinkedInProfileNotFoundError(Exception):
    pass


class LinkedInClient:
    BASE_URL = "https://www.linkedin.com"
    VOYAGER_BASE = "https://www.linkedin.com/voyager/api"

    def __init__(self):
        self.li_at = os.environ.get("LI_AT", "")
        if not self.li_at:
            raise LinkedInAuthError("LI_AT environment variable is not set")
        self.session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.cookies.set("li_at", self.li_at, domain=".linkedin.com")
        # Derive CSRF token from JSESSIONID (set during first request)
        session.headers.update({
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
        csrf = self._fetch_csrf_token(session)
        session.headers["csrf-token"] = csrf
        session.cookies.set("JSESSIONID", f'"{csrf}"', domain=".linkedin.com")
        return session

    def _fetch_csrf_token(self, session: requests.Session) -> str:
        """Fetch the home page to obtain a JSESSIONID / CSRF token."""
        resp = session.get(self.BASE_URL, timeout=15)
        for cookie in resp.cookies:
            if cookie.name == "JSESSIONID":
                return cookie.value.strip('"')
        # Fallback: parse from response body
        match = re.search(r'"JSESSIONID":"([^"]+)"', resp.text)
        if match:
            return match.group(1).strip('"')
        raise LinkedInAuthError(
            "Could not obtain CSRF token. Check that your LI_AT cookie is valid."
        )

    def _voyager_get(self, path: str, params: Optional[dict] = None) -> dict:
        url = f"{self.VOYAGER_BASE}{path}"
        resp = self.session.get(url, params=params, timeout=20)

        if resp.status_code == 401 or resp.status_code == 403:
            raise LinkedInAuthError(
                "LinkedIn returned 401/403 — your LI_AT cookie may have expired."
            )
        if resp.status_code == 404:
            raise LinkedInProfileNotFoundError("Profile not found.")
        if resp.status_code == 429 or resp.status_code == 999:
            raise LinkedInRateLimitError(
                "LinkedIn is rate-limiting requests. Please wait and try again."
            )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _extract_username(url: str) -> str:
        match = re.search(r"linkedin\.com/in/([^/?#\s]+)", url.strip())
        if not match:
            raise ValueError(f"Invalid LinkedIn profile URL: {url!r}")
        return match.group(1).rstrip("/")

    def get_profile(self, profile_url: str) -> dict:
        username = self._extract_username(profile_url)
        profile_view = self._voyager_get(f"/identity/profiles/{username}/profileView")
        skills = self._fetch_skills(username)
        return self._parse_profile(profile_view, skills, username)

    def _fetch_skills(self, username: str) -> list:
        try:
            data = self._voyager_get(
                f"/identity/profiles/{username}/skills",
                params={"count": 100, "start": 0},
            )
            return data.get("elements", [])
        except Exception:
            return []

    # ── Parsing ──────────────────────────────────────────────────────────────

    def _parse_profile(self, data: dict, skills_data: list, username: str) -> dict:
        profile = data.get("profile", {})
        return {
            "username": username,
            "profile_url": f"https://www.linkedin.com/in/{username}",
            "name": f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip(),
            "headline": profile.get("headline"),
            "location": profile.get("locationName"),
            "about": profile.get("summary"),
            "industry": profile.get("industryName"),
            "profile_image": self._extract_image(profile),
            "followers": self._extract_followers(data),
            "connections": self._extract_connections(profile),
            "experience": self._parse_positions(
                data.get("positionView", {}).get("elements", [])
            ),
            "education": self._parse_education(
                data.get("educationView", {}).get("elements", [])
            ),
            "skills": self._parse_skills(
                data.get("skillView", {}).get("elements", []), skills_data
            ),
            "certifications": self._parse_certifications(
                data.get("certificationView", {}).get("elements", [])
            ),
            "languages": self._parse_languages(
                data.get("languageView", {}).get("elements", [])
            ),
        }

    @staticmethod
    def _extract_image(profile: dict) -> Optional[str]:
        try:
            vec = (
                profile.get("profilePicture", {})
                .get("displayImageReference", {})
                .get("vectorImage", {})
            )
            root = vec.get("rootUrl", "")
            artifacts = vec.get("artifacts", [])
            if root and artifacts:
                largest = max(artifacts, key=lambda a: a.get("width", 0))
                return root + largest.get("fileIdentifyingUrlPathSegment", "")
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_followers(data: dict) -> Optional[int]:
        try:
            return data.get("profile", {}).get("followingInfo", {}).get("followerCount")
        except Exception:
            return None

    @staticmethod
    def _extract_connections(profile: dict) -> Optional[str]:
        try:
            count = profile.get("connectionsCount")
            if count is not None:
                return str(count) if count < 500 else "500+"
        except Exception:
            pass
        return None

    @staticmethod
    def _parse_date(period: Optional[dict]) -> Optional[str]:
        if not period:
            return None
        year = period.get("year")
        month = period.get("month")
        if year and month:
            return f"{year}-{month:02d}"
        if year:
            return str(year)
        return None

    def _parse_positions(self, positions: list) -> list:
        result = []
        for pos in positions:
            mini = pos.get("company", {}).get("miniCompany", {})
            tp = pos.get("timePeriod", {})
            result.append({
                "title": pos.get("title"),
                "company": pos.get("companyName") or mini.get("name"),
                "company_linkedin_url": (
                    f"https://www.linkedin.com/company/{mini['universalName']}"
                    if mini.get("universalName")
                    else None
                ),
                "location": pos.get("locationName"),
                "description": pos.get("description"),
                "start_date": self._parse_date(tp.get("startDate")),
                "end_date": self._parse_date(tp.get("endDate")),
                "is_current": not bool(tp.get("endDate")),
            })
        return result

    def _parse_education(self, education: list) -> list:
        result = []
        for edu in education:
            tp = edu.get("timePeriod", {})
            result.append({
                "school": edu.get("schoolName"),
                "degree": edu.get("degreeName"),
                "field_of_study": edu.get("fieldOfStudy"),
                "description": edu.get("description"),
                "start_date": self._parse_date(tp.get("startDate")),
                "end_date": self._parse_date(tp.get("endDate")),
            })
        return result

    @staticmethod
    def _parse_skills(skill_view: list, skills_data: list) -> list:
        source = skills_data if skills_data else skill_view
        return [{"name": s["name"]} for s in source if s.get("name")]

    def _parse_certifications(self, certs: list) -> list:
        result = []
        for cert in certs:
            tp = cert.get("timePeriod", {})
            result.append({
                "name": cert.get("name"),
                "issuing_organization": cert.get("authority"),
                "credential_id": cert.get("licenseNumber"),
                "credential_url": cert.get("url"),
                "issue_date": self._parse_date(tp.get("startDate")),
                "expiry_date": self._parse_date(tp.get("endDate")),
            })
        return result

    @staticmethod
    def _parse_languages(languages: list) -> list:
        result = []
        for lang in languages:
            proficiency = lang.get("proficiency", "")
            result.append({
                "name": lang.get("name"),
                "proficiency": PROFICIENCY_MAP.get(proficiency, proficiency) or None,
            })
        return result
