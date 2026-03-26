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
python manage.py migrate
python manage.py seed_reference_data
python manage.py runserver
```

## API docs
- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`

## Useful commands
```bash
python manage.py ingest_sources
python manage.py normalize_stories
python manage.py score_stories
python manage.py dispatch_alerts
python manage.py verify_rumor <claim_id>
python manage.py test
```
