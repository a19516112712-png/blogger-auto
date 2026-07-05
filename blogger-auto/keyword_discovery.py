#!/usr/bin/env python3
"""
Keyword Discovery Engine — Production-Grade Combinatorial Topic Generator

Generates 10,000+ unique long-tail keywords from combinatorial dimensions.
Every keyword is checked against SQLite before insertion — zero duplicates.

Search Intent Categories:
  LIST_INTENT       — "100 X Baby Names" listicles
  MEANING_INTENT    — "baby names that mean X"
  ORIGIN_INTENT     — "X origin baby names"
  STYLE_INTENT      — "X-style baby names"
  TREND_INTENT      — "trending/popular X names"
  ADVICE_INTENT     — "how to choose X names"
  COMPARISON_INTENT — "X vs Y baby names"
  GUIDE_INTENT      — "complete guide to X names"

Dimensions:
  Meaning, Origin, Style, Gender, Popularity, Religion, Nature,
  Animals, Flowers, Colors, Seasons, Letters, Endings, Mythology,
  Occupations, Celebrity, Historical, Geographic, Cultural,
  Phonetics, Syllables, Length, Rarity, Era, Theme
"""

import hashlib
import logging
import random
import re
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)

# =========================================================================
# DIMENSION POOLS
# =========================================================================

MEANINGS = [
    "love", "hope", "light", "peace", "joy", "strength", "grace", "wisdom",
    "miracle", "blessing", "dream", "star", "brave", "courage", "faith",
    "truth", "honor", "victory", "freedom", "kindness", "beauty", "power",
    "valor", "noble", "gentle", "pure", "bright", "swift", "calm",
    "serene", "radiant", "divine", "eternal", "wise", "strong", "fierce",
    "bold", "free", "wild", "sweet", "soft", "warm", "cool", "fair",
    "just", "true", "good", "kind", "dear", "precious", "rare", "golden",
    "silver", "crystal", "diamond", "pearl", "ruby", "emerald", "sapphire",
    "amber", "coral", "jade", "bronze", "crimson", "scarlet", "azure",
    "teal", "violet", "indigo", "lavender", "ochre", "sienna", "ebony",
    "ivory", "cream", "snow", "fire", "earth", "water", "air", "sky",
    "sun", "moon", "angel", "hero", "queen", "king", "prince", "princess",
    "warrior", "guardian", "protector", "leader", "ruler", "chief",
]

ORIGINS = [
    "Irish", "Japanese", "Korean", "French", "Italian", "Spanish", "German",
    "Arabic", "Greek", "Scandinavian", "Celtic", "Nordic", "Russian",
    "Polish", "Dutch", "Hawaiian", "African", "Indian", "Persian", "Chinese",
    "Hebrew", "Latin", "Slavic", "Portuguese", "Turkish", "Egyptian",
    "Mayan", "Aztec", "Sanskrit", "Welsh", "Scottish", "English",
    "Norman", "Basque", "Finnish", "Estonian", "Lithuanian", "Ukrainian",
    "Romanian", "Czech", "Hungarian", "Icelandic", "Swedish", "Norwegian",
    "Danish", "Gaelic", "Breton", "Cornish", "Manx", "Georgian", "Armenian",
    "Tibetan", "Mongolian", "Vietnamese", "Thai", "Burmese", "Cambodian",
    "Indonesian", "Malay", "Filipino", "Maori", "Samoan", "Tongan",
    "Zulu", "Xhosa", "Swahili", "Yoruba", "Igbo", "Amharic", "Somali",
    "Berber", "Kurdish", "Pashto", "Urdu", "Bengali", "Tamil", "Telugu",
    "Kannada", "Malayalam", "Marathi", "Gujarati", "Punjabi", "Nepali",
    "Bhutanese", "Lao", "Khmer", "Balinese", "Javanese", "Sundanese",
]

STYLES = [
    "modern", "vintage", "classic", "contemporary", "traditional",
    "bohemian", "minimalist", "elegant", "rustic", "farmhouse",
    "glamorous", "hippie", "retro", "mid-century", "art deco",
    "gothic", "romantic", "dramatic", "subtle", "bold",
    "delicate", "strong", "feminine", "masculine", "unisex",
    "gender-neutral", "whimsical", "dreamy", "ethereal", "mystical",
    "magical", "enchanted", "fairytale", "storybook", "legendary",
    "mythical", "fantasy", "sci-fi", "futuristic", "prehistoric",
    "ancient", "medieval", "renaissance", "baroque", "rococo",
    "impressionist", "surrealist", "cubist", "abstract", "geometric",
]

