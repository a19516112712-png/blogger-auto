#!/usr/bin/env python3
"""
Keyword Discovery Engine — Unlimited Combinatorial Topic Generator

Replaces the old static TOPICS array and limited keyword_discovery.
Generates 10,000+ unique long-tail keywords from combinatorial dimensions.

Dimensions:
  Meaning, Origin, Gender, Popularity, Religion, Nature, Animals,
  Flowers, Colors, Season, Letter, Ending, Middle Names, Sibling Names,
  Twin Names, Nicknames, Rare, Vintage, Modern, Country, Language,
  Mythology, Occupation, Celebrity Trend, Current Year

Every generated keyword is checked against the SQLite database before
insertion — zero duplicates guaranteed.

Usage:
    from database.topic_queue import TopicQueue
    from keyword_discovery import discover_keywords
    
    q = TopicQueue()
    keywords = discover_keywords(q, count=100)
    q.bulk_insert_keywords(keywords)
"""

import hashlib
import logging
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Combinatorial dimension pools
# ---------------------------------------------------------------------------

MEANINGS = [
    "love", "hope", "light", "peace", "joy", "strength", "grace", "wisdom",
    "miracle", "blessing", "dream", "star", "brave", "courage", "faith",
    "truth", "honor", "victory", "freedom", "kindness", "beauty", "power",
    "courage", "valor", "noble", "gentle", "pure", "bright", "swift",
    "calm", "serene", "radiant", "divine", "eternal", "wise", "strong",
    "fierce", "bold", "free", "wild", "sweet", "soft", "warm", "cool",
    "fair", "just", "true", "good", "kind", "dear", "precious", "rare",
]

ORIGINS = [
    "Irish", "Japanese", "Korean", "French", "Italian", "Spanish", "German",
    "Arabic", "Greek", "Scandinavian", "Celtic", "Nordic", "Russian",
    "Polish", "Dutch", "Hawaiian", "African", "Indian", "Persian", "Chinese",
    "Hebrew", "Latin", "Slavic", "Portuguese", "Turkish", "Egyptian",
    "Mayan", "Aztec", "Sanskrit", "Welsh", "Scottish", "English",
    "Norman", "Basque", "Finnish", "Estonian", "Lithuanian", "Ukrainian",
]

GENGENDERS = ["baby", "boy", "girl", "unisex", "gender-neutral"]

POPULARITY = ["popular", "trending", "classic", "modern", "vintage",
              "unique", "rare", "obscure", "hidden gem", "rising",
              "timeless", "traditional", "contemporary", "new", "fresh"]

RELIGIONS = ["biblical", "christian", "hebrew", "muslim", "hindu",
             "buddhist", "jewish", "catholic", "orthodox", "spiritual",
             "saint", "angelic", "monastic", "pagan", "druid"]

NATURE = [
    "flower", "tree", "ocean", "mountain", "river", "lake", "sea",
    "forest", "garden", "meadow", "field", "valley", "hill", "cliff",
    "canyon", "desert", "island", "beach", "shore", "wave", "tide",
    "stream", "brook", "pond", "spring", "glacier", "volcano", "crater",
]

ANIMALS = [
    "bird", "eagle", "hawk", "falcon", "owl", "raven", "dove", "swan",
    "crane", "heron", "sparrow", "robin", "lark", "thrush", "finch",
    "lion", "tiger", "wolf", "bear", "fox", "deer", "stag", "hare",
    "rabbit", "horse", "wolf", "panther", "leopard", "cheetah", "jaguar",
    "fish", "dolphin", "whale", "shark", "salmon", "trout", "bass",
    "dragon", "phoenix", "griffin", "unicorn", "centaur", "satyr",
]

FLOWERS = [
    "rose", "lily", "daisy", "violet", "jasmine", "tulip", "orchid",
    "lavender", "lotus", "iris", "peony", "hibiscus", "magnolia",
    "azalea", "camellia", "chrysanthemum", "sunflower", "poppy",
    "marigold", "blossom", "petal", "fern", "ivy", "willow", "birch",
]

COLORS = [
    "red", "blue", "green", "gold", "silver", "ivory", "pearl", "ruby",
    "emerald", "sapphire", "diamond", "amber", "coral", "jade", "bronze",
    "crimson", "scarlet", "azure", "teal", "violet", "indigo", "mauve",
    "lavender", "ochre", "sienna", "umber", "ebony", "ivory", "cream",
]

SEASONS = ["spring", "summer", "autumn", "winter", "seasonal"]

LETTERS = list("abcdefghijklmnopqrstuvwxyz")

ENDINGS = [
    "a", "ia", "ea", "oa", "ua",  # feminine
    "o", "io", "eo", "ao",       # masculine
    "er", "or", "ar", "ir", "ur",
    "ley", "leigh", "ly", "ney",
    "wood", "worth", "ton", "field", "dale", "gate",
    "ette", "elle", "ine", "ine", "elle",
    "wen", "lyn", "ynn", "ren",
    "ith", "iel", "iel", "iel",
]

YEARS = [str(y) for y in range(2025, 2035)]

