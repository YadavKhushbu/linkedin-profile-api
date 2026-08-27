import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .linkedin_client import (
    LinkedInClient,
    LinkedInAuthError,
    LinkedInRateLimitError,
    LinkedInProfileNotFoundError,
)
from .models import ProfileResponse, HealthResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_client: LinkedInClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _client
    try:
        _client = LinkedInClient()
        logger.info("LinkedIn client initialized successfully.")
    except LinkedInAuthError as e:
        logger.error(f"LinkedIn auth failed on startup: {e}")
    yield
    _client = None


app = FastAPI(
    title="LinkedIn Profile API",
    description=(
        "Reverse-engineered LinkedIn Voyager API wrapper. "
        "Accepts a LinkedIn profile URL and returns structured JSON."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/", tags=["meta"])
def root():
    return {
        "name": "LinkedIn Profile API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "profile_endpoint": "/profile?url=https://www.linkedin.com/in/williamhgates",
    }


@app.get("/health", response_model=HealthResponse, tags=["meta"])
def health():
    return HealthResponse(status="ok", authenticated=_client is not None)


@app.get("/profile", response_model=ProfileResponse, tags=["profile"])
def get_profile(
    url: str = Query(
        ...,
        description="Full LinkedIn profile URL, e.g. https://www.linkedin.com/in/williamhgates",
        example="https://www.linkedin.com/in/williamhgates",
    )
):
    if _client is None:
        raise HTTPException(
            status_code=503,
            detail="LinkedIn client is not initialized. Check that LI_AT is set and valid.",
        )

    try:
        data = _client.get_profile(url)
        return ProfileResponse(success=True, data=data)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except LinkedInProfileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except LinkedInAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    except LinkedInRateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))

    except Exception as e:
        logger.exception("Unexpected error fetching profile")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e}")