GENDERS = ["baby", "boy", "girl", "unisex", "gender-neutral", "male", "female"]

POPULARITIES = [
    "popular", "trending", "classic", "modern", "vintage",
    "unique", "rare", "obscure", "hidden gem", "rising",
    "timeless", "traditional", "contemporary", "new", "fresh",
    "popular", "common", "uncommon", "extraordinary", "remarkable",
    "extraordinary", "stunning", "captivating", "mesmerizing",
    "enchanting", "irresistible", "irreplaceable", "incomparable",
]

RELIGIONS = [
    "biblical", "christian", "hebrew", "muslim", "hindu",
    "buddhist", "jewish", "catholic", "orthodox", "spiritual",
    "saint", "angelic", "monastic", "pagan", "druid",
    "shinto", "confucian", "taoist", "zoroastrian", "sikh",
    "dharmic", "vedic", "torah", "quran", "gospel",
]

NATURE_ELEMENTS = [
    "flower", "tree", "ocean", "mountain", "river", "lake", "sea",
    "forest", "garden", "meadow", "field", "valley", "hill", "cliff",
    "canyon", "desert", "island", "beach", "shore", "wave", "tide",
    "stream", "brook", "pond", "spring", "glacier", "volcano", "crater",
    "cave", "waterfall", "waterway", "marsh", "swamp", "wetland",
    "tundra", "savanna", "prairie", "steppe", "plateau", "mesa",
    "ridge", "peak", "summit", "basin", "delta", "estuary", "reef",
    "atoll", "peninsula", "isthmus", "glacier", "fjord", "geyser",
]

ANIMALS = [
    "bird", "eagle", "hawk", "falcon", "owl", "raven", "dove", "swan",
    "crane", "heron", "sparrow", "robin", "lark", "thrush", "finch",
    "lion", "tiger", "wolf", "bear", "fox", "deer", "stag", "hare",
    "rabbit", "horse", "panther", "leopard", "cheetah", "jaguar",
    "fish", "dolphin", "whale", "shark", "salmon", "trout", "bass",
    "dragon", "phoenix", "griffin", "unicorn", "centaur", "satyr",
    "kitten", "puppy", "cub", "foal", "lamb", "kid", "chick",
    "butterfly", "moth", "bee", "ant", "ladybug", "dragonfly",
    "firefly", "cricket", "frog", "toad", "turtle", "tortoise",
    "snail", "octopus", "jellyfish", "seahorse", "starfish",
    "parrot", "macaw", "toucan", "hummingbird", "pelican", "flamingo",
    "peacock", "penguin", "alpaca", "llama", "camel", "giraffe",
    "zebra", "gorilla", "chimp", "orangutan", "koala", "kangaroo",
    "platypus", "echidna", "wombat", "possum", "raccoon", "otter",
    "badger", "weasel", "mink", "ferret", "mongoose", "hyena",
    "elephant", "rhino", "hippo", "buffalo", "bison", "mammoth",
]

FLOWERS = [
    "rose", "lily", "daisy", "violet", "jasmine", "tulip", "orchid",
    "lavender", "lotus", "iris", "peony", "hibiscus", "magnolia",
    "azalea", "camellia", "chrysanthemum", "sunflower", "poppy",
    "marigold", "blossom", "petal", "fern", "ivy", "willow", "birch",
    "maple", "oak", "cedar", "pine", "elm", "ash", "birch",
    "cherry", "plum", "apple", "pear", "peach", "mango", "papaya",
    "lavender", "sage", "thyme", "mint", "basil", "rosemary", "dill",
    "cactus", "bamboo", "reeds", "lotus", "wisteria", "gardenia",
    "begonia", "zinnia", "dahlia", "aster", "primrose", "hyacinth",
    "bluebell", "crocus", "daffodil", "cornflower", "forget-me-not",
]

