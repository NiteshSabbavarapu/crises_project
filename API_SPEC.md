# CrisisSync API Specification

This document describes the currently wired HTTP API surface in the backend as implemented in the URL config and view/serializer layer.

Base URL:

```text
/api/v1/
```

Documentation endpoints:

- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`

Authentication:

- JWT Bearer auth is enabled for protected endpoints.
- Send:

```http
Authorization: Bearer <access_token>
```

Default pagination:

- DRF page-number pagination is enabled globally.
- Default page size: `20`
- Paginated list shape:

```json
{
  "count": 42,
  "next": "http://localhost:8000/api/v1/stories/?page=2",
  "previous": null,
  "results": []
}
```

Current route registration is defined in:

- `config/urls.py`
- `config/api_urls.py`

No public HTTP endpoints are currently registered for:

- `intel`
- `sources`
- `jobs`

## 1. Current End-to-End Flow

This is the current product flow exposed by the API.

### Flow A: User onboarding and personalization

1. User registers with `/auth/register`.
2. User logs in with `/auth/login`.
3. Client stores `access` and `refresh` tokens.
4. Client fetches `/auth/me` to get the complete profile bundle.
5. User sets one or more preferred locations using `/profile/location`.
6. User updates alert settings using `/profile/preferences`.
7. User updates household/action context using `/profile/action-profile`.

### Flow B: Location discovery

1. Client fetches available cities with `/locations/cities`.
2. Client optionally filters cities by `state` or `country`.
3. Client fetches areas with `/locations/areas`.
4. Client optionally filters areas by `city`.
5. IDs returned here are then used in profile and story filters.

### Flow C: Crisis intelligence consumption

1. Background jobs ingest raw source items from the trusted source registry.
2. Raw items are normalized into canonical stories.
3. Gemini retrieves recent official Indian web context using date-aware search queries.
4. OpenAI decides whether the story is `verified`, `unconfirmed`, or `debunked`.
5. The system stores the decision plus summary, impact, and action guidance on the story.
6. Client fetches normalized stories from `/stories/`.
7. Client filters by geography, category, status, recency, or minimum priority.
8. Client opens a single story using `/stories/{id}`.
9. Client can fetch high-priority items with `/stories/critical`.
10. Client can fetch debunked items with `/stories/fake-news`.

### Flow C1: Story intelligence pipeline

1. Client fetches normalized stories from `/stories/`.
2. Stories originate from `RawIngestItem` records created by the ingestion job.
3. Normalization groups similar raw items under a canonical `Story`.
4. Gemini retrieval is used to search recent official Indian sources with a date window and official-domain bias.
5. OpenAI decisioning consumes:
   - local evidence from stored sources
   - Gemini grounded official context
   - current story metadata
6. OpenAI returns structured JSON with:
   - `status`
   - `confidence_score`
   - `official_resource_url`
   - `summary`
   - `impact_summary`
   - `action_summary`
   - `rationale`
7. If provider calls fail or keys are unavailable, the backend falls back to local heuristics.

### Flow D: Alert consumption

1. System generates alert digests internally from stories.
2. Delivered stories are stored per user with a `local` or `global` scope and are not sent again to the same user.
3. Logged-in user fetches their digests from `/alerts/`.
4. Logged-in user fetches all already-delivered personal news from `/alerts/news`.
5. User opens an individual digest with `/alerts/{id}`.
6. Admin/staff user can trigger `/alerts/test-send` to generate and send a test digest from the highest-priority story.

### Flow E: Rumor verification

1. Logged-in user submits a rumor claim to `/rumors/`.
2. Backend creates the `RumorClaim`.
3. Backend immediately triggers verification via `verify_claim(claim)`.
4. Client fetches the created claim or list of claims from `/rumors/` and `/rumors/{id}`.
5. The response includes the current verification verdict and supporting evidence when available.

## 2. Authentication Rules

### Public endpoints

- `GET /health/`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/token/refresh`
- `GET /locations/cities`
- `GET /locations/areas`
- `GET /stories/`
- `GET /stories/{id}`
- `GET /stories/critical`
- `GET /stories/fake-news`

### Authenticated endpoints

- `GET /auth/me`
- `POST /profile/location`
- `PUT /profile/preferences`
- `PUT /profile/action-profile`
- `GET /alerts/`
- `GET /alerts/news`
- `GET /alerts/{id}`
- `POST /alerts/test-send`
- `GET /rumors/`
- `POST /rumors/`
- `GET /rumors/{id}`

