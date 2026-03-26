# CrisisSync Backend

Backend-first Django MVP for crisis intelligence, source verification, and alert delivery.

## Included
- JWT auth and profile setup APIs
- Pan-India-capable location schema with Hyderabad seed data
- Trusted source registry and raw ingestion pipeline
- Story normalization, verification, and priority scoring
- Immediate and scheduled alert generation
- Rumor verification hooks
- Django admin and OpenAPI docs

## Setup
```bash
source venv/bin/activate
venv/bin/pip install -r requirements.txt
cp .env.example .env
venv/bin/python manage.py migrate
venv/bin/python manage.py seed_reference_data
venv/bin/python manage.py runserver
```

## Environment

This project is configured from `.env`.

### AI providers

Use real provider APIs by setting:

```env
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-5.2
OPENAI_REASONING_EFFORT=medium
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-2.5-flash
GEMINI_ENABLE_WEB_SEARCH=True
```

Notes:

- OpenAI summaries run only when `OPENAI_API_KEY` is present.
- Gemini grounded web search runs only when `GEMINI_API_KEY` is present and `GEMINI_ENABLE_WEB_SEARCH=True`.
- Without valid API keys, the app falls back to rule-based summaries. It does not get live provider responses.

### Gmail SMTP

To send real emails through Gmail SMTP, set:

```env
DJANGO_DEBUG=False
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_DELIVERY_PROVIDER=smtp
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-google-app-password
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_TIMEOUT=30
DEFAULT_FROM_EMAIL=your-email@gmail.com
```

Notes:

- Use a Google App Password, not your normal Gmail password.
- If you want SendGrid instead, set `EMAIL_DELIVERY_PROVIDER=sendgrid` and provide `SENDGRID_API_KEY`.
- SMTP is now the default delivery provider.

## API docs
- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`

## Useful commands
```bash
venv/bin/python manage.py ingest_sources
venv/bin/python manage.py normalize_stories
venv/bin/python manage.py score_stories
venv/bin/python manage.py dispatch_alerts
venv/bin/python manage.py verify_rumor <claim_id>
venv/bin/python manage.py test
```