COLORS = [
    "red", "blue", "green", "gold", "silver", "ivory", "pearl", "ruby",
    "emerald", "sapphire", "diamond", "amber", "coral", "jade", "bronze",
    "crimson", "scarlet", "azure", "teal", "violet", "indigo", "mauve",
    "lavender", "ochre", "sienna", "umber", "ebony", "cream", "white",
    "black", "pink", "orange", "yellow", "purple", "brown", "gray",
    "charcoal", "blonde", "auburn", "chestnut", "mahogany", "walnut",
    "copper", "titanium", "platinum", "steel", "iron", "zinc",
    "cerulean", "cobalt", "turquoise", "mint", "lime", "olive",
    "burgundy", "maroon", "navy", "khaki", "tan", "beige", "sand",
    "honey", "caramel", "chocolate", "coffee", "espresso", "mocha",
]

SEASONS = ["spring", "summer", "autumn", "winter", "seasonal"]

LETTERS = list("abcdefghijklmnopqrstuvwxyz")

ENDINGS = [
    "a", "ia", "ea", "oa", "ua",
    "o", "io", "eo", "ao",
    "er", "or", "ar", "ir", "ur",
    "ley", "leigh", "ly", "ney",
    "wood", "worth", "ton", "field", "dale", "gate",
    "ette", "elle", "ine", "wen", "lyn", "ynn", "ren",
    "ith", "iel", "ius", "ara", "ela", "ina", "ona", "ula",
    "rio", "mio", "nio", "lio", "gio", "pio", "vio",
    "den", "ton", "lyn", "ley", "ford", "bridge", "vale", "crest",
    "stone", "rock", "cloud", "rain", "storm", "wind", "snow", "ice",
]

YEARS = [str(y) for y in range(2025, 2040)]

MYTHOLOGIES = [
    "greek", "roman", "norse", "egyptian", "celtic", "hindu",
    "japanese", "korean", "chinese", "mesopotamian", "babylonian",
    "persian", "aztec", "maya", "inca", "polynesian", "welsh",
    "irish", "scottish", "finnish", "slavic", "tibetan", "thai",
    "sumerian", "phoenician", "etruscan", "iberian", "thracian",
    "dacian", "illyrian", "thuringian", "gothic", "vandalian",
    "visigothic", "ostrogothic", "lombard", "frankish", "saxon",
    "anglo-saxon", "vikings", "druidic", "shamanic", "totemic",
]

OCCUPATIONS = [
    "king", "queen", "prince", "princess", "noble", "royal",
    "warrior", "knight", "soldier", "guardian", "protector",
    "scholar", "teacher", "healer", "artist", "musician",
    "poet", "writer", "singer", "dancer", "painter",
    "hunter", "farmer", "fisher", "weaver", "smith", "baker",
    "merchant", "trader", "navigator", "explorer", "inventor",
    "scientist", "philosopher", "general", "admiral", "captain",
    "judge", "lawyer", "doctor", "priest", "monk", "nun",
    "wizard", "witch", "mage", "sorcerer", "enchanter",
    "astronomer", "architect", "engineer", "physician", "surgeon",
    "diplomat", "ambassador", "statesman", "emperor", "sultan",
    "caliph", "pharaoh", "samurai", "shogun", "daimyo",
]

GEOS = [
    "European", "Asian", "African", "American", "Australian",
    "Mediterranean", "Caribbean", "Pacific", "Atlantic", "Arctic",
    "Antarctic", "Central", "South", "North", "East", "West",
    "Southern", "Northern", "Eastern", "Western", "Global",
    "International", "Universal", "Cosmic", "Celestial", "Galactic",
    "Interstellar", "Lunar", "Solar", "Planetary", "Terrestrial",
    "Oceanic", "Continental", "Subtropical", "Tropical", "Temperate",
    "Alpine", "Coastal", "Desert", "Island", "Mountain", "Valley",
    "River", "Forest", "Savanna", "Prairie", "Tundra", "Jungle",
    "Rainforest", "Volcanic", "Glacial", "Aquatic", "Marine",
]

PHONETICS = [
    "soft-spoken", "melodic", "rhythmic", "harmonic", "sonorous",
    "resonant", "dulcet", "lyrical", "musical", "symphonic",
    "harmonious", "euphonious", "cacophonous", "alliterative",
    "syllabic", "vowel-rich", "consonant-heavy", "open-syllabled",
    "closed-syllabled", "diphthong", "triphthong", "nasal",
    "guttural", "liquid", "glide", "plosive", "fricative",
    "affricate", "tap", "trill", "lateral", "velar", "palatal",
    "alveolar", "dental", "labial", "uvular", "pharyngeal",
]