### Admin-only behavior

- `POST /alerts/test-send`

If the authenticated user is not `is_staff` and not `is_superuser`, this endpoint returns `403`.

## 3. API Specification

## Health

### GET `/api/v1/health/`

Purpose:

- Basic health check for the backend service.

Authentication:

- Public

Request body:

- None

Response `200`

```json
{
  "status": "ok",
  "service": "crisissync"
}
```

Flow notes:

- Used by clients, deployment checks, or monitoring to verify the API is reachable.

## Alerts APIs

### GET `/api/v1/alerts/news`

Purpose:

- Returns all stories that have already been delivered to the authenticated user.
- Each delivered item is classified as either `local` or `global`.
- This is the canonical user-specific news history API.

Authentication:

- Required

Query parameters:

- `scope`: optional, one of `local` or `global`

Response `200`

```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 11,
      "scope": "local",
      "first_sent_at": "2026-03-26T10:35:00Z",
      "last_sent_at": "2026-03-26T10:35:00Z",
      "story": {
        "id": 7,
        "headline": "Critical shortage confirmed in Banjara Hills",
        "summary": "Verified update",
        "impact_summary": "Short-term supply disruption likely.",
        "action_summary": "Check official ration updates.",
        "category": "supply_crisis",
        "severity": "critical",
        "status": "verified",
        "priority_score": 90,
        "confidence_score": 90,
        "official_resource_url": "https://example.com/official",
        "source_count": 2,
        "published_at": "2026-03-26T10:30:00Z",
        "detected_at": "2026-03-26T10:31:00Z",
        "evidence": [],
        "locations": [],
        "tags": []
      }
    }
  ]
}
```

Behavior:

- Stories are returned from newest delivered to oldest.
- A story is stored only once per user, so previously sent items will not be sent again to that same user in later digests.

## Auth APIs

### POST `/api/v1/auth/register`

Purpose:

- Creates a user account.
- Also initializes:
  - `UserAlertPreference`
  - `UserActionProfile`

Authentication:

- Public

Request body:

```json
{
  "username": "nitesh",
  "email": "nitesh@example.com",
  "password": "StrongPassword123",
  "password_confirm": "StrongPassword123",
  "first_name": "Nitesh",
  "last_name": "Kumar"
}
```

Request fields:

- `username`: required by serializer schema, but if omitted in create logic it falls back to `email`
- `email`: optional at serializer level, typically expected by product flow
- `password`: required, minimum 8 chars
- `password_confirm`: required, must match `password`
- `first_name`: optional
- `last_name`: optional

Response `201`

```json
{
  "id": 1,
  "username": "nitesh",
  "email": "nitesh@example.com",
  "first_name": "Nitesh",
  "last_name": "Kumar"
}
```

Validation and behavior:

- Passwords must match.
- Django password validators are applied.
- Alert preference and action profile records are auto-created for the user.

Flow notes:

1. Call register.
2. Then call login to obtain JWT tokens.
3. Then call `/auth/me` to get the complete current profile bundle.

### POST `/api/v1/auth/login`

Purpose:

- Authenticates the user and returns JWT tokens.

Authentication:

- Public

Request body:

```json
{
  "username": "nitesh",
  "password": "StrongPassword123"
}
```

Response `200`

```json
{
  "refresh": "jwt-refresh-token",
  "access": "jwt-access-token"
}
```

Flow notes:

1. Use `access` token for protected APIs.
2. Use `refresh` token with `/auth/token/refresh` to obtain a new access token.

### POST `/api/v1/auth/token/refresh`

Purpose:

- Exchanges a refresh token for a new access token.

Authentication:

- Public

Request body:

```json
{
  "refresh": "jwt-refresh-token"
}
```

Response `200`

```json
{
  "access": "new-jwt-access-token"
}
```

### GET `/api/v1/auth/me`

Purpose:

- Returns the authenticated user’s complete current profile bundle.
- Ensures `alert_preference` and `action_profile` exist.

Authentication:

- Required

Request body:

- None

Response `200`