MYTHOLOGIES = [
    "greek", "roman", "norse", "egyptian", "celtic", "hindu",
    "japanese", "korean", "chinese", "mesopotamian", "babylonian",
    "persian", "aztec", "maya", "inca", "polynesian", "welsh",
    "irish", "scottish", "finnish", "slavic", "tibetan", "thai",
]

OCCUPATIONS = [
    "king", "queen", "prince", "princess", "noble", "royal",
    "warrior", "knight", "soldier", "guardian", "protector",
    "scholar", "teacher", "healer", "artist", "musician",
    "poet", "writer", "singer", "dancer", "painter",
    "hunter", "fisher", "weaver", "smith", "builder",
    "leader", "chief", "ruler", "ranger", "scout",
]

CELEBRITY_TRENDS = [
    "celebrity", "influencer", "instagram", "tiktok", "viral",
    "modern celebrity", "hollywood", "pop star", "rock star",
]

# ---------------------------------------------------------------------------
# Template library — each template produces semantically valid keywords
# ---------------------------------------------------------------------------

TEMPLATES = [
    # Meaning-based
    "{gender} names that mean {meaning}",
    "names meaning {meaning} for {gender}",
    "{gender} baby names with meaning {meaning}",
    "meaning of {gender} name {meaning}",
    
    # Origin-based
    "{origin} {gender} baby names",
    "{origin} baby names and meanings for {gender}",
    "traditional {origin} {gender} names",
    "modern {origin} {gender} baby names",
    "{origin} {gender} names with meanings",
    "ancient {origin} {gender} names",
    "{origin} {gender} names starting with {letter}",
    "{origin} {gender} names ending with {ending}",
    
    # Nature-based
    "nature {gender} baby names",
    "{nature} inspired {gender} names",
    "{flower} names for {gender}",
    "{animal} names for babies",
    "{color} themed {gender} names",
    "{season} inspired {gender} baby names",
    "{nature} {gender} baby names",
    
    # Mythology
    "{mythology} {gender} baby names",
    "{mythology} mythology {gender} names",
    "norse {gender} warrior names",
    "greek {gender} god names",
    
    # Style
    "{popularity} {gender} baby names",
    "unique {gender} baby names",
    "rare {gender} names",
    "vintage {gender} baby names",
    "modern {gender} baby names",
    "classic {gender} names",
    
    # Letter-based
    "{gender} baby names starting with {letter}",
    "baby names beginning with {letter} for {gender}",
    "{origin} {gender} names starting with {letter}",
    
    # Ending-based
    "{gender} names ending with {ending}",
    "baby names that end in {ending} for {gender}",
    "{origin} {gender} names ending with {ending}",
    
    # Middle names
    "best middle names for {gender}",
    "{origin} middle names for {gender}",
    "nature middle names for {gender}",
    "unique middle names for {gender}",
    "{popularity} middle names for {gender}",
    "{meaning} middle names for {gender}",
    
    # Sibling names
    "sibling names to match {gender}",
    "matching sibling names for {gender}",
    "{origin} sibling name sets for {gender}",
    "coordinated sibling names for {gender}",
    
    # Twin names
    "twin names for {gender} babies",
    "{origin} twin names for {gender}",
    "matching twin names for {gender}",
    "unique twin name pairs for {gender}",
    
    # Nicknames
    "cute nicknames for {gender} names",
    "{origin} nickname ideas for {gender}",
    "sweet nicknames for {gender}",
    "funny nicknames for {gender} babies",
    
    # Occasion
    "{season} {gender} baby names",
    "{color} themed {gender} names",
    "{mythology} inspired {gender} names",
    
    # Year
    "{gender} baby names {year}",
    "trending {gender} names {year}",
    "popular {gender} names {year}",
    
    # Occupations
    "{occupation} inspired {gender} names",
    "royal {gender} baby names",
    "warrior {gender} names",
]


def _normalize(keyword: str) -> str:
    """Normalize a keyword for dedup comparison."""
    return re.sub(r"\s+", " ", keyword.strip().lower())


def _keyword_hash(keyword: str) -> str:
    """SHA-256 hash for content dedup."""
    return hashlib.sha256(_normalize(keyword).encode()).hexdigest()[:16]


def discover_keywords(queue, count: int = 100,
                      history_blacklist: Optional[set] = None) -> list[tuple]:
    """Discover up to `count` unique keywords.

    Args:
        queue: TopicQueue instance for duplicate checking.
        count: Maximum keywords to generate.
        history_blacklist: Set of already-seen keywords (legacy compat).

    Returns:
        List of tuples: (keyword, intent, cluster, priority, difficulty,
                         search_volume, cpc)
    """
    seen = set()
    if history_blacklist:
        seen = {_normalize(h) for h in history_blacklist}

    # Also check database
    db_keywords = set()
    try:
        existing = queue.conn.execute(
            "SELECT LOWER(keyword) FROM keywords"
        ).fetchall()
        db_keywords = {r[0] for r in existing}
    except Exception:
        pass

    seen |= db_keywords

    candidates = []
    attempts = 0
    max_attempts = count * 50  # Safety limit

    random.seed()  # Fresh seed per run

    while len(candidates) < count and attempts < max_attempts:
        attempts += 1

        # Pick random template and random dimension values
        template = random.choice(TEMPLATES)
        keyword = _fill_template(template)
        normalized = _normalize(keyword)

        if normalized in seen:
            continue

        seen.add(normalized)

        # Score the keyword
        intent, cluster, priority, difficulty, volume, cpc = _score_keyword(keyword)

        candidates.append((
            keyword, intent, cluster, priority, difficulty, volume, cpc,
        ))

    log.info("Keyword discovery: %d unique keywords in %d attempts",
             len(candidates), attempts)
    return candidates