SYLLABLE_COUNTS = ["one-syllable", "two-syllable", "three-syllable", "four-syllable", "five-syllable"]

ERA_TAGS = [
    "ancient", "medieval", "renaissance", "industrial", "victorian",
    "edwardian", "georgian", "elizabethan", "jacobeans", "restoration",
    "baroque", "romantic-era", "modern-era", "postmodern", "contemporary",
    "digital-age", "space-age", "atomic-era", "cold-war", "post-war",
    "great-depression", "golden-age", "dark-age", "iron-age", "bronze-age",
    "stone-age", "paleolithic", "neolithic", "chalcolithic", "classical",
    "hellenistic", "byzantine", "ottoman", "mongol", "tibetan",
]

THEMES = [
    "celestial", "cosmic", "astronomical", "astrological", "zodiac",
    "constellation", "planet", "galaxy", "nebula", "comet",
    "meteor", "asteroid", "eclipse", "solstice", "equinox",
    "lunar", "solar", "tidal", "gravitational", "quantum",
    "elemental", "alchemical", "herbal", "botanical", "zoological",
    "ornithological", "ichthyological", "entomological", "mycological",
    "geological", "mineralogical", "crystallographic", "petrographic",
    "archaeological", "anthropological", "sociological", "psychological",
    "philosophical", "theological", "mythological", "folkloric",
    "legendary", "epic", "ballad", "sonnet", "haiku",
    "prose", "poetry", "literary", "academic", "scholarly",
    "intellectual", "creative", "artistic", "aesthetic", "visual",
    "auditory", "kinesthetic", "tactile", "olfactory", "gustatory",
    "emotional", "spiritual", "transcendental", "mystical", "esoteric",
    "occult", "divine", "sacred", "holy", "blessed", "anointed",
    "consecrated", "sanctified", "purified", "cleansed", "redeemed",
    "salvation", "liberation", "emancipation", "independence", "sovereignty",
]


# =========================================================================
# TEMPLATE DEFINITIONS
# =========================================================================

TEMPLATES = [
    # LIST templates — high volume, high CPC
    "100 {popularity} {origin} baby names",
    "100 {meaning} baby names for {gender}",
    "100 {style} {origin} baby names",
    "100 {nature} themed baby names for {gender}",
    "100 {animal} inspired baby names",
    "100 {flower} named baby names",
    "100 {color} baby names for {gender}",
    "100 {mythology} baby names and meanings",
    "100 {era} baby names for {gender}",
    "100 {theme} baby names",
    "100 {ending} ending baby names for {gender}",
    "100 {letter} starting baby names for {gender}",
    "100 {syllable} baby names for {gender}",
    "100 {season} baby names for {gender}",
    "100 {phonetic} baby names for {gender}",

    # MEANING templates
    "baby names that mean {meaning}",
    "baby names with {meaning} meaning",
    "names meaning {meaning} for {gender}",
    "100 baby names that mean {meaning} and {meaning2}",

    # STYLE templates
    "{style} baby names for {gender}",
    "{style} {origin} baby names",
    "{style} {era} baby names",
    "{style} baby names with {meaning} meaning",

    # TREND templates
    "trending {origin} baby names in {year}",
    "most popular {style} baby names {year}",
    "rising {gender} names {year}",
    "{popularity} {origin} baby names {year}",
    "new {style} baby names trending {year}",

    # COMPARISON templates
    "{origin} vs {origin2} baby names",
    "{style} vs traditional baby names",
    "{meaning} names vs {meaning2} names",
    "{gender} names starting with {letter} vs {letter2}",

    # GUIDE templates
    "complete guide to {origin} baby names",
    "how to choose {style} baby names for {gender}",
    "{origin} baby names: meanings, origins, and popularity",
    "ultimate {theme} baby names guide for {gender}",

    # THEME templates
    "{theme} baby names for {gender}",
    "{theme} inspired baby names",
    "names from {theme} mythology for {gender}",
    "{theme} themed baby names list",

    # GEographic templates
    "{geo} baby names for {gender}",
    "{geo} inspired baby names",
    "names from {geo} cultures for {gender}",
    "{geo} region baby names list",

    # PHONETIC templates
    "{phonetic} baby names for {gender}",
    "{phonetic} sounding baby names",
    "names with {phonetic} qualities for {gender}",

    # SPECIALTY templates
    "{gender} baby names that start with {letter}",
    "{gender} baby names that end with {ending}",
    "{gender} baby names with {syllable} syllables",
    "rare {origin} baby names for {gender}",
    "unique {style} baby names for {gender}",
    "unusual {theme} baby names",
    "obscure {origin} baby names",
    "forgotten {era} baby names",
    "lost {mythology} baby names",
]