```json
{
  "user": {
    "id": 1,
    "username": "nitesh",
    "email": "nitesh@example.com",
    "first_name": "Nitesh",
    "last_name": "Kumar"
  },
  "locations": [
    {
      "id": 7,
      "country": 1,
      "country_name": "India",
      "state": 5,
      "state_name": "Telangana",
      "city": 12,
      "city_name": "Hyderabad",
      "area": 44,
      "area_name": "Madhapur",
      "pincode": "500081",
      "lat": "17.448300",
      "lng": "78.391500",
      "is_primary": true
    }
  ],
  "alert_preference": {
    "frequency": "critical_only",
    "categories": [],
    "email_enabled": true
  },
  "action_profile": {
    "household_size": 1,
    "has_vehicle": false,
    "medical_needs": "",
    "notes": ""
  }
}
```

Flow notes:

- Use this immediately after login to hydrate the user session in the frontend.

## Profile APIs

### POST `/api/v1/profile/location`

Purpose:

- Adds a location preference for the authenticated user.
- If `is_primary` is true or omitted, all existing preferences for that user are first marked non-primary.

Authentication:

- Required

Request body:

```json
{
  "country": 1,
  "state": 5,
  "city": 12,
  "area": 44,
  "pincode": "500081",
  "lat": "17.448300",
  "lng": "78.391500",
  "is_primary": true
}
```

Request fields:

- `country`: optional FK id
- `state`: optional FK id
- `city`: optional FK id
- `area`: optional FK id
- `pincode`: optional string
- `lat`: optional decimal
- `lng`: optional decimal
- `is_primary`: optional boolean, defaults to true in behavior

Validation:

- `state` must belong to `country`
- `city` must belong to `state`
- `area` must belong to `city`

Response `201`

```json
{
  "id": 7,
  "country": 1,
  "country_name": "India",
  "state": 5,
  "state_name": "Telangana",
  "city": 12,
  "city_name": "Hyderabad",
  "area": 44,
  "area_name": "Madhapur",
  "pincode": "500081",
  "lat": "17.448300",
  "lng": "78.391500",
  "is_primary": true
}
```

Flow notes:

1. Use `/locations/cities` and `/locations/areas` first to discover IDs.
2. Save one or more user locations here.
3. The primary location represents the main area of interest for alerts and crisis tracking.

### PUT `/api/v1/profile/preferences`

Purpose:

- Updates alert delivery preference settings.

Authentication:

- Required

Request body:

```json
{
  "frequency": "critical_only",
  "categories": ["weather", "health"],
  "email_enabled": true
}
```

Allowed values:

- `frequency`: `30min`, `hourly`, `critical_only`
- `categories`: JSON array of category strings
- `email_enabled`: boolean

Response `200`

```json
{
  "frequency": "critical_only",
  "categories": ["weather", "health"],
  "email_enabled": true
}
```

Flow notes:

- This controls how the user wants alert digests to be sent and filtered.

### PUT `/api/v1/profile/action-profile`

Purpose:

- Stores user context used to personalize action-oriented guidance.

Authentication:

- Required

Request body:

```json
{
  "household_size": 4,
  "has_vehicle": true,
  "medical_needs": "Insulin storage required",
  "notes": "Two elderly family members at home"
}
```

Response `200`

```json
{
  "household_size": 4,
  "has_vehicle": true,
  "medical_needs": "Insulin storage required",
  "notes": "Two elderly family members at home"
}
```

Flow notes:

- This profile is part of the `/auth/me` bundle and should generally be updated after onboarding.

## Location APIs

### GET `/api/v1/locations/cities`

Purpose:

- Lists active cities.
- Supports filtering by `state` and `country`.

Authentication:

- Public

Query params:

- `state`: optional state id
- `country`: optional country id
- `page`: optional page number

Example request:

```http
GET /api/v1/locations/cities?country=1&page=1
```

Response `200`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 12,
      "name": "Hyderabad",
      "slug": "telangana-hyderabad",
      "state_name": "Telangana",
      "country_name": "India"
    }
  ]
}
```

Flow notes:

- Fetch cities before saving a profile location or applying story filters.

### GET `/api/v1/locations/areas`

Purpose:

- Lists active areas.
- Supports filtering by `city`.

Authentication:

- Public

Query params:

- `city`: optional city id
- `page`: optional page number

Example request:

```http
GET /api/v1/locations/areas?city=12&page=1
```

Response `200`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 44,
      "name": "Madhapur",
      "city": 12,
      "city_name": "Hyderabad",
      "pincode": "500081",
      "latitude": "17.448300",
      "longitude": "78.391500"
    }
  ]
}
```

