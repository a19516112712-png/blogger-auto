def generate_article_with_retry(client: OpenAI, topic: dict) -> str | None:
    """Generate an article with retry logic for transient failures."""
    global _quota_exhausted
    keyword = topic["keyword"]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            active_model = MODEL
            response = client.chat.completions.create(
                model=active_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Write an SEO-optimized blog article about: {keyword}"},
                ],
                temperature=0.9,
                top_p=0.95,
                max_tokens=8192,
            )

            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
            log.warning("Attempt %d: empty response for '%s'.", attempt, keyword)
        except Exception as model_exc:
            exc_str = str(model_exc).lower()
            status_code = getattr(model_exc, "status_code", None)

            # Model not found — try fallback
            if "model_not_found" in exc_str and active_model != FALLBACK_MODEL:
                log.warning("Model '%s' not found, falling back to '%s'.", active_model, FALLBACK_MODEL)
                try:
                    active_model = FALLBACK_MODEL
                    response = client.chat.completions.create(
                        model=active_model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": f"Write an SEO-optimized blog article about: {keyword}"},
                        ],
                        temperature=0.9,
                        top_p=0.95,
                        max_tokens=8192,
                    )
                    if response.choices and response.choices[0].message.content:
                        return response.choices[0].message.content
                except Exception:
                    pass
                continue

            # Rate limit
            if status_code == 429 or "429" in exc_str or "rate_limit" in exc_str or "resource_exhausted" in exc_str:
                log.warning("[WARNING] Agnes AI rate limit exceeded (429).")
                if not _quota_exhausted:
                    set_quota_exhausted()
                return None

            # Retryable errors
            if status_code in RETRYABLE_CODES or any(str(c) in exc_str for c in RETRYABLE_CODES) or "timeout" in exc_str:
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt - 1]
                    log.warning("Attempt %d/%d failed (%s). Retrying in %ds…", attempt, MAX_RETRIES, type(model_exc).__name__, delay)
                    time.sleep(delay)
                    continue

            log.error("Agnes AI API error for '%s' (attempt %d): %s", keyword, attempt, model_exc)
            return None

    log.error("All %d retries exhausted for topic '%s'.", MAX_RETRIES, keyword)
    return None
