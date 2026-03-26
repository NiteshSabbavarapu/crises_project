import re
from typing import Any

from django.conf import settings
from google import genai
from google.genai import types
from openai import OpenAI

from intel.models import IntelligenceRun
from news.models import Story


def personalize_actions(story, user_profile):
    actions = [line.strip() for line in (story.action_summary or "").splitlines() if line.strip()]
    if not actions:
        actions = ["Follow official local guidance and avoid sharing unverified updates."]
    if user_profile and user_profile.medical_needs:
        actions.append("Keep essential medicines and prescriptions ready in case access is disrupted.")
    if user_profile and user_profile.has_vehicle:
        actions.append("Use your vehicle only after checking route advisories and official closures.")
    return actions[:3]


def _extract_output_text(response: Any) -> str:
    text = getattr(response, "output_text", "") or getattr(response, "text", "") or ""
    return text.strip()


def _extract_gemini_sources(response: Any) -> list[str]:
    urls = []
    for candidate in getattr(response, "candidates", []) or []:
        grounding = getattr(candidate, "grounding_metadata", None) or getattr(candidate, "groundingMetadata", None)
        if not grounding:
            continue
        chunks = getattr(grounding, "grounding_chunks", None) or getattr(grounding, "groundingChunks", None) or []
        for chunk in chunks:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None) or getattr(chunk, "uri", None)
            if uri and uri not in urls:
                urls.append(uri)
    return urls


def build_grounded_search_query(story: Story) -> str:
    location_names = []
    for location in story.locations.select_related("city", "area").all()[:3]:
        if location.area:
            location_names.append(location.area.name)
        if location.city:
            location_names.append(location.city.name)
    location_suffix = ", ".join(dict.fromkeys(location_names))
    if location_suffix:
        return f"{story.headline} {location_suffix} official advisory latest updates"
    return f"{story.headline} official advisory latest updates India"


def gemini_web_search(query: str) -> dict[str, Any]:
    if not settings.GEMINI_API_KEY or not settings.GEMINI_ENABLE_WEB_SEARCH:
        return {"summary": "", "sources": [], "success": False, "provider": "gemini"}

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    tool = types.Tool(googleSearch=types.GoogleSearch())
    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[tool],
            temperature=0.2,
            maxOutputTokens=350,
            systemInstruction=(
                "Summarize only trustworthy, directly relevant real-time web context for a crisis-intelligence backend. "
                "Keep it concise and neutral."
            ),
        ),
    )
    return {
        "summary": _extract_output_text(response),
        "sources": _extract_gemini_sources(response),
        "success": True,
        "provider": "gemini",
    }


def _build_openai_prompt(story: Story, evidence_lines: list[str], grounded_context: dict[str, Any]) -> str:
    grounded_text = grounded_context.get("summary") or "No fresh grounded web context available."
    grounded_sources = grounded_context.get("sources") or []
    source_lines = "\n".join(f"- {line}" for line in evidence_lines)
    grounded_source_lines = "\n".join(f"- {url}" for url in grounded_sources) or "- No Gemini grounding citations available."
    return (
        f"Story headline: {story.headline}\n"
        f"Category: {story.category}\n"
        f"Severity: {story.severity}\n"
        f"Verification status: {story.status}\n"
        f"Official resource URL: {story.official_resource_url or 'N/A'}\n\n"
        f"Trusted evidence:\n{source_lines}\n\n"
        f"Gemini grounded web context:\n{grounded_text}\n\n"
        f"Gemini grounded citations:\n{grounded_source_lines}\n\n"
        "Return exactly this format:\n"
        "SUMMARY: one concise paragraph\n"
        "IMPACT: one concise paragraph focused on local impact\n"
        "ACTIONS:\n"
        "- action 1\n"
        "- action 2\n"
        "- action 3\n"
        "Requirements: stay factual, do not invent sources, and keep recommendations practical."
    )


def _parse_openai_brief(text: str) -> tuple[str, str, str]:
    summary_match = re.search(r"SUMMARY:\s*(.*?)(?:\nIMPACT:|\Z)", text, flags=re.DOTALL)
    impact_match = re.search(r"IMPACT:\s*(.*?)(?:\nACTIONS:|\Z)", text, flags=re.DOTALL)
    actions_match = re.search(r"ACTIONS:\s*(.*)", text, flags=re.DOTALL)
    summary = summary_match.group(1).strip() if summary_match else ""
    impact = impact_match.group(1).strip() if impact_match else ""
    actions = actions_match.group(1).strip() if actions_match else ""
    actions = "\n".join(line.strip() for line in actions.splitlines() if line.strip())
    return summary, impact, actions


def generate_story_brief(story: Story, fallback_actions: list[str]) -> tuple[str, str, str]:
    evidence = list(story.evidence.select_related("raw_item__source"))
    evidence_lines = [
        f"{item.raw_item.source.name}: {item.raw_item.headline} ({item.raw_item.url})" for item in evidence[:4]
    ]
    grounded_context = {"summary": "", "sources": [], "success": False, "provider": "gemini"}

    query = build_grounded_search_query(story)
    try:
        grounded_context = gemini_web_search(query)
    except Exception as exc:
        IntelligenceRun.objects.create(
            story=story,
            task_type=IntelligenceRun.TaskType.SUMMARY,
            provider="gemini",
            model_name=settings.GEMINI_MODEL,
            request_payload={"query": query},
            response_payload={"error": str(exc)},
            success=False,
        )

    if settings.OPENAI_API_KEY:
        prompt = _build_openai_prompt(story, evidence_lines, grounded_context)
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        try:
            response = client.responses.create(
                model=settings.OPENAI_MODEL,
                reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
                input=prompt,
                max_output_tokens=500,
            )
            output_text = _extract_output_text(response)
            summary, impact, actions = _parse_openai_brief(output_text)
            IntelligenceRun.objects.create(
                story=story,
                task_type=IntelligenceRun.TaskType.SUMMARY,
                provider="openai",
                model_name=settings.OPENAI_MODEL,
                request_payload={"prompt": prompt},
                response_payload={
                    "output_text": output_text,
                    "grounded_context": grounded_context,
                },
                success=bool(summary and actions),
            )
            if summary and actions:
                return summary, impact, actions
        except Exception as exc:
            IntelligenceRun.objects.create(
                story=story,
                task_type=IntelligenceRun.TaskType.SUMMARY,
                provider="openai",
                model_name=settings.OPENAI_MODEL,
                request_payload={"query": query},
                response_payload={"error": str(exc), "grounded_context": grounded_context},
                success=False,
            )

    fallback_summary = f"Verified from {story.source_count} source(s): " + " | ".join(
        item.raw_item.headline for item in evidence[:3]
    )
    if grounded_context.get("summary"):
        fallback_summary = f"{fallback_summary}\n\nGrounded web context: {grounded_context['summary']}"
    fallback_impact = f"This may affect {story.category.replace('_', ' ')} conditions near the tagged location."
    fallback_action_text = "\n".join(f"- {item}" for item in fallback_actions[:3])
    IntelligenceRun.objects.create(
        story=story,
        task_type=IntelligenceRun.TaskType.SUMMARY,
        provider="rules",
        model_name="fallback",
        request_payload={"query": query, "grounded_context": grounded_context},
        response_payload={
            "summary": fallback_summary,
            "impact": fallback_impact,
            "actions": fallback_action_text,
        },
        success=True,
    )
    return fallback_summary, fallback_impact, fallback_action_text