Flow notes:

- Use returned area IDs in profile preferences and story filtering.

## Story APIs

### Story generation and verification flow

The `/stories/*` endpoints are read-only views over the `Story` table. Stories are produced by a backend pipeline:

1. `ingest_sources`
   - fetches raw content from active trusted sources
   - currently only RSS sources are ingested automatically
2. `normalize_stories`
   - groups similar raw items into canonical stories
   - infers category, severity, and location matches
3. `score_stories`
   - calls Gemini to retrieve recent official Indian source context
   - calls OpenAI to decide `verified`, `unconfirmed`, or `debunked`
   - stores summary, impact summary, action summary, confidence score, and official resource URL
   - computes `priority_score`

The live AI decision flow is currently implemented in:

- `intel/services.py`
- `news/services.py`

Current AI behavior:

- Gemini retrieval prompt is explicitly India-focused and date-aware
- Gemini is expected to surface official sources such as `gov.in` and `nic.in`
- OpenAI is the final decision engine for story verification status
- Fallback heuristics still exist if provider calls are unavailable or fail

### Story object shape

Story responses use this core structure:

```json
{
  "id": 101,
  "headline": "Heavy rainfall disrupts transport in western Hyderabad",
  "summary": "Localized flooding and closures reported.",
  "impact_summary": "Road congestion and delivery delays expected.",
  "action_summary": "Avoid low-lying roads and follow municipal advisories.",
  "category": "weather",
  "severity": "high",
  "status": "verified",
  "priority_score": 88,
  "confidence_score": 91,
  "official_resource_url": "https://example.gov/advisory",
  "source_count": 3,
  "published_at": "2026-03-26T05:30:00Z",
  "detected_at": "2026-03-26T05:45:00Z",
  "evidence": [
    {
      "id": 5,
      "source_name": "Official Weather Desk",
      "url": "https://example.gov/advisory",
      "headline": "Heavy rainfall alert issued",
      "is_primary": true,
      "note": "Primary official source"
    }
  ],
  "locations": [
    {
      "country_name": "India",
      "state_name": "Telangana",
      "city_name": "Hyderabad",
      "area_name": "Madhapur",
      "pincode": "500081",
      "relevance_score": 90
    }
  ],
  "tags": [
    {
      "name": "rain"
    },
    {
      "name": "traffic"
    }
  ]
}
```

### GET `/api/v1/stories/`

Purpose:

- Lists normalized crisis stories.
- Supports filtering by geography, category, status, score, and detection time.

Authentication:

- Public read access

Query params:

- `city`: optional city id
- `area`: optional area id
- `pincode`: optional string
- `category`: optional category
- `status`: optional story status
- `min_priority`: optional integer threshold
- `since`: optional datetime string parseable by Django `parse_datetime`
- `page`: optional page number

Allowed categories:

- `supply_crisis`
- `weather`
- `civil_unrest`
- `price_surge`
- `health`
- `general`

Allowed status values:

- `verified`
- `unconfirmed`
- `debunked`

Example request:

```http
GET /api/v1/stories/?city=12&category=weather&min_priority=70&page=1
```

