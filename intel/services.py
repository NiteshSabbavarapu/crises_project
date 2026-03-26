import json
import re
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.utils import timezone
from google import genai
from google.genai import types
from openai import OpenAI

from intel.models import IntelligenceRun
from news.models import Story


GEMINI_OFFICIAL_SEARCH_SYSTEM_PROMPT = (
    "You are a crisis-intelligence retrieval system for India. "
    "Find only directly relevant, date-aware, official Indian sources for the described situation. "
    "Prioritize central, state, district, municipal, police, disaster-management, weather, health, and transport authorities. "
    "Prefer domains such as gov.in, nic.in, and known official Indian public-agency domains. "
    "Use the most recent information first, mention concrete dates when available, and ignore generic commentary or unofficial summaries. "
    "Return a concise retrieval summary with dates and factual claims only."
)

OPENAI_DECISION_SYSTEM_PROMPT = (
    "You are the verification decision engine for an India crisis-intelligence backend. "
    "Your job is to decide whether a story should be marked verified, unconfirmed, or debunked based on trusted source evidence and grounded official Indian web context. "
    "Prefer official Indian sources over media reports. Treat unsupported claims conservatively. "
    "Return strict JSON only with factual, operational outputs for the backend."
)


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


def _is_official_india_url(url: str) -> bool:
    if not url:
        return False
    host = (urlparse(url).netloc or "").lower()
    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in ("gov.in", "nic.in", "ndma.gov.in", "imd.gov.in", "mohfw.gov.in")
    )


def build_grounded_search_query(story: Story) -> str:
    location_names = []
    for location in story.locations.select_related("city", "area").all()[:3]:
        if location.area:
            location_names.append(location.area.name)
        if location.city:
            location_names.append(location.city.name)
    location_suffix = ", ".join(dict.fromkeys(location_names))
    today = timezone.localdate().isoformat()
    recent_start = (timezone.localdate() - timedelta(days=7)).isoformat()
    if location_suffix:
        return (
            f"{story.headline} {location_suffix} India official advisory "
            f"site:gov.in OR site:nic.in after:{recent_start} before:{today}"
        )
    return (
        f"{story.headline} India official advisory "
        f"site:gov.in OR site:nic.in after:{recent_start} before:{today}"
    )


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
            systemInstruction=GEMINI_OFFICIAL_SEARCH_SYSTEM_PROMPT,
        ),
    )
    sources = _extract_gemini_sources(response)
    return {
        "summary": _extract_output_text(response),
        "sources": sources,
        "official_sources": [url for url in sources if _is_official_india_url(url)],
        "success": True,
        "provider": "gemini",
    }


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced_match = re.search(r"```json\s*(\{.*\})\s*```", text, flags=re.DOTALL)
    if fenced_match:
        text = fenced_match.group(1)
    else:
        brace_match = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if brace_match:
            text = brace_match.group(1)
    return json.loads(text)


def _build_openai_prompt(story: Story, evidence_lines: list[str], grounded_context: dict[str, Any]) -> str:
    grounded_text = grounded_context.get("summary") or "No fresh grounded web context available."
    grounded_sources = grounded_context.get("official_sources") or grounded_context.get("sources") or []
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