# Second meaning for compound templates
_MEANINGS_PAIRS = list(zip(MEANINGS, MEANINGS[1:] + MEANINGS[:1]))

# =========================================================================
# KEYWORD GENERATION
# =========================================================================

def _normalize(keyword: str) -> str:
    """Normalize keyword for dedup comparison."""
    return re.sub(r'[^\w\s]', '', keyword.lower()).strip()


def _fill_template(template: str) -> str:
    """Fill a template with random dimension values."""
    replacements = {
        "{meaning}": random.choice(MEANINGS),
        "{meaning2}": random.choice(MEANINGS),
        "{origin}": random.choice(ORIGINS),
        "{origin2}": random.choice(ORIGINS),
        "{gender}": random.choice(GENDERS),
        "{popularity}": random.choice(POPULARITIES),
        "{style}": random.choice(STYLES),
        "{nature}": random.choice(NATURE_ELEMENTS),
        "{animal}": random.choice(ANIMALS),
        "{flower}": random.choice(FLOWERS),
        "{color}": random.choice(COLORS),
        "{season}": random.choice(SEASONS),
        "{letter}": random.choice(LETTERS),
        "{letter2}": random.choice(LETTERS),
        "{ending}": random.choice(ENDINGS),
        "{year}": random.choice(YEARS),
        "{mythology}": random.choice(MYTHOLOGIES),
        "{era}": random.choice(ERA_TAGS),
        "{theme}": random.choice(THEMES),
        "{geo}": random.choice(GEOS),
        "{phonetic}": random.choice(PHONETICS),
        "{syllable}": random.choice(SYLLABLE_COUNTS),
    }

    keyword = template
    for placeholder, value in replacements.items():
        keyword = keyword.replace(placeholder, value)

    # Clean up double spaces and common artifacts
    keyword = re.sub(r"\s+", " ", keyword).strip()
    return keyword


