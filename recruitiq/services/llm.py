"""Optional helper that rewrites interview questions to fit a role. It is off unless an API key is set.

What it is allowed to see: the job title and skill names. It is never sent resume text, names or emails, so there is
nothing personal to leak, and nothing in scoring depends on it. The reply is validated, and on any problem the
deterministic questions are used instead.
"""
import json
import logging

import httpx
from pydantic import BaseModel, Field, ValidationError

log = logging.getLogger(__name__)
MODELS = ["openai/gpt-oss-120b:free", "qwen/qwen3-next-80b-a3b-instruct:free", "google/gemma-4-31b-it:free"]


class Questions(BaseModel):
    questions: list[str] = Field(min_length=2, max_length=6)


def refine_questions(api_key: str, job_title: str, skills: list[str], base: list[str],
                     base_url: str = "https://openrouter.ai/api/v1", transport=None, models=None) -> list[str] | None:
    if not api_key:
        return None
    prompt = (f"Rewrite these interview questions so they fit a '{job_title}' role that uses: {', '.join(skills) or 'general skills'}. "
              "Keep each question open ended, about the candidate's own work, free of trick questions and of anything about age, family, "
              "health, nationality or religion. Return only JSON like {\"questions\": [\"...\"]}.\n\n" + "\n".join(f"- {q}" for q in base))
    for model in models or MODELS:
        try:
            with httpx.Client(timeout=20, transport=transport) as c:
                r = c.post(f"{base_url}/chat/completions", headers={"Authorization": f"Bearer {api_key}"},
                           json={"model": model, "temperature": 0.3, "max_tokens": 400,
                                 "messages": [{"role": "user", "content": prompt}]})
                r.raise_for_status()
                text = r.json()["choices"][0]["message"]["content"]
            start, end = text.find("{"), text.rfind("}")
            return Questions.model_validate(json.loads(text[start:end + 1])).questions
        except (httpx.HTTPError, KeyError, ValueError, ValidationError) as e:
            log.warning("llm model %s failed: %s", model, type(e).__name__)
    return None