def _build_openai_decision_prompt(
    story: Story, evidence_lines: list[str], grounded_context: dict[str, Any], fallback_actions: list[str]
) -> str:
    grounded_sources = grounded_context.get("official_sources") or grounded_context.get("sources") or []
    return (
        f"Story headline: {story.headline}\n"
        f"Story category: {story.category}\n"
        f"Story severity: {story.severity}\n"
        f"Current published_at: {story.published_at or 'unknown'}\n"
        f"Current official_resource_url: {story.official_resource_url or 'N/A'}\n\n"
        f"Local stored evidence:\n" + ("\n".join(f"- {line}" for line in evidence_lines) or "- None") + "\n\n"
        f"Gemini official-context summary:\n{grounded_context.get('summary') or 'No grounded summary available.'}\n\n"
        f"Gemini citations:\n" + ("\n".join(f"- {url}" for url in grounded_sources) or "- None") + "\n\n"
        f"Fallback action ideas:\n" + ("\n".join(f"- {item}" for item in fallback_actions[:3]) or "- Follow official local guidance.") + "\n\n"
        "Return strict JSON with exactly these keys:\n"
        "{\n"
        '  "status": "verified|unconfirmed|debunked",\n'
        '  "confidence_score": 0,\n'
        '  "official_resource_url": "",\n'
        '  "summary": "",\n'
        '  "impact_summary": "",\n'
        '  "action_summary": "- action 1\\n- action 2\\n- action 3",\n'
        '  "rationale": ""\n'
        "}\n"
        "Decision rules:\n"
        "- Mark verified when official Indian sources clearly confirm the event.\n"
        "- Mark debunked when official Indian sources clearly deny or correct the claim.\n"
        "- Mark unconfirmed when confirmation is insufficient.\n"
        "- Prefer the best official Indian citation for official_resource_url.\n"
        "- Mention concrete dates where useful in summary or rationale.\n"
        "- Be conservative and do not infer confirmation from weak evidence."
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


def decide_story_status(story: Story, fallback_actions: list[str]) -> dict[str, Any]:
    evidence = list(story.evidence.select_related("raw_item__source"))
    evidence_lines = [
        f"{item.raw_item.source.name} (official={item.raw_item.source.is_official}): "
        f"{item.raw_item.headline} ({item.raw_item.url})"
        for item in evidence[:6]
    ]
    query = build_grounded_search_query(story)
    grounded_context = {"summary": "", "sources": [], "official_sources": [], "success": False, "provider": "gemini"}

    try:
        grounded_context = gemini_web_search(query)
        IntelligenceRun.objects.create(
            story=story,
            task_type=IntelligenceRun.TaskType.SCORING,
            provider="gemini",
            model_name=settings.GEMINI_MODEL,
            request_payload={"query": query},
            response_payload=grounded_context,
            success=grounded_context.get("success", False),
        )
    except Exception as exc:
        IntelligenceRun.objects.create(
            story=story,
            task_type=IntelligenceRun.TaskType.SCORING,
            provider="gemini",
            model_name=settings.GEMINI_MODEL,
            request_payload={"query": query},
            response_payload={"error": str(exc)},
            success=False,
        )

    if settings.OPENAI_API_KEY:
        prompt = _build_openai_decision_prompt(story, evidence_lines, grounded_context, fallback_actions)
        client = OpenAI(api_key=settings.OPENAI_API_KEY)
        try:
            response = client.responses.create(
                model=settings.OPENAI_MODEL,
                reasoning={"effort": settings.OPENAI_REASONING_EFFORT},
                input=[
                    {"role": "system", "content": OPENAI_DECISION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                max_output_tokens=700,
            )
            output_text = _extract_output_text(response)
            decision = _extract_json_object(output_text)
            IntelligenceRun.objects.create(
                story=story,
                task_type=IntelligenceRun.TaskType.SCORING,
                provider="openai",
                model_name=settings.OPENAI_MODEL,
                request_payload={"prompt": prompt, "query": query},
                response_payload={"output_text": output_text, "grounded_context": grounded_context},
                success=True,
            )
            return {
                "status": decision.get("status", Story.Status.UNCONFIRMED),
                "confidence_score": int(decision.get("confidence_score", 45) or 45),
                "official_resource_url": decision.get("official_resource_url", "") or "",
                "summary": decision.get("summary", "") or "",
                "impact_summary": decision.get("impact_summary", "") or "",
                "action_summary": decision.get("action_summary", "") or "",
                "rationale": decision.get("rationale", "") or "",
                "grounded_context": grounded_context,
            }
        except Exception as exc:
            IntelligenceRun.objects.create(
                story=story,
                task_type=IntelligenceRun.TaskType.SCORING,
                provider="openai",
                model_name=settings.OPENAI_MODEL,
                request_payload={"query": query},
                response_payload={"error": str(exc), "grounded_context": grounded_context},
                success=False,
            )

    has_local_official = any(item.raw_item.source.is_official for item in evidence)
    has_grounded_official = bool(grounded_context.get("official_sources"))
    if has_local_official or has_grounded_official:
        status = Story.Status.VERIFIED
        confidence = 85 if has_local_official else 70
    elif len({item.raw_item.source_id for item in evidence}) >= 2:
        status = Story.Status.VERIFIED
        confidence = 75
    else:
        status = Story.Status.UNCONFIRMED
        confidence = 45
    return {
        "status": status,
        "confidence_score": confidence,
        "official_resource_url": (grounded_context.get("official_sources") or [story.official_resource_url or ""])[0],
        "summary": "",
        "impact_summary": "",
        "action_summary": "",
        "rationale": "Fallback heuristic used because OpenAI decisioning was unavailable.",
        "grounded_context": grounded_context,
    }


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