def _fill_template(template: str) -> str:
    """Fill a template with random dimension values."""
    replacements = {
        "{meaning}": random.choice(MEANINGS),
        "{origin}": random.choice(ORIGINS),
        "{gender}": random.choice(GENGENDERS),
        "{popularity}": random.choice(POPULARITY),
        "{religion}": random.choice(RELIGIONS),
        "{nature}": random.choice(NATURE),
        "{animal}": random.choice(ANIMALS),
        "{flower}": random.choice(FLOWERS),
        "{color}": random.choice(COLORS),
        "{season}": random.choice(SEASONS),
        "{letter}": random.choice(LETTERS),
        "{ending}": random.choice(ENDINGS),
        "{year}": random.choice(YEARS),
        "{mythology}": random.choice(MYTHOLOGIES),
        "{occupation}": random.choice(OCCUPATIONS),
    }

    keyword = template
    for placeholder, value in replacements.items():
        keyword = keyword.replace(placeholder, value)

    # Clean up double spaces
    keyword = re.sub(r"\s+", " ", keyword).strip()
    return keyword


def _score_keyword(keyword: str) -> tuple:
    """Score a keyword for CPC, intent, cluster, priority, difficulty, volume."""
    kw = keyword.lower()

    # CPC lookup (from old keyword_discovery.py, enhanced)
    cpc_map = {
        "meaning": 2.85, "girl": 2.40, "boy": 2.35, "unique": 2.20,
        "gender": 2.10, "middle name": 1.95, "biblical": 1.90,
        "japanese": 1.85, "vintage": 1.80, "rare": 1.75,
        "irish": 1.65, "nature": 1.60, "strong": 1.55,
        "modern": 1.50, "twin": 1.45, "greek": 1.40,
        "french": 1.35, "italian": 1.30, "spanish": 1.25,
        "german": 1.20, "korean": 1.05, "arabic": 1.00,
        "letter": 1.80, "short": 1.70, "cute": 1.90,
        "flower": 1.60, "ocean": 1.55, "star": 1.50,
        "mythology": 1.15, "royal": 1.00, "nick": 1.30,
        "sibling": 1.25, "ending": 1.10,
    }

    cpc = 0.50
    for term, value in cpc_map.items():
        if term in kw:
            cpc = max(cpc, value)

    # Intent classification
    if "meaning" in kw or "mean" in kw:
        intent = "LIST_INTENT"
    elif any(o in kw for o in ORIGINS):
        intent = "ORIGIN_INTENT"
    elif "twin" in kw:
        intent = "LIST_INTENT"
    elif "middle name" in kw or "sibling" in kw or "nickname" in kw:
        intent = "ADVICE_INTENT"
    elif "starting with" in kw or "ending with" in kw:
        intent = "LETTER_INTENT"
    elif "unique" in kw or "rare" in kw or "popular" in kw:
        intent = "TREND_INTENT"
    else:
        intent = "LIST_INTENT"

    # Cluster
    cluster = "uncategorized"
    for o in ORIGINS:
        if o.lower() in kw:
            cluster = f"origin_{o.lower()}"
            break
    if cluster == "uncategorized":
        for n in NATURE:
            if n in kw:
                cluster = f"nature_{n}"
                break
    if cluster == "uncategorized":
        for m in MEANINGS[:10]:
            if m in kw:
                cluster = f"meaning_{m}"
                break

    # Priority (higher = more valuable)
    priority = 50.0
    if cpc >= 2.0:
        priority = 80.0
    elif cpc >= 1.5:
        priority = 65.0
    if "unique" in kw or "rare" in kw:
        priority += 10
    if "middle" in kw or "sibling" in kw:
        priority += 5

    # Difficulty (lower = easier to rank)
    difficulty = 60.0
    if "baby names" in kw:
        difficulty = 75.0
    if "unique" in kw or "rare" in kw:
        difficulty = 40.0
    for o in ORIGINS:
        if o.lower() in kw:
            difficulty = min(difficulty, 35.0)
            break

    # Volume estimate
    volume = 1000
    if cpc >= 2.0:
        volume = 10000
    elif cpc >= 1.5:
        volume = 5000
    if "unique" in kw or "rare" in kw:
        volume = max(volume, 3000)

    return intent, cluster, round(priority, 1), round(difficulty, 1), volume, round(cpc, 2)
