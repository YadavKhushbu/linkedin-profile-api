from pydantic import BaseModel
from typing import Optional, List


class Experience(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False


class Education(BaseModel):
    school: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class Skill(BaseModel):
    name: str


class Certification(BaseModel):
    name: Optional[str] = None
    issuing_organization: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None


class Language(BaseModel):
    name: Optional[str] = None
    proficiency: Optional[str] = None


class ProfileData(BaseModel):
    username: str
    profile_url: str
    name: str
    headline: Optional[str] = None
    location: Optional[str] = None
    about: Optional[str] = None
    industry: Optional[str] = None
    profile_image: Optional[str] = None
    followers: Optional[int] = None
    connections: Optional[str] = None
    experience: List[Experience] = []
    education: List[Education] = []
    skills: List[Skill] = []
    certifications: List[Certification] = []
    languages: List[Language] = []


class ProfileResponse(BaseModel):
    success: bool
    data: Optional[ProfileData] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    authenticated: bool