Response `200`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 101,
      "headline": "Heavy rainfall disrupts transport in western Hyderabad",
      "summary": "Localized flooding and closures reported.",
      "impact_summary": "Road congestion and delivery delays expected.",
      "action_summary": "Avoid low-lying roads and follow municipal advisories.",
      "category": "weather",
      "severity": "high",
      "status": "verified",
      "priority_score": 88,
      "confidence_score": 91,
      "official_resource_url": "https://example.gov/advisory",
      "source_count": 3,
      "published_at": "2026-03-26T05:30:00Z",
      "detected_at": "2026-03-26T05:45:00Z",
      "evidence": [],
      "locations": [],
      "tags": []
    }
  ]
}
```

Flow notes:

1. This is the main feed endpoint.
2. Frontend typically combines this with user location preferences.
3. `status` now reflects the story-decision pipeline driven by Gemini retrieval plus OpenAI decisioning when provider keys are configured.
4. `official_resource_url` may come from the OpenAI decision output or from a local official source fallback.
5. `min_priority` is useful for showing only urgent stories.
6. `since` is useful for incremental polling.

### GET `/api/v1/stories/{id}`

Purpose:

- Returns one normalized story in full detail.

Authentication:

- Public read access

Path params:

- `id`: story primary key

Response `200`

- Returns a single Story object using the same structure as above.

Flow notes:

- Use this when a user opens a story from the feed.

### GET `/api/v1/stories/critical`

Purpose:

- Returns stories with `priority_score >= 80`.

Authentication:

- Public read access

Query params:

- None currently implemented

Response `200`

```json
[
  {
    "id": 101,
    "headline": "Heavy rainfall disrupts transport in western Hyderabad",
    "summary": "Localized flooding and closures reported.",
    "impact_summary": "Road congestion and delivery delays expected.",
    "action_summary": "Avoid low-lying roads and follow municipal advisories.",
    "category": "weather",
    "severity": "high",
    "status": "verified",
    "priority_score": 88,
    "confidence_score": 91,
    "official_resource_url": "https://example.gov/advisory",
    "source_count": 3,
    "published_at": "2026-03-26T05:30:00Z",
    "detected_at": "2026-03-26T05:45:00Z",
    "evidence": [],
    "locations": [],
    "tags": []
  }
]
```

Important behavior:

- This endpoint returns a plain array, not a paginated object.

Flow notes:

- Use this for emergency banners, critical panels, or fast-priority dashboards.

### GET `/api/v1/stories/fake-news`

Purpose:

- Lists only debunked stories.

Authentication:

- Public read access

Query params:

- `page`: optional page number

Response `200`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 205,
      "headline": "Water contamination rumor proven false",
      "summary": "No contamination found in official test report.",
      "impact_summary": "Public panic reduced after clarification.",
      "action_summary": "Follow official municipal updates only.",
      "category": "health",
      "severity": "medium",
      "status": "debunked",
      "priority_score": 40,
      "confidence_score": 95,
      "official_resource_url": "https://example.gov/test-report",
      "source_count": 2,
      "published_at": "2026-03-25T12:00:00Z",
      "detected_at": "2026-03-25T12:15:00Z",
      "evidence": [],
      "locations": [],
      "tags": []
    }
  ]
}
```

Flow notes:

- Intended for fake-news or misinformation views.
- A story appears here only when its stored `status` is `debunked`.
- In the current pipeline, `debunked` can now be produced by the OpenAI decision output when official Indian sources clearly deny or correct the claim.

## Alert APIs

### Alert digest object shape

```json
{
  "id": 31,
  "digest_type": "scheduled",
  "subject": "Critical update for your area",
  "body_text": "Text digest body",
  "body_html": "<p>HTML digest body</p>",
  "scheduled_for": "2026-03-26T07:00:00Z",
  "sent_at": "2026-03-26T07:00:30Z",
  "stories": [],
  "created_at": "2026-03-26T06:59:55Z"
}
```

Allowed `digest_type` values:

- `immediate`
- `scheduled`
- `test`

### GET `/api/v1/alerts/`

Purpose:

- Lists alert digests for the authenticated user only.

Authentication:

- Required

Query params:

- `page`: optional page number

