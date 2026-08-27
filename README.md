# LinkedIn Profile API

A hosted REST API that accepts a LinkedIn profile URL and returns structured JSON containing the publicly visible information on that profile page.

**Live API:** `https://linkedin-profile-api.onrender.com`

---

## Quick Start

```bash
curl "https://linkedin-profile-api.onrender.com/profile?url=https://www.linkedin.com/in/williamhgates"
```

---

## API Documentation

### `GET /profile`

Returns structured profile data for a LinkedIn user.

**Query Parameters**

| Parameter | Type   | Required | Description                          |
|-----------|--------|----------|--------------------------------------|
| `url`     | string | Yes      | Full LinkedIn profile URL            |

**Example Request**

```
GET /profile?url=https://www.linkedin.com/in/williamhgates
```

**Example Response**

```json
{
  "success": true,
  "data": {
    "username": "williamhgates",
    "profile_url": "https://www.linkedin.com/in/williamhgates",
    "name": "Bill Gates",
    "headline": "Co-chair, Bill & Melinda Gates Foundation",
    "location": "Seattle, Washington, United States",
    "about": "Co-chair of the Bill & Melinda Gates Foundation...",
    "industry": "Philanthropic Fundraising Services",
    "profile_image": "https://media.licdn.com/dms/image/...",
    "followers": 35600000,
    "connections": "500+",
    "experience": [
      {
        "title": "Co-chair",
        "company": "Bill & Melinda Gates Foundation",
        "company_linkedin_url": "https://www.linkedin.com/company/bill-melinda-gates-foundation",
        "location": "Seattle, Washington",
        "description": null,
        "start_date": "2000-01",
        "end_date": null,
        "is_current": true
      }
    ],
    "education": [
      {
        "school": "Harvard University",
        "degree": null,
        "field_of_study": null,
        "description": null,
        "start_date": "1973",
        "end_date": "1975"
      }
    ],
    "skills": [
      { "name": "Public Speaking" },
      { "name": "Philanthropy" }
    ],
    "certifications": [],
    "languages": [
      { "name": "English", "proficiency": "Native or Bilingual" }
    ]
  }
}
```

**Response Schema**

| Field           | Type            | Description                                          |
|-----------------|-----------------|------------------------------------------------------|
| `username`      | string          | LinkedIn slug extracted from the URL                 |
| `profile_url`   | string          | Canonical LinkedIn profile URL                       |
| `name`          | string          | Full name                                            |
| `headline`      | string \| null  | Professional headline                                |
| `location`      | string \| null  | Location string                                      |
| `about`         | string \| null  | About / summary section                              |
| `industry`      | string \| null  | Industry                                             |
| `profile_image` | string \| null  | URL of the largest available profile photo           |
| `followers`     | int \| null     | Follower count (when publicly available)             |
| `connections`   | string \| null  | Connection count or `"500+"` when capped             |
| `experience`    | array           | Work history (see below)                             |
| `education`     | array           | Education history                                    |
| `skills`        | array           | Skill names                                          |
| `certifications`| array           | Certifications / licences                            |
| `languages`     | array           | Languages and proficiency levels                     |

**Experience item fields:** `title`, `company`, `company_linkedin_url`, `location`, `description`, `start_date` (YYYY-MM or YYYY), `end_date`, `is_current`

**Error Responses**

| HTTP Status | Meaning                                         |
|-------------|-------------------------------------------------|
| 400         | Invalid or unparseable LinkedIn URL             |
| 401         | LinkedIn session cookie expired                 |
| 404         | Profile not found                               |
| 429         | LinkedIn rate limit hit — retry after a moment  |
| 503         | Server not initialized (check env vars)         |

### `GET /health`

```json
{ "status": "ok", "authenticated": true }
```

### `GET /docs`

Interactive Swagger UI.

---

## Approach

LinkedIn does not offer a public API for profile data. This project **reverse-engineers LinkedIn's internal Voyager API** — the same JSON API that LinkedIn's own web front-end uses.

### Authentication

LinkedIn authenticates Voyager API calls via two pieces:

1. **`li_at` cookie** — the long-lived session token written to the browser after login. This is supplied via the `LI_AT` environment variable.
2. **CSRF token** — on startup the server makes a single GET request to `linkedin.com` with the `li_at` cookie. LinkedIn responds by setting a `JSESSIONID` cookie whose value (stripped of quotes) doubles as the CSRF token for all subsequent `csrf-token` headers.

### Data Extraction

The primary endpoint is:

```
GET https://www.linkedin.com/voyager/api/identity/profiles/{username}/profileView
```

This single call returns a JSON object with the following sub-documents:

- `profile` — name, headline, location, summary, profile image
- `positionView` — work experience
- `educationView` — education
- `skillView` — skills (top portion)
- `certificationView` — certifications
- `languageView` — languages

For a more complete skill list a second call is made to:

```
GET https://www.linkedin.com/voyager/api/identity/profiles/{username}/skills?count=100&start=0
```

All of this data is parsed and normalised into the response schema above.

### Stack

- **FastAPI** — API framework
- **requests** — HTTP client for Voyager API calls
- **Pydantic v2** — response validation and serialisation
- **Render** — free HTTPS hosting

---

## Local Setup

### Prerequisites

- Python 3.11+
- A LinkedIn account

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/linkedin-profile-api.git
cd linkedin-profile-api
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Get your LinkedIn session cookie

1. Log in to [linkedin.com](https://www.linkedin.com) in your browser.
2. Open DevTools (`F12`) → **Application** → **Cookies** → `https://www.linkedin.com`.
3. Find the cookie named **`li_at`** and copy its value.

### 4. Set the environment variable

```bash
# Linux / macOS
export LI_AT="your_cookie_value_here"

# Windows PowerShell
$env:LI_AT = "your_cookie_value_here"
```

Or copy `.env.example` to `.env`, fill in the value, and load it:

```bash
cp .env.example .env
# edit .env, then:
set -a && source .env && set +a   # Linux/macOS
```

### 5. Run the server

```bash
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for the interactive API docs.

---

## Deploying to Render

1. Push the repository to GitHub.
2. Go to [render.com](https://render.com) → **New Web Service** → connect your repo.
3. Render detects `render.yaml` automatically.
4. In the **Environment** section add `LI_AT` with your cookie value.
5. Click **Deploy** — Render provides a free HTTPS URL.

---

## Known Limitations

- **Cookie expiry** — the `li_at` cookie typically lasts around one year. When it expires, you must obtain a fresh value from your browser and update the environment variable.
- **Rate limiting** — LinkedIn throttles automated requests. Making many requests in quick succession returns HTTP 429 / status code 999. The API surfaces this as a 429 response.
- **Private profiles** — profiles set to private or "connections only" return partial or no data depending on whether your account is connected to them.
- **LinkedIn API changes** — LinkedIn changes its internal API without notice. The Voyager API field names and response structure may shift and require updates to the parser.
- **No pagination for positions/education** — the `profileView` endpoint returns up to approximately 10 positions and 10 education entries. Profiles with more entries will have them truncated.
- **Authentication method** — using personal credentials in a backend is against LinkedIn's Terms of Service. This project is built as a technical demonstration for the Tross engineering hiring challenge.
