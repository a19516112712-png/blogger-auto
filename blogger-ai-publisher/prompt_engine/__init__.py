"""AI Prompt Engine — production-ready prompt generation for baby name article images.

Components:
    analyzer.py     — Analyze article titles for SEO intent and topic classification.
    builder.py      — Build image prompts from YAML component libraries.
    validator.py    — Validate prompts for length, keywords, negative constraints.
    scorer.py       — Score prompts against weighted quality criteria.
    generator.py    — Full pipeline: analyze → build → validate → score → dedup.
    models.py       — Shared dataclasses (PromptAnalysis, GeneratedPrompt, etc.).
"""