Response `200`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 31,
      "digest_type": "scheduled",
      "subject": "Critical update for your area",
      "body_text": "Text digest body",
      "body_html": "<p>HTML digest body</p>",
      "scheduled_for": "2026-03-26T07:00:00Z",
      "sent_at": "2026-03-26T07:00:30Z",
      "stories": [],
      "created_at": "2026-03-26T06:59:55Z"
    }
  ]
}
```

Flow notes:

- This is the user’s alert history endpoint.
- Users only see digests belonging to themselves.

### GET `/api/v1/alerts/{id}`

Purpose:

- Returns a single alert digest for the authenticated user.

Authentication:

- Required

Path params:

- `id`: alert digest primary key

Response `200`

```json
{
  "id": 31,
  "digest_type": "scheduled",
  "subject": "Critical update for your area",
  "body_text": "Text digest body",
  "body_html": "<p>HTML digest body</p>",
  "scheduled_for": "2026-03-26T07:00:00Z",
  "sent_at": "2026-03-26T07:00:30Z",
  "stories": [],
  "created_at": "2026-03-26T06:59:55Z"
}
```

Flow notes:

- Use this when opening one alert from the list.

### POST `/api/v1/alerts/test-send`

Purpose:

- Admin-only helper endpoint to create and send a test digest.
- Uses the highest-priority story currently available.

Authentication:

- Required
- User must be `is_staff` or `is_superuser`

Request body:

- None

Success response `200`

```json
{
  "digest": {
    "id": 45,
    "digest_type": "test",
    "subject": "Test alert",
    "body_text": "Text digest body",
    "body_html": "",
    "scheduled_for": null,
    "sent_at": "2026-03-26T08:05:00Z",
    "stories": [],
    "created_at": "2026-03-26T08:04:58Z"
  },
  "delivery_status": "sent"
}
```

Possible error `403`

```json
{
  "detail": "Test send is admin-only."
}
```

Possible error `400`

```json
{
  "detail": "No stories available."
}
```

Flow notes:

1. Endpoint selects `Story.objects.order_by("-priority_score").first()`.
2. Creates a `test` `AlertDigest`.
3. Adds the story to the digest.
4. Sends it through the configured email delivery service.
5. Returns the digest plus final delivery status.

## Rumor APIs

### Rumor claim object shape

```json
{
  "id": 91,
  "text": "Water tankers will stop in Madhapur tonight",
  "city": 12,
  "area": 44,
  "pincode": "500081",
  "extracted_entities": ["water", "Madhapur", "tonight"],
  "status": "completed",
  "created_at": "2026-03-26T09:00:00Z",
  "updated_at": "2026-03-26T09:00:03Z",
  "verdict": {
    "verdict": "unconfirmed",
    "confidence": 61,
    "explanation": "No matching verified official notice was found.",
    "official_link": "",
    "verified_at": "2026-03-26T09:00:03Z",
    "evidence": [
      {
        "id": 12,
        "source_name": "Municipal Board",
        "url": "https://example.gov/notice",
        "note": "Latest official advisory checked"
      }
    ]
  }
}
```

Allowed `status` values:

- `pending`
- `completed`

Allowed verdict values:

- `verified`
- `unconfirmed`
- `false_debunked`

### GET `/api/v1/rumors/`

Purpose:

- Lists rumor claims.
- Supports optional city filtering.

Authentication:

- Required

Query params:

- `city`: optional city id
- `page`: optional page number

Response `200`

```json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 91,
      "text": "Water tankers will stop in Madhapur tonight",
      "city": 12,
      "area": 44,
      "pincode": "500081",
      "extracted_entities": ["water", "Madhapur", "tonight"],
      "status": "completed",
      "created_at": "2026-03-26T09:00:00Z",
      "updated_at": "2026-03-26T09:00:03Z",
      "verdict": {
        "verdict": "unconfirmed",
        "confidence": 61,
        "explanation": "No matching verified official notice was found.",
        "official_link": "",
        "verified_at": "2026-03-26T09:00:03Z",
        "evidence": []
      }
    }
  ]
}
```

Important behavior:

- The current queryset is `RumorClaim.objects.all()`.
- That means authenticated users can currently list all rumor claims, not just their own.

Flow notes:

- Frontend can use this as the rumor history view.

### POST `/api/v1/rumors/`

Purpose:

- Submits a rumor or user claim for verification.
- Immediately triggers backend verification.

Authentication:

- Required

Request body:

```json
{
  "text": "Water tankers will stop in Madhapur tonight",
  "city": 12,
  "area": 44,
  "pincode": "500081",
  "extracted_entities": ["water", "Madhapur", "tonight"]
}
```

Request fields:

- `text`: required
- `city`: optional city id
- `area`: optional area id
- `pincode`: optional string
- `extracted_entities`: optional JSON array
- `status`: technically writable in the serializer because it is included, though the expected flow is that backend controls it

Response `201`

```json
{
  "id": 91,
  "text": "Water tankers will stop in Madhapur tonight",
  "city": 12,
  "area": 44,
  "pincode": "500081",
  "extracted_entities": ["water", "Madhapur", "tonight"],
  "status": "pending",
  "created_at": "2026-03-26T09:00:00Z",
  "updated_at": "2026-03-26T09:00:00Z",
  "verdict": null
}
```

Current backend flow:

1. Serializer saves the claim with `submitter=request.user`.
2. `verify_claim(claim)` is called immediately in `perform_create`.
3. Depending on the verification implementation and timing, the created response may contain:
   - a pending claim with no verdict yet
   - or a completed claim with a nested verdict

Frontend guidance:

- After submit, poll `GET /rumors/{id}` if you need the finalized verdict reliably.

### GET `/api/v1/rumors/{id}`

Purpose:

- Returns one rumor claim with nested verdict and evidence.

Authentication:

- Required

Path params:

- `id`: rumor claim primary key

Response `200`

```json
{
  "id": 91,
  "text": "Water tankers will stop in Madhapur tonight",
  "city": 12,
  "area": 44,
  "pincode": "500081",
  "extracted_entities": ["water", "Madhapur", "tonight"],
  "status": "completed",
  "created_at": "2026-03-26T09:00:00Z",
  "updated_at": "2026-03-26T09:00:03Z",
  "verdict": {
    "verdict": "unconfirmed",
    "confidence": 61,
    "explanation": "No matching verified official notice was found.",
    "official_link": "",
    "verified_at": "2026-03-26T09:00:03Z",
    "evidence": [
      {
        "id": 12,
        "source_name": "Municipal Board",
        "url": "https://example.gov/notice",
        "note": "Latest official advisory checked"
      }
    ]
  }
}
```

Flow notes:

- This is the safest endpoint to use for rendering the final rumor-check result.

## 4. Current Serializer/Flow Caveats

These are important implementation realities in the current code and should be considered part of the current spec.

### Schema generation is partial for some APIViews

- The generated OpenAPI schema does not fully describe `APIView` endpoints like:
  - `/auth/me`
  - `/profile/location`
  - `/profile/preferences`
  - `/profile/action-profile`
  - `/alerts/test-send`
  - `/health/`
  - `/stories/critical`

Reason:

- These views do not declare explicit serializer classes for schema generation.

### `stories/critical` is not paginated

- Unlike most list endpoints, `/stories/critical` returns a plain array.

### Rumor list/detail are not user-scoped

- The current queryset is global, so authenticated users can access all rumor claims.

### `status` is included in rumor create/update serializer fields

- Client can technically submit `status`, although the intended flow suggests the backend should manage it.

### Register serializer vs create behavior

- Serializer schema marks `username` as required.
- Create logic also contains fallback behavior to use `email` as `username` if missing.
- Current clients should still send `username` explicitly to avoid validation mismatch.

### AI decisioning depends on real provider configuration

- Gemini retrieval runs only when `GEMINI_API_KEY` is present and web search is enabled.
- OpenAI decisioning runs only when `OPENAI_API_KEY` is present.
- If those keys are missing or calls fail, the backend falls back to heuristic verification and summary generation.

### Gemini retrieval favors official Indian sources but cannot guarantee only official results

- The retrieval prompt and post-processing prefer official Indian domains.
- Final verification status is still dependent on the OpenAI decision output and fallback rules.

### Story status is now pipeline-driven rather than purely source-count driven

- The system still records `source_count` and uses it in priority scoring.
- But story `status` is now primarily determined by the AI decision flow when provider calls succeed.

## 5. Recommended Frontend Usage Sequence

### New user

1. `POST /api/v1/auth/register`
2. `POST /api/v1/auth/login`
3. `GET /api/v1/auth/me`
4. `GET /api/v1/locations/cities`
5. `GET /api/v1/locations/areas`
6. `POST /api/v1/profile/location`
7. `PUT /api/v1/profile/preferences`
8. `PUT /api/v1/profile/action-profile`
9. `GET /api/v1/stories/`

### Returning user

1. `POST /api/v1/auth/login`
2. `GET /api/v1/auth/me`
3. `GET /api/v1/stories/`
4. `GET /api/v1/alerts/`
5. `GET /api/v1/rumors/`

### Rumor verification flow

1. `POST /api/v1/rumors/`
2. `GET /api/v1/rumors/{id}`
3. Show verdict, confidence, explanation, and evidence

## 6. Source of Truth in Code

The current implementation described in this document is based on these files:

- `config/urls.py`
- `config/api_urls.py`
- `accounts/urls.py`
- `accounts/profile_urls.py`
- `accounts/views.py`
- `accounts/serializers.py`
- `locations/urls.py`
- `locations/views.py`
- `locations/serializers.py`
- `news/urls.py`
- `news/views.py`
- `news/serializers.py`
- `alerts/urls.py`
- `alerts/views.py`
- `alerts/serializers.py`
- `rumors/urls.py`
- `rumors/views.py`
- `rumors/serializers.py`
- `config/settings.py`