def _score_keyword(keyword: str) -> tuple:
    """Score a keyword for CPC, intent, cluster, priority, difficulty, volume."""
    kw = keyword.lower()

    # CPC lookup
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
        "sibling": 1.25, "ending": 1.10, "celestial": 1.70,
        "cosmic": 1.65, "zodiac": 1.55, "norse": 1.40,
        "egyptian": 1.35, "celtic": 1.30, "slavic": 1.20,
        "persian": 1.15, "sanskrit": 1.10, "tibetan": 1.05,
        "haiku": 1.45, "sonnet": 1.40, "ballad": 1.35,
        "alchemical": 1.50, "herbal": 1.45, "botanical": 1.40,
        "zoological": 1.35, "ornithological": 1.30,
        "geological": 1.25, "mineralogical": 1.20,
        "archaeological": 1.15, "anthropological": 1.10,
        "philosophical": 1.05, "theological": 1.00,
        "esoteric": 1.55, "occult": 1.50,
        "transcendental": 1.45, "mystical": 1.40,
        "divine": 1.35, "sacred": 1.30, "holy": 1.25,
        "angelic": 1.20, "blessed": 1.15, "anointed": 1.10,
        "consecrated": 1.05, "sanctified": 1.00,
        "purified": 0.95, "cleansed": 0.90, "redeemed": 0.85,
        "salvation": 0.80, "liberation": 0.75, "emancipation": 0.70,
        "independence": 0.65, "sovereignty": 0.60,
        "zodiac": 1.55, "constellation": 1.50, "planet": 1.45,
        "galaxy": 1.40, "nebula": 1.35, "comet": 1.30,
        "meteor": 1.25, "asteroid": 1.20, "eclipse": 1.15,
        "solstice": 1.10, "equinox": 1.05, "lunar": 1.00,
        "solar": 0.95, "tidal": 0.90, "gravitational": 0.85,
        "quantum": 0.80, "elemental": 0.75,
    }

    cpc = 0.50
    for term, value in cpc_map.items():
        if term in kw:
            cpc = max(cpc, value)

    # Intent classification
    if "meaning" in kw:
        intent = "MEANING_INTENT"
    elif any(o in kw for o in ORIGINS):
        intent = "ORIGIN_INTENT"
    elif any(s in kw for s in STYLES):
        intent = "STYLE_INTENT"
    elif any(t in kw for t in THEMES):
        intent = "THEME_INTENT"
    elif any(g in kw for g in GEOS):
        intent = "GEO_INTENT"
    elif any(p in kw for p in PHONETICS):
        intent = "PHONETIC_INTENT"
    elif "vs " in kw or "compare" in kw or "comparison" in kw:
        intent = "COMPARISON_INTENT"
    elif "guide" in kw or "how to" in kw or "ultimate" in kw:
        intent = "GUIDE_INTENT"
    elif "trending" in kw or "popular" in kw or "rising" in kw:
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
        for s in STYLES:
            if s in kw:
                cluster = f"style_{s}"
                break
    if cluster == "uncategorized":
        for n in NATURE_ELEMENTS:
            if n in kw:
                cluster = f"nature_{n}"
                break
    if cluster == "uncategorized":
        for a in ANIMALS:
            if a in kw:
                cluster = f"animal_{a}"
                break
    if cluster == "uncategorized":
        for fl in FLOWERS:
            if fl in kw:
                cluster = f"flower_{fl}"
                break
    if cluster == "uncategorized":
        for c in COLORS:
            if c in kw:
                cluster = f"color_{c}"
                break
    if cluster == "uncategorized":
        for m in MEANINGS:
            if m in kw:
                cluster = f"meaning_{m}"
                break

    # Priority
    priority = 50.0
    if cpc >= 2.0:
        priority = 85.0
    elif cpc >= 1.5:
        priority = 70.0
    elif cpc >= 1.0:
        priority = 55.0
    if "unique" in kw or "rare" in kw or "obscure" in kw:
        priority += 10
    if "meaning" in kw:
        priority += 5
    if "guide" in kw or "ultimate" in kw:
        priority += 5

    # Difficulty
    difficulty = 60.0
    if "baby names" in kw:
        difficulty = 75.0
    if "unique" in kw or "rare" in kw or "obscure" in kw or "obscure" in kw:
        difficulty = 30.0
    for o in ORIGINS:
        if o.lower() in kw:
            difficulty = min(difficulty, 35.0)
            break

    # Volume estimate
    volume = 1000
    if cpc >= 2.0:
        volume = 15000
    elif cpc >= 1.5:
        volume = 8000
    elif cpc >= 1.0:
        volume = 4000
    if "unique" in kw or "rare" in kw:
        volume = max(volume, 3000)

    return intent, cluster, round(priority, 1), round(difficulty, 1), volume, round(cpc, 2)


def discover_keywords(queue, count: int = 5000, max_attempts: int = 50000) -> list[tuple]:
    """Discover unique keywords and return as bulk-insert tuples.

    Args:
        queue: TopicQueue instance for dedup checking
        count: Target number of unique keywords
        max_attempts: Safety limit on generation attempts

    Returns:
        List of tuples: (keyword, intent, cluster, priority, difficulty, volume, cpc)
    """
    from database.topic_queue import TopicQueue

    # Load existing keywords from DB for dedup
    seen = set()
    try:
        existing = queue.conn.execute(
            "SELECT LOWER(keyword) FROM keywords"
        ).fetchall()
        seen = {r[0] for r in existing}
        log.info("Loaded %d existing keywords from DB for dedup", len(seen))
    except Exception:
        pass

    candidates = []
    attempts = 0

    random.seed()

    while len(candidates) < count and attempts < max_attempts:
        attempts += 1

        template = random.choice(TEMPLATES)
        keyword = _fill_template(template)
        normalized = _normalize(keyword)

        if normalized in seen:
            continue

        seen.add(normalized)

        intent, cluster, priority, difficulty, volume, cpc = _score_keyword(keyword)

        candidates.append((
            keyword, intent, cluster, priority, difficulty, volume, cpc,
        ))

    log.info("Keyword discovery: %d unique keywords in %d attempts",
             len(candidates), attempts)
    return candidates
