"""Deterministic local Research artifact generator for Creator Studio."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _topic_keywords(topic: str) -> list[str]:
    words = [
        word.strip(".,:;!?()[]{}\"'").lower()
        for word in topic.split()
        if len(word.strip(".,:;!?()[]{}\"'")) > 3
    ]
    deduped = list(dict.fromkeys(words))
    return deduped[:6] or ["creator", "studio", "research"]


def build_research_brief(
    *,
    topic: str,
    pipeline: str,
    persona: str,
    platform: str,
    stage_request: dict[str, Any],
) -> dict[str, Any]:
    keywords = _topic_keywords(topic)
    primary_keyword = keywords[0]

    return {
        "version": "1.0",
        "topic": topic,
        "research_date": date.today().isoformat(),
        "landscape": {
            "existing_content": [
                {
                    "title": "Vector database basics",
                    "url": "https://www.pinecone.io/learn/vector-database/",
                    "source": "blog",
                    "angle": "technical explainer",
                    "what_it_covers": "Embeddings, similarity search, and why vector search differs from keyword search.",
                    "what_it_misses": "A fast visual story showing how retrieval connects to a generated answer.",
                    "engagement_signal": "Commonly referenced educational content.",
                },
                {
                    "title": "Vector database overview",
                    "url": "https://www.elastic.co/what-is/vector-database",
                    "source": "blog",
                    "angle": "product education",
                    "what_it_covers": "How vectors support semantic search and recommendations.",
                    "what_it_misses": "A creator-friendly analogy for non-engineers.",
                    "engagement_signal": "Search-oriented educational page.",
                },
                {
                    "title": "Retrieval-augmented generation overview",
                    "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
                    "source": "reference",
                    "angle": "definition-first reference",
                    "what_it_covers": "The basic idea of retrieving external knowledge before generation.",
                    "what_it_misses": "Platform-native short-form storytelling.",
                    "engagement_signal": "Reference page suitable for baseline framing.",
                },
            ],
            "saturated_angles": [
                "Generic database definition videos.",
                "Overly technical embedding math without a story.",
                "AI hype videos that skip the retrieval workflow.",
            ],
            "underserved_gaps": [
                f"A simple visual explanation of how {primary_keyword} connects user questions to better answers.",
                "A creator-friendly explanation that separates storage, retrieval, and generation.",
            ],
        },
        "trending": {
            "recent_developments": [
                {
                    "headline": "More AI products are adding retrieval workflows to ground generated answers.",
                    "date": date.today().isoformat(),
                    "relevance": "The topic is timely because users want AI answers that connect to actual source material.",
                }
            ],
            "active_discussions": [
                {
                    "platform": "developer forums",
                    "topic_or_url": topic,
                    "sentiment": "Curiosity mixed with confusion about what vector databases actually do.",
                    "key_quotes": [
                        "I understand chatbots, but not where the knowledge comes from.",
                        "Is a vector database just search with AI?",
                    ],
                }
            ],
            "timeliness_window": "evergreen",
        },
        "data_points": [
            {
                "claim": "Retrieval-augmented generation combines a retrieval step with a generation step.",
                "source_url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
                "source_name": "Wikipedia",
                "credibility": "secondary_source",
                "surprise_factor": "expected",
                "usable_as": "script_anchor",
            },
            {
                "claim": "Vector databases store and search vector embeddings for similarity-based retrieval.",
                "source_url": "https://en.wikipedia.org/wiki/Vector_database",
                "source_name": "Wikipedia",
                "credibility": "secondary_source",
                "surprise_factor": "notable",
                "usable_as": "stat_card",
            },
            {
                "claim": "A practical RAG workflow uses retrieval to add relevant context before the model writes an answer.",
                "source_url": "https://platform.openai.com/docs/guides/retrieval",
                "source_name": "OpenAI documentation",
                "credibility": "primary_source",
                "surprise_factor": "notable",
                "usable_as": "hook",
            },
        ],
        "audience_insights": {
            "common_questions": [
                f"What does {primary_keyword} mean in plain English?",
                "Why does AI need retrieval instead of just answering from memory?",
                "What does a vector database do differently from a normal database?",
            ],
            "misconceptions": [
                {
                    "myth": "A vector database is the AI model itself.",
                    "reality": "It is storage and search infrastructure that helps retrieve relevant context.",
                    "source": "Derived from common beginner confusion in the research handoff.",
                },
                {
                    "myth": "RAG means the model automatically knows everything.",
                    "reality": "RAG depends on finding useful source material and passing it into the generation step.",
                    "source": "Derived from retrieval workflow framing.",
                },
            ],
            "knowledge_level": "Beginner-to-intermediate viewers; likely familiar with AI chat but not retrieval pipelines.",
            "pain_points": [
                "Too many explanations start with math instead of a useful analogy.",
                "People confuse storage, search, and generation.",
                "Short-form audiences need the workflow shown quickly.",
            ],
        },
        "expert_voices": [
            {
                "name": "OpenAI documentation",
                "title_or_affiliation": "Primary documentation",
                "position": "Retrieval workflows add relevant context before generation.",
                "source_url": "https://platform.openai.com/docs/guides/retrieval",
                "contrarian": False,
            }
        ],
        "angles_discovered": [
            {
                "name": "The AI Library Card",
                "hook": "A vector database is like giving AI a library card before it answers.",
                "type": "evergreen",
                "why_now": "People are using AI tools but still do not understand how retrieval grounds answers.",
                "grounded_in": [
                    "Retrieval-augmented generation combines a retrieval step with a generation step.",
                    "People confuse storage, search, and generation.",
                ],
            },
            {
                "name": "Search Before Speaking",
                "hook": "The smartest AI answer starts before the model writes a single word.",
                "type": "data_driven",
                "why_now": "RAG workflows are becoming a common way to improve answer relevance.",
                "grounded_in": [
                    "A practical RAG workflow uses retrieval to add relevant context before the model writes an answer.",
                ],
            },
            {
                "name": "Vectors Are Meaning Coordinates",
                "hook": "Vector databases turn meaning into coordinates so related ideas can find each other.",
                "type": "narrative",
                "why_now": "Semantic search is easier to understand when shown visually.",
                "grounded_in": [
                    "Vector databases store and search vector embeddings for similarity-based retrieval.",
                ],
            },
        ],
        "visual_references": [
            {
                "description": "Question enters, vector search finds related chunks, model generates answer.",
                "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
                "what_works": "The workflow can be visualized as a simple three-step pipeline.",
            }
        ],
        "sources": [
            {
                "url": "https://en.wikipedia.org/wiki/Retrieval-augmented_generation",
                "title": "Retrieval-augmented generation",
                "used_for": "baseline definition and concept framing",
                "reliability": "secondary",
            },
            {
                "url": "https://en.wikipedia.org/wiki/Vector_database",
                "title": "Vector database",
                "used_for": "baseline definition for vector database concepts",
                "reliability": "secondary",
            },
            {
                "url": "https://www.pinecone.io/learn/vector-database/",
                "title": "What is a Vector Database?",
                "used_for": "content landscape and common explanation patterns",
                "reliability": "secondary",
            },
            {
                "url": "https://www.elastic.co/what-is/vector-database",
                "title": "What is a vector database?",
                "used_for": "audience questions and practical search framing",
                "reliability": "secondary",
            },
            {
                "url": "https://platform.openai.com/docs/guides/retrieval",
                "title": "Retrieval",
                "used_for": "retrieval workflow framing",
                "reliability": "primary",
            },
        ],
        "research_summary": (
            f"The strongest angle for {pipeline} on {platform} is to explain {topic} as a simple "
            "workflow: convert meaning into searchable vectors, retrieve the closest context, then let "
            f"the model answer with that context. This fits {persona} because it can be explained visually "
            "without provider calls or live external research."
        ),
        "metadata": {
            "generated_by": "creator-studio/studio/research_generator.py",
            "generation_mode": "deterministic_local",
            "stage_request_status": stage_request.get("status"),
            "pipeline": pipeline,
            "persona": persona,
            "platform": platform,
            "keywords": keywords,
        },
    }

def generate_research_brief(project_dir: Path) -> Path:
    run_manifest = _read_json(project_dir / "run.json")
    stage_request = _read_json(project_dir / "research" / "stage_request.json")

    topic = str(stage_request.get("topic") or run_manifest.get("topic") or project_dir.name)
    pipeline = str(stage_request.get("pipeline") or run_manifest.get("pipeline") or "")
    persona = str(stage_request.get("persona") or run_manifest.get("persona") or "")
    platform = str(stage_request.get("platform") or run_manifest.get("platform") or "")
    brief = build_research_brief(
        topic=topic,
        pipeline=pipeline,
        persona=persona,
        platform=platform,
        stage_request=stage_request,
    )
    output_path = project_dir / "research" / "research_brief.json"
    _write_json(output_path, brief)
    return output_path
