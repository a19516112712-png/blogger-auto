#!/usr/bin/env python3
"""
Blogger Content Generator — Production Grade

Uses Agnes AI (OpenAI-compatible) to generate SEO-optimized
baby-name articles. Articles are saved as markdown into posts/.

Features:
  - Quota protection (429 → graceful stop, no crash)
  - Retry with exponential backoff
  - Dynamic ARTICLES_PER_RUN via environment variable
  - Strong production validation (title length, body length, label count)
  - Expanded 200+ topic pool with rich label mapping
  - Duplicate prevention via generated_topics.json + existing posts
"""

import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from openai import OpenAI

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
POSTS_DIR = Path(__file__).resolve().parent / "posts"
HISTORY_FILE = Path(__file__).resolve().parent / "generated_topics.json"
# Primary and fallback models (Agnes AI supported models)
DEFAULT_MODEL = "agnes-2.0-flash"
FALLBACK_MODEL = "agnes-1.5-flash"
MODEL = os.environ.get("AGNES_MODEL", DEFAULT_MODEL)

# Dynamic article count: read from env or default to 5
DEFAULT_ARTICLES_PER_RUN = 5
ARTICLES_PER_RUN = int(os.environ.get("ARTICLES_PER_RUN", DEFAULT_ARTICLES_PER_RUN))

AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"

# Retry configuration
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]  # seconds
RETRYABLE_CODES = (429, 500, 503)

# Validation thresholds
# Banned phrases — titles/descriptions must never contain these
BANNED_PHRASES = [
    "the rise of", "timeless choices", "artistic flair", "perfect balance",
    "modern parents", "creative naming ideas", "for your little one",
    "beautiful choices", "inspired living", "elegant selections",
    "meaningful journey", "hidden gems", "naming inspiration",
    "magical names", "dreamy names", "enchanting names", "whimsical names",
    "naming ideas", "the rise of",
]

MIN_TITLE_LENGTH = 10       # characters (titles now start with '100 ...')
MIN_BODY_WORDS = 1500       # words (reject below 1500, target 2500-4000)
MIN_LABELS = 4
MAX_LABELS = 6

# Quota tracking (module-level — survives across retries but not runs)
_quota_exhausted = False


# ---------------------------------------------------------------------------
# Expanded Topic Pool (200+ unique baby-name topics)
# ---------------------------------------------------------------------------
TOPICS = [
    # --- Light, Hope, Love, Peace, Joy, Strength ---
    "baby names that mean light",
    "baby names that mean love",
    "baby names that mean hope",
    "baby names that mean peace",
    "baby names that mean joy",
    "baby names that mean strength",
    "baby names that mean grace",
    "baby names that mean wisdom",
    "baby names that mean miracle",
    "baby names that mean blessing",
    "baby names that mean dream",
    "baby names that mean star",
    "baby names that mean brave",
    # --- Biblical & Religious ---
    "biblical baby names and meanings",
    "christian baby names from the bible",
    "hebrew baby names and meanings",
    "biblical boy names with meaning",
    "biblical girl names and meanings",
    # --- Vintage & Classic ---
    "vintage baby names",
    "vintage baby boy names",
    "vintage baby girl names",
    "old fashioned baby names making a comeback",
    "classic baby names that never go out of style",
    "retro baby names from the 1950s",
    # --- Nature, Flowers, Ocean, Forest ---
    "nature baby names inspired by flowers",
    "flower baby names for girls",
    "nature baby names for boys",
    "ocean baby names inspired by the sea",
    "beach baby names for summer babies",
    "forest baby names for nature lovers",
    "earthy baby names and meanings",
    "tree baby names and meanings",
    # --- Japanese, Irish, French, Italian, Greek, Korean ---
    "japanese baby names and meanings",
    "irish baby names for boys and girls",
    "french baby names that sound beautiful",
    "italian baby names and meanings",
    "greek baby names from mythology",
    "korean baby names and meanings",
    "chinese baby names and meanings",
    "indian baby names and meanings",
    "african baby names and meanings",
    "arabic baby names and meanings",
    "spanish baby names and meanings",
    # --- Gender Neutral, Unique, Modern, Popular ---
    "gender neutral baby names",
    "gender neutral baby names for modern families",
    "unisex baby names for boys and girls",
    "unique baby names you haven't heard",
    "unique baby girl names",
    "unique baby boy names",
    "modern baby names that are trending",
    "popular baby names right now",
    # --- Strong Boy, Beautiful Girl ---
    "baby boy names that mean strong",
    "baby boy names with powerful meanings",
    "strong baby names for boys",
    "beautiful baby girl names and meanings",
    "elegant baby girl names",
    "cute baby girl names",
    # --- Royal, Warrior, Mythological ---
    "royal baby names for boys and girls",
    "warrior baby names and meanings",
    "mythology baby names and meanings",
    "greek god and goddess baby names",
    "celtic baby names and meanings",
    "norse baby names for boys",
    # --- Celestial, Space, Star ---
    "celestial baby names inspired by stars",
    "space baby names and meanings",
    "moon baby names and meanings",
    "star names for babies",
    # --- Short, One-Syllable, Middle ---
    "one syllable baby names",
    "short baby names with big meanings",
    "middle names for girls",
    "middle names for boys",
    # --- Country, Western, Boho ---
    "country baby names for boys and girls",
    "southern baby names with charm",
    "bohemian baby names with meanings",
    # --- Color, Gemstone, Bird, Animal ---
    "color baby names and meanings",
    "gemstone baby names for girls",
    "bird baby names and meanings",
    "animal baby names for babies",
    # --- Twin, Pet, Dog, Cat ---
    "twin baby names that go together",
    "pet inspired baby names",
    "dog names and meanings",
    "cat names and meanings",
    # --- Fantasy, Elf, Dragon, Kingdom ---
    "fantasy baby names and meanings",
    "elf names and meanings",
    "dragon names and meanings",
    "kingdom names and meanings",
    # --- Scientist, Explorer, Viking ---
    "scientist baby names and meanings",
    "explorer baby names inspired by adventure",
    "viking baby names and meanings",
]

# ---------------------------------------------------------------------------
# Rich Label Map (always 4 labels per keyword match)
# ---------------------------------------------------------------------------
TOPIC_LABEL_MAP = {
    # Biblical & Religious
    "biblical":   ["Biblical Names", "Christian Names", "Hebrew Names", "Religious Names"],
    "hebrew":     ["Hebrew Names", "Biblical Names", "Jewish Names", "Traditional Names"],
    "christian":  ["Christian Names", "Religious Names", "Biblical Names", "Faith Names"],
    "saint":      ["Saint Names", "Religious Names", "Christian Names", "Holy Names"],
    "virtue":     ["Virtue Names", "Meaningful Names", "Inspirational Names", "Faith Names"],
    "spiritual":  ["Spiritual Names", "Meaningful Names", "Soulful Names", "Faith Names"],
    "testament":  ["Biblical Names", "Religious Names", "Christian Names", "Traditional Names"],
    # Vintage & Classic
    "vintage":    ["Vintage Names", "Classic Names", "Old-Fashioned Names", "Timeless Names"],
    "classic":    ["Classic Names", "Timeless Names", "Traditional Names", "Elegant Names"],
    "old-fashion":["Vintage Names", "Old-Fashioned Names", "Retro Names", "Classic Names"],
    "retro":      ["Retro Names", "Vintage Names", "Nostalgic Names", "Classic Names"],
    "victorian":  ["Victorian Names", "Vintage Names", "Elegant Names", "Classic Names"],
    "edwardian":  ["Edwardian Names", "Vintage Names", "Aristocratic Names", "Classic Names"],
    "antique":    ["Vintage Names", "Antique Names", "Rare Names", "Classic Names"],
    "1950":       ["Retro Names", "Vintage Names", "Classic Names", "Nostalgic Names"],
    # Nature
    "nature":     ["Nature Names", "Outdoor Names", "Organic Names", "Earthy Names"],
    "earthy":     ["Nature Names", "Botanical Names", "Floral Names", "Earthy Names"],
    "botanical":  ["Nature Names", "Botanical Names", "Floral Names", "Plant Names"],
    "floral":     ["Floral Names", "Flower Names", "Nature Names", "Botanical Names"],
    "flower":     ["Flower Names", "Floral Names", "Nature Names", "Botanical Names"],
    "tree":       ["Tree Names", "Forest Names", "Nature Names", "Woodland Names"],
    "forest":     ["Forest Names", "Woodland Names", "Nature Names", "Tree Names"],
    "mountain":   ["Mountain Names", "Nature Names", "Outdoor Names", "Strong Names"],
    "meadow":     ["Nature Names", "Meadow Names", "Earthy Names", "Peaceful Names"],
    "desert":     ["Desert Names", "Unique Names", "Nature Names", "Earthy Names"],
    "river":      ["River Names", "Water Names", "Nature Names", "Flowing Names"],
    "stream":     ["Water Names", "Nature Names", "Stream Names", "Flowing Names"],
    "garden":     ["Garden Names", "Floral Names", "Nature Names", "Botanical Names"],
    "season":     ["Seasonal Names", "Nature Names", "Calendar Names", "Unique Names"],
    "spring":     ["Spring Names", "Seasonal Names", "Nature Names", "Fresh Names"],
    "summer":     ["Summer Names", "Seasonal Names", "Warm Names", "Radiant Names"],
    "autumn":     ["Autumn Names", "Seasonal Names", "Golden Names", "Nature Names"],
    "winter":     ["Winter Names", "Seasonal Names", "Crisp Names", "Snow Names"],
    # Ocean & Water
    "ocean":      ["Ocean Names", "Water Names", "Beach Names", "Coastal Names"],
    "water":      ["Water Names", "Nature Names", "Ocean Names", "Coastal Names"],
    "beach":      ["Beach Names", "Ocean Names", "Coastal Names", "Summer Names"],
    "coastal":    ["Coastal Names", "Ocean Names", "Beach Names", "Nature Names"],
    "sea":        ["Ocean Names", "Sea Names", "Water Names", "Beach Names"],
    "sailor":     ["Sailor Names", "Nautical Names", "Ocean Names", "Adventure Names"],
    "nautical":   ["Nautical Names", "Ocean Names", "Sailor Names", "Adventure Names"],
    "island":     ["Island Names", "Tropical Names", "Ocean Names", "Unique Names"],
    "lake":       ["Lake Names", "Water Names", "Nature Names", "Peaceful Names"],
    # Celestial & Space
    "celestial":  ["Celestial Names", "Space Names", "Star Names", "Cosmic Names"],
    "space":      ["Space Names", "Celestial Names", "Cosmic Names", "Star Names"],
    "star":       ["Star Names", "Celestial Names", "Cosmic Names", "Shining Names"],
    "constellation":["Star Names", "Celestial Names", "Cosmic Names", "Astronomy Names"],
    "moon":       ["Moon Names", "Celestial Names", "Lunar Names", "Mystical Names"],
    "galaxy":     ["Cosmic Names", "Galaxy Names", "Space Names", "Star Names"],
    "astronomy":  ["Astronomy Names", "Space Names", "Star Names", "Science Names"],
    "sun":        ["Sun Names", "Celestial Names", "Radiant Names", "Bright Names"],
    "zodiac":     ["Zodiac Names", "Astrology Names", "Star Names", "Celestial Names"],
    "planet":     ["Space Names", "Planet Names", "Astronomy Names", "Celestial Names"],
    # Mythology
    "mythology":  ["Mythology Names", "Legendary Names", "Ancient Names", "Heroic Names"],
    "greek":      ["Greek Names", "Mythology Names", "Ancient Names", "Classical Names"],
    "roman":      ["Roman Names", "Mythology Names", "Ancient Names", "Classical Names"],
    "norse":      ["Norse Names", "Viking Names", "Mythology Names", "Warrior Names"],
    "egyptian":   ["Egyptian Names", "Ancient Names", "Mythology Names", "Royal Names"],
    "celtic":     ["Celtic Names", "Irish Names", "Mythology Names", "Nature Names"],
    "hindu":      ["Hindu Names", "Indian Names", "Spiritual Names", "Traditional Names"],
    "japanese":   ["Japanese Names", "Asian Names", "Elegant Names", "Modern Names"],
    # Literary
    "literary":   ["Literary Names", "Book Names", "Classic Novels", "Author Names"],
    "shakespeare":["Shakespearean Names", "Literary Names", "Dramatic Names", "Classic Names"],
    "poet":       ["Poetic Names", "Literary Names", "Artistic Names", "Creative Names"],
    "fairy tale": ["Fairy Tale Names", "Magical Names", "Literary Names", "Fantasy Names"],
    "austen":     ["Literary Names", "Regency Names", "Classic Names", "Elegant Names"],
    "fantasy":    ["Fantasy Names", "Magical Names", "Literary Names", "Imaginative Names"],
    "children book":["Literary Names", "Nostalgic Names", "Classic Names", "Whimsical Names"],
    "novel":      ["Literary Names", "Book Names", "Author Names", "Classic Names"],
    # Royal
    "royal":      ["Royal Names", "Aristocratic Names", "Regal Names", "Noble Names"],
    "british":    ["British Names", "Royal Names", "Traditional Names", "Classic Names"],
    "monarchy":   ["Royal Names", "Monarchy Names", "Noble Names", "Aristocratic Names"],
    "king":       ["Royal Names", "King Names", "Regal Names", "Strong Names"],
    "queen":      ["Royal Names", "Queen Names", "Regal Names", "Elegant Names"],
    "noble":      ["Noble Names", "Aristocratic Names", "Royal Names", "Refined Names"],
    "regal":      ["Regal Names", "Royal Names", "Elegant Names", "Noble Names"],
    "crown":      ["Royal Names", "Noble Names", "Regal Names", "Aristocratic Names"],
    "prince":     ["Royal Names", "Prince Names", "Regal Names", "Noble Names"],
    "princess":   ["Royal Names", "Princess Names", "Elegant Names", "Fairy Tale Names"],
    # Musical & Arts
    "musical":    ["Musical Names", "Creative Names", "Arts Names", "Melodic Names"],
    "opera":      ["Opera Names", "Musical Names", "Dramatic Names", "Classical Names"],
    "jazz":       ["Jazz Names", "Musical Names", "Cool Names", "Creative Names"],
    "rock":       ["Rock Names", "Musical Names", "Rebellious Names", "Cool Names"],
    "composer":   ["Musical Names", "Classical Names", "Artistic Names", "Creative Names"],
    "art":        ["Artistic Names", "Creative Names", "Arts Names", "Bohemian Names"],
    "paint":      ["Artistic Names", "Creative Names", "Arts Names", "Bohemian Names"],
    "dance":      ["Dance Names", "Graceful Names", "Artistic Names", "Rhythmic Names"],
    # International
    "international":["International Names", "Global Names", "Multicultural Names", "World Names"],
    "french":     ["French Names", "European Names", "Chic Names", "Romantic Names"],
    "italian":    ["Italian Names", "European Names", "Romantic Names", "Melodic Names"],
    "irish":      ["Irish Names", "Celtic Names", "Charming Names", "Traditional Names"],
    "scottish":   ["Scottish Names", "Celtic Names", "Strong Names", "Traditional Names"],
    "german":     ["German Names", "European Names", "Strong Names", "Traditional Names"],
    "spanish":    ["Spanish Names", "Latin Names", "Passionate Names", "Vibrant Names"],
    "russian":    ["Russian Names", "Slavic Names", "Bold Names", "Traditional Names"],
    "scandinavian":["Scandinavian Names", "Nordic Names", "Modern Names", "Cool Names"],
    "korean":     ["Korean Names", "Asian Names", "Modern Names", "Elegant Names"],
    "chinese":    ["Chinese Names", "Asian Names", "Meaningful Names", "Traditional Names"],
    "indian":     ["Indian Names", "Hindu Names", "Spiritual Names", "Diverse Names"],
    "arabic":     ["Arabic Names", "Middle Eastern Names", "Poetic Names", "Powerful Names"],
    "persian":    ["Persian Names", "Middle Eastern Names", "Ancient Names", "Regal Names"],
    "african":    ["African Names", "Diverse Names", "Unique Names", "Cultural Names"],
    "hawaiian":   ["Hawaiian Names", "Island Names", "Nature Names", "Tropical Names"],
    "native":     ["Native American Names", "Nature Names", "Earthy Names", "Unique Names"],
    "aboriginal": ["Aboriginal Names", "Australian Names", "Ancient Names", "Unique Names"],
    "brazilian":  ["Brazilian Names", "Latin Names", "Rhythmic Names", "Vibrant Names"],
    "swedish":    ["Swedish Names", "Scandinavian Names", "Modern Names", "Clean Names"],
    "dutch":      ["Dutch Names", "European Names", "Distinctive Names", "Charming Names"],
    "polish":     ["Polish Names", "Slavic Names", "Strong Names", "Traditional Names"],
    "european":   ["European Names", "International Names", "Classic Names", "Diverse Names"],
    "asian":      ["Asian Names", "International Names", "Diverse Names", "Cultural Names"],
    "latin":      ["Latin Names", "International Names", "Vibrant Names", "Romantic Names"],
    "slavic":     ["Slavic Names", "European Names", "Strong Names", "Traditional Names"],
    # Strong & Powerful
    "strong":     ["Strong Names", "Powerful Names", "Bold Names", "Masculine Names"],
    "boy":        ["Boy Names", "Masculine Names", "Strong Names", "Traditional Names"],
    "powerful":   ["Meaningful Names", "Powerful Names", "Virtue Names", "Inspirational Names"],
    "warrior":    ["Warrior Names", "Strong Names", "Fearless Names", "Heroic Names"],
    "hero":       ["Heroic Names", "Strong Names", "Legendary Names", "Inspirational Names"],
    "courage":    ["Meaningful Names", "Courage Names", "Strong Names", "Virtue Names"],
    "bravery":    ["Meaningful Names", "Bravery Names", "Strong Names", "Virtue Names"],
    "fearless":   ["Fearless Names", "Bold Names", "Adventure Names", "Strong Names"],
    # Elegant & Beautiful
    "beautiful":  ["Girl Names", "Beautiful Names", "Elegant Names", "Charming Names"],
    "girl":       ["Girl Names", "Feminine Names", "Elegant Names", "Beautiful Names"],
    "elegant":    ["Elegant Names", "Sophisticated Names", "Refined Names", "Classic Names"],
    "feminine":   ["Girl Names", "Feminine Names", "Delicate Names", "Charming Names"],
    "charming":   ["Charming Names", "Sweet Names", "Girl Names", "Adorable Names"],
    "melodic":    ["Melodic Names", "Musical Names", "Beautiful Names", "Romantic Names"],
    "romantic":   ["Romantic Names", "Love Names", "Beautiful Names", "Melodic Names"],
    "enchanting": ["Enchanting Names", "Magical Names", "Beautiful Names", "Mystical Names"],
    "dreamy":     ["Dreamy Names", "Romantic Names", "Beautiful Names", "Fantasy Names"],
    # Gender-Neutral
    "gender-neutral":["Gender Neutral Names", "Unisex Names", "Modern Names", "Trending Names"],
    "unisex":     ["Unisex Names", "Gender Neutral Names", "Modern Names", "Flexible Names"],
    "modern":     ["Modern Names", "Trending Names", "Contemporary Names", "Fresh Names"],
    "trending":   ["Trending Names", "Popular Names", "Modern Names", "Hot Names"],
    "androgynous":["Gender Neutral Names", "Androgynous Names", "Inclusive Names", "Modern Names"],
    # Unique & Rare
    "unique":     ["Unique Names", "Rare Names", "Uncommon Names", "Distinctive Names"],
    "rare":       ["Rare Names", "Unique Names", "Uncommon Names", "Hidden Gem Names"],
    "uncommon":   ["Uncommon Names", "Unique Names", "Rare Names", "Distinctive Names"],
    "distinctive":["Distinctive Names", "Unique Names", "Standout Names", "Memorable Names"],
    "one-of-a-kind":["Unique Names", "Rare Names", "Standout Names", "Extraordinary Names"],
    "hidden gem": ["Hidden Gem Names", "Rare Names", "Unique Names", "Under-the-Radar Names"],
    # Short Names
    "short":      ["Short Names", "One-Syllable Names", "Minimalist Names", "Simple Names"],
    "one-syllable":["Short Names", "One-Syllable Names", "Minimalist Names", "Simple Names"],
    "two-syllable":["Two-Syllable Names", "Balanced Names", "Classic Names", "Melodic Names"],
    "three-letter":["Short Names", "Three-Letter Names", "Minimalist Names", "Tiny Names"],
    "minimalist": ["Minimalist Names", "Simple Names", "Short Names", "Clean Names"],
    "sweet":      ["Short Names", "Charming Names", "Sweet Names", "Simple Names"],
    # Colors & Gems
    "color":      ["Color Names", "Vibrant Names", "Creative Names", "Nature Names"],
    "gemstone":   ["Gemstone Names", "Precious Names", "Rare Names", "Beautiful Names"],
    "bird":       ["Bird Names", "Nature Names", "Free-Spirited Names", "Unique Names"],
    "animal":     ["Animal Names", "Wild Names", "Nature Names", "Unique Names"],
    "weather":    ["Weather Names", "Nature Names", "Celestial Names", "Unique Names"],
    "rainbow":    ["Rainbow Names", "Color Names", "Hopeful Names", "Beautiful Names"],
    # Trendy
    "popular":    ["Trending Names", "Popular Names", "Modern Names", "Hot Names"],
    "celebrity":  ["Celebrity Names", "Trending Names", "Pop Culture Names", "Modern Names"],
    "social media":["Modern Names", "Trending Names", "Digital-Age Names", "Unique Names"],
    "tech":       ["Tech Names", "Modern Names", "Innovative Names", "Future Names"],
    "hottest":    ["Trending Names", "Popular Names", "Hot Names", "Modern Names"],
    # STEM
    "scientists": ["STEM Names", "Inventor Names", "Scientist Names", "Intellectual Names"],
    "inventors":  ["STEM Names", "Inventor Names", "Scientist Names", "Innovative Names"],
    "philosopher":["Intellectual Names", "Philosophical Names", "Deep Names", "Thoughtful Names"],
    "mathematician":["STEM Names", "Mathematical Names", "Intellectual Names", "Precise Names"],
    "explorer":   ["Explorer Names", "Adventure Names", "Bold Names", "World Names"],
    "astronaut":  ["Space Names", "STEM Names", "Adventure Names", "Heroic Names"],
    "engineer":   ["STEM Names", "Engineer Names", "Innovative Names", "Strong Names"],
    # BoHo
    "bohemian":   ["Bohemian Names", "Artistic Names", "Free-Spirited Names", "Creative Names"],
    "free-spirit":["Free-Spirited Names", "Bohemian Names", "Wanderlust Names", "Creative Names"],
    "hippie":     ["Hippie Names", "Bohemian Names", "Peace Names", "Nature Names"],
    "creative":   ["Creative Names", "Artistic Names", "Arts Names", "Bohemian Names"],
    "eclectic":   ["Eclectic Names", "Unique Names", "Bohemian Names", "Creative Names"],
    # Holidays
    "holiday":    ["Holiday Names", "Festive Names", "Joyful Names", "Seasonal Names"],
    "christmas":  ["Christmas Names", "Holiday Names", "Festive Names", "Winter Names"],
    # Love & Emotion
    "love":       ["Love Names", "Romantic Names", "Meaningful Names", "Heartfelt Names"],
    "joy":        ["Joyful Names", "Happy Names", "Positive Names", "Bright Names"],
    "peace":      ["Peaceful Names", "Calm Names", "Serene Names", "Meaningful Names"],
    "hope":       ["Hopeful Names", "Meaningful Names", "Virtue Names", "Inspirational Names"],
    "faith":      ["Faith Names", "Meaningful Names", "Virtue Names", "Spiritual Names"],
    # Food
    "food":       ["Food Names", "Culinary Names", "Sweet Names", "Creative Names"],
    "spice":      ["Spice Names", "Exotic Names", "Warm Names", "Unique Names"],
    "herb":       ["Herb Names", "Nature Names", "Botanical Names", "Garden Names"],
    "fruit":      ["Fruit Names", "Fresh Names", "Sweet Names", "Nature Names"],
    "wine":       ["Wine Names", "Sophisticated Names", "European Names", "Luxury Names"],
    # Country & Western
    "country":    ["Country Names", "Southern Names", "Charming Names", "Rustic Names"],
    "western":    ["Western Names", "Cowboy Names", "Rugged Names", "American Names"],
    "ranch":      ["Ranch Names", "Western Names", "Rustic Names", "American Names"],
    "farmhouse":  ["Farmhouse Names", "Rustic Names", "Wholesome Names", "Country Names"],
    "southern":   ["Southern Names", "Country Names", "Charming Names", "American Names"],
    # Pop Culture
    "disney":     ["Disney Names", "Magical Names", "Pop Culture Names", "Beloved Names"],
    "movie":      ["Movie Names", "Pop Culture Names", "Iconic Names", "Modern Names"],
    "tv show":    ["TV Names", "Pop Culture Names", "Trending Names", "Modern Names"],
    "video game": ["Video Game Names", "Gamer Names", "Pop Culture Names", "Modern Names"],
    "comic":      ["Superhero Names", "Comic Book Names", "Pop Culture Names", "Strong Names"],
    "anime":      ["Anime Names", "Japanese Names", "Pop Culture Names", "Creative Names"],
    # Spiritual
    "meditation": ["Spiritual Names", "Meditation Names", "Peaceful Names", "Soulful Names"],
    "zen":        ["Zen Names", "Minimalist Names", "Peaceful Names", "Spiritual Names"],
    "yoga":       ["Yoga Names", "Spiritual Names", "Peaceful Names", "Meaningful Names"],
    "soul":       ["Soulful Names", "Spiritual Names", "Deep Names", "Meaningful Names"],
    "karmic":     ["Karmic Names", "Spiritual Names", "Meaningful Names", "Destiny Names"],
}

# ---------------------------------------------------------------------------
# Prompt template — NO frontmatter; we build that ourselves.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are a professional Programmatic SEO content writer specializing in baby names.

Your job is to write high-quality, SEO-optimized articles that rank on Google and provide real value to parents searching for baby names.

=== TITLE RULES ===
The first line of your response MUST be an H1 heading (# ) with the EXACT format:
# 100 {Topic Keyword Phrase}
Examples: # 100 Baby Names That Mean Light, # 100 Biblical Baby Names and Meanings, # 100 Irish Baby Names for Boys and Girls
- ALWAYS start the title with a number (100, 150, 200, 250)
- Maximum 65 characters total
- NEVER use these phrases anywhere: The Rise of, Timeless Choices, Artistic Flair, Perfect Balance, Modern Parents, Creative Naming Ideas, For Your Little One, Beautiful Choices, Inspired Living, Elegant Selections, Meaningful Journey, Hidden Gems, Naming Inspiration, Magical Names, Dreamy Names, Enchanting Names, Whimsical Names

=== ARTICLE STRUCTURE ===
1. # Title (H1 — number-prefixed, SEO-optimized)
2. Engaging introduction (2-3 paragraphs, naturally include the primary keyword)
3. ## Table of Contents (ordered list)
4. ## 100 {Topic} Names and Meanings
   - A LARGE TABLE with these columns:
     | # | Name | Meaning | Origin | Pronunciation | Gender |
   - The table MUST contain at least 100 names
   - Every row must have all 6 columns filled
   - Use real, verified name data
5. ## Cultural Background and History
6. ## Naming Tips and Advice
7. ## Frequently Asked Questions
   - 7-10 FAQs with detailed, helpful answers
   - Format each as: ### Q: Question? followed by a detailed answer
8. ## Conclusion
9. ## Related Articles (5-10 internal links in markdown format)

=== CONTENT RULES ===
- Total article length: 2500-4000 words minimum
- The name table is the core of the article — it must be comprehensive
- Every name needs: meaning, origin, pronunciation, gender
- Use real, accurate name data — do not fabricate meanings
- Write unique, original content — do not use generic AI filler text
- Include cultural context and naming traditions
- Bold key terms and baby names for emphasis

=== INTERNAL LINKING ===
At the end of the article, add a "Related Articles" section with 5-10 contextual internal links in this format:
- [100 Irish Baby Names for Boys and Girls](/100-irish-baby-names)
- [100 Japanese Baby Names and Meanings](/100-japanese-baby-names)
Pick links that are thematically related to the current article topic.

Return ONLY the article body in markdown. No YAML frontmatter, no code fences, no commentary."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def slugify(title: str) -> str:
    """Convert a title to a safe filename slug."""
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:80]


def strip_fences(text: str) -> str:
    """Remove outermost ```markdown ... ``` fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.rstrip().endswith("```"):
            text = text.rsplit("\n", 1)[0]
    return text.strip()


# ---------------------------------------------------------------------------
# History database — prevents duplicate generation
# ---------------------------------------------------------------------------
def load_history() -> list[dict]:
    """Load the generation history from generated_topics.json."""
    if not HISTORY_FILE.exists():
        log.info("No history file found. Starting fresh.")
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            log.info("Loaded history: %d previous generation(s).", len(data))
            return data
        log.warning("History file is not a list; ignoring.")
        return []
    except (json.JSONDecodeError, Exception) as exc:
        log.warning("Could not parse history file: %s. Starting fresh.", exc)
        return []


def save_history_entry(topic: str, title: str, slug: str):
    """Append a new entry to generated_topics.json."""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    entry = {"topic": topic, "title": title, "slug": slug, "date": today}
    history.append(entry)
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    log.info("History updated: added '%s' → %d total entries.", topic, len(history))


def scan_existing_posts() -> dict:
    """Scan all markdown files in posts/ and extract titles and slugs."""
    titles, slugs = set(), set()
    if not POSTS_DIR.exists():
        return {"titles": titles, "slugs": slugs}
    for md_file in POSTS_DIR.glob("*.md"):
        name = md_file.stem
        slug_match = re.match(r"^\d{4}-\d{2}-\d{2}-(.+)", name)
        slugs.add((slug_match.group(1) if slug_match else name).lower())
        try:
            text = md_file.read_text(encoding="utf-8")
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    fm = yaml.safe_load(parts[1].strip())
                    if isinstance(fm, dict) and fm.get("title"):
                        titles.add(str(fm["title"]).strip().lower())
        except Exception:
            pass
    return {"titles": titles, "slugs": slugs}


def build_blacklist() -> dict:
    """Combine history file + existing posts into a unified blacklist."""
    history = load_history()
    existing = scan_existing_posts()
    bt, bti, bs = set(), set(), set()
    for e in history:
        if e.get("topic"): bt.add(e["topic"].strip().lower())
        if e.get("title"): bti.add(e["title"].strip().lower())
        if e.get("slug"): bs.add(e["slug"].strip().lower())
    bti |= existing["titles"]
    bs |= existing["slugs"]
    log.info("Blacklist built: %d topics, %d titles, %d slugs.", len(bt), len(bti), len(bs))
    return {"topics": bt, "titles": bti, "slugs": bs}


# ---------------------------------------------------------------------------
# Frontmatter construction (programmatic)
# ---------------------------------------------------------------------------
def extract_title(body: str, topic: str) -> str:
    """Extract the article title from the first H1 heading in the body."""
    match = re.search(r"^#\s+(.+?)$", body, re.MULTILINE)
    if match:
        return match.group(1).strip()
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("---") and not stripped.startswith("```"):
            return stripped[:150]
    return topic


def sanitize_title(raw_title: str) -> str:
    """Strip leading YAML key prefixes from a title string."""
    YAML_KEY_PREFIXES = ("title:", "date:", "labels:", "meta_description:", "---", "# ")
    title = raw_title.strip()
    for prefix in YAML_KEY_PREFIXES:
        if title.lower().startswith(prefix):
            title = title.split(":", 1)[1].strip() if ":" in prefix else title[len(prefix):].strip()
            log.info("Stripped '%s' prefix from title → '%s'", prefix.rstrip(": "), title)
            break
    return title.strip()


def strip_existing_frontmatter(text: str) -> str:
    """Remove any YAML frontmatter block the model may have generated."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return text


def generate_labels(topic: str) -> list[str]:
    """Derive topic-specific labels (4-6 total, always 'Baby Names' first)."""
    topic_lower = topic.lower()
    seen = {"Baby Names"}
    topic_labels = ["Baby Names"]
    for keyword, label_list in TOPIC_LABEL_MAP.items():
        if keyword in topic_lower:
            for lbl in label_list:
                if lbl not in seen:
                    topic_labels.append(lbl)
                    seen.add(lbl)
    return topic_labels[:MAX_LABELS]


def build_frontmatter(title: str, labels: list[str], today: str, topic: str) -> str:
    """Construct a valid YAML frontmatter block using yaml.dump."""
    meta_desc = generate_meta_description(title, topic)
    seo_title = title[:65] if len(title) <= 65 else title[:62] + "..."
    data = {
        "title": title,
        "labels": labels,
        "date": today,
        "slug": slugify(title),
        "meta_description": meta_desc,
        "seo_title": seo_title,
        "og_title": title,
        "og_description": meta_desc,
    }
    yaml_body = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return "---\n" + yaml_body + "---"


def count_words(text: str) -> int:
    """Count words in the body text (after frontmatter is stripped)."""
    return len(text.split())


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_saved_file(filepath: Path) -> bool:
    """Validate that a saved markdown file has correct frontmatter and body."""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception as exc:
        log.error("Cannot read saved file %s: %s", filepath.name, exc)
        return False

    if not text.startswith("---"):
        log.error("Post-save validation FAILED: %s does not start with ---", filepath.name)
        return False

    parts = text.split("---", 2)
    if len(parts) < 3:
        log.error("Post-save validation FAILED: %s has malformed frontmatter delimiters", filepath.name)
        return False

    try:
        fm = yaml.safe_load(parts[1].strip())
    except yaml.YAMLError as exc:
        log.error("Post-save validation FAILED: %s YAML error — %s", filepath.name, exc)
        return False

    if not isinstance(fm, dict):
        log.error("Post-save validation FAILED: %s frontmatter is not a dict", filepath.name)
        return False

    for field in ("title", "date", "labels"):
        if field not in fm:
            log.error("Post-save validation FAILED: %s missing '%s' field", filepath.name, field)
            return False
        if fm[field] is None:
            log.error("Post-save validation FAILED: %s '%s' field is None", filepath.name, field)
            return False

    if not str(fm["title"]).strip():
        log.error("Post-save validation FAILED: %s has empty title", filepath.name)
        return False

    if not isinstance(fm["labels"], list) or len(fm["labels"]) == 0:
        log.error("Post-save validation FAILED: %s has empty/missing labels", filepath.name)
        return False

    body_text = parts[2].strip()
    if not body_text:
        log.error("Post-save validation FAILED: %s has empty body", filepath.name)
        return False

    return True


# ---------------------------------------------------------------------------
# Generation with retry & quota protection
# ---------------------------------------------------------------------------
def is_quota_exhausted() -> bool:
    """Check whether the API rate limit has been exhausted."""
    return _quota_exhausted


def set_quota_exhausted():
    """Mark the API rate limit as exhausted (global flag)."""
    global _quota_exhausted
    _quota_exhausted = True


def pick_topics(num: int, blacklist: dict) -> list[str]:
    """Pick `num` unique topics, skipping blacklisted ones."""
    available, skipped = [], []
    for topic in TOPICS:
        if topic.strip().lower() in blacklist["topics"]:
            skipped.append(topic)
            continue
        available.append(topic)
    for dup in skipped:
        log.info("Duplicate detected: Skipping topic '%s' (already in history).", dup)
    random.shuffle(available)
    chosen = available[:num]
    if len(chosen) < num:
        log.warning("Only %d fresh topic(s) available (wanted %d). %d/%d topics used.",
                    len(chosen), num, len(skipped), len(TOPICS))
    return chosen


def generate_article_with_retry(client: OpenAI, topic: str) -> str | None:
    """Generate an article with retry logic for transient failures.

    Retries on: 429, 500, 503, and network timeouts.
    Stops immediately on permanent quota exhaustion (429).
    Uses OpenAI-compatible chat completions API via Agnes AI.
    """
    global _quota_exhausted

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # Try primary model first, fall back to alternate on model-not-found
            active_model = MODEL
            try:
                response = client.chat.completions.create(
                    model=active_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": f"Write an SEO-optimized blog article about: {topic}"},
                    ],
                    temperature=0.9,
                    top_p=0.95,
                    max_tokens=4096,
                )
            except Exception as model_exc:
                exc_str = str(model_exc).lower()
                if "model_not_found" in exc_str and active_model != FALLBACK_MODEL:
                    log.warning("Model '%s' not found, falling back to '%s'.", active_model, FALLBACK_MODEL)
                    active_model = FALLBACK_MODEL
                    response = client.chat.completions.create(
                        model=active_model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": f"Write an SEO-optimized blog article about: {topic}"},
                        ],
                        temperature=0.9,
                        top_p=0.95,
                        max_tokens=4096,
                    )
                else:
                    raise

            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content
            log.warning("Attempt %d: empty response from Agnes AI for '%s'.", attempt, topic)
        except Exception as exc:
            exc_str = str(exc).lower()
            status_code = getattr(exc, "status_code", None)

            # 429 = quota/rate limit exhausted — mark globally and stop retrying
            if status_code == 429 or "429" in exc_str or "rate_limit" in exc_str or "resource_exhausted" in exc_str:
                log.warning("[WARNING] Agnes AI rate limit exceeded (429).")
                if not _quota_exhausted:
                    set_quota_exhausted()
                return None  # Don't retry — rate limit is gone

            # Retryable error codes
            if status_code in RETRYABLE_CODES or any(str(c) in exc_str for c in RETRYABLE_CODES) or "timeout" in exc_str:
                if attempt < MAX_RETRIES:
                    delay = RETRY_DELAYS[attempt - 1]
                    log.warning("Attempt %d/%d failed (%s). Retrying in %ds…", attempt, MAX_RETRIES, type(exc).__name__, delay)
                    time.sleep(delay)
                    continue
            log.error("Agnes AI API error for '%s' (attempt %d): %s", topic, attempt, exc)
            return None

    log.error("All %d retries exhausted for topic '%s'.", MAX_RETRIES, topic)
    return None


# ---------------------------------------------------------------------------
# Save pipeline with production validation
# ---------------------------------------------------------------------------

def enforce_title_rules(title: str) -> str | None:
    """Post-process a title to ensure it follows SEO rules.

    Returns the cleaned title, or None if it cannot be fixed.
    """
    title = title.strip()
    original = title

    # Strip any "# " prefix
    if title.startswith("# "):
        title = title[2:].strip()

    # Check for banned phrases
    title_lower = title.lower()
    for phrase in BANNED_PHRASES:
        if phrase in title_lower:
            log.warning("Title contains banned phrase '%s': %s", phrase, title)
            return None

    # Enforce max 65 characters
    if len(title) > 65:
        # Try to trim at last space before 65
        trimmed = title[:65].rsplit(" ", 1)[0]
        if len(trimmed) < 10:
            return None
        title = trimmed

    # Must start with a number (100, 150, etc.)
    if not re.match(r"^\d+\s", title):
        log.warning("Title does not start with a number: %s", title)
        return None

    if title != original:
        log.info("Title adjusted: %r -> %r", original, title)

    return title


def generate_meta_description(title: str, topic: str) -> str:
    """Generate an SEO-optimized meta description from the title."""
    # Strip number prefix for the description
    desc_title = re.sub(r"^\d+\s+", "", title)
    return (
        f"Discover {title.lower()}, including meanings, origins, "
        f"pronunciation guides, and naming ideas. Find the perfect "
        f"{desc_title.lower()} for your baby."
    )[:160]


# Pool of related article slugs for internal linking
RELATED_ARTICLES_POOL = [
    ("100 Irish Baby Names for Boys and Girls", "100-irish-baby-names"),
    ("100 Japanese Baby Names and Meanings", "100-japanese-baby-names"),
    ("100 Biblical Baby Names and Meanings", "100-biblical-baby-names"),
    ("100 Baby Names That Mean Light", "100-baby-names-that-mean-light"),
    ("100 Gender Neutral Baby Names", "100-gender-neutral-baby-names"),
    ("100 Vintage Baby Names", "100-vintage-baby-names"),
    ("100 Nature Baby Names Inspired by Flowers", "100-nature-baby-names"),
    ("100 Unique Baby Names You Haven't Heard", "100-unique-baby-names"),
    ("100 Baby Boy Names That Mean Strong", "100-baby-boy-names"),
    ("100 Beautiful Baby Girl Names and Meanings", "100-baby-girl-names"),
    ("100 French Baby Names That Sound Beautiful", "100-french-baby-names"),
    ("100 Italian Baby Names and Meanings", "100-italian-baby-names"),
    ("100 Greek Baby Names from Mythology", "100-greek-baby-names"),
    ("100 Korean Baby Names and Meanings", "100-korean-baby-names"),
    ("100 Royal Baby Names for Boys and Girls", "100-royal-baby-names"),
    ("100 Warrior Baby Names and Meanings", "100-warrior-baby-names"),
    ("100 One Syllable Baby Names", "100-one-syllable-baby-names"),
    ("100 Middle Names for Girls", "100-middle-names"),
    ("100 Celestial Baby Names Inspired by Stars", "100-celestial-baby-names"),
    ("100 Country Baby Names for Boys and Girls", "100-country-baby-names"),
]
def save_and_validate(article_text: str, topic: str, blacklist: dict) -> Path | None:
    """Clean, extract, validate, and save an article.  Returns file path or None."""
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. Clean the raw response
    cleaned = strip_fences(article_text)
    body = strip_existing_frontmatter(cleaned)

    # 2. Extract and enforce SEO title rules
    raw_title = extract_title(body, topic)
    title = enforce_title_rules(raw_title)
    if title is None:
        log.error("[ERROR] Title failed SEO rules for '%s': %s", topic, raw_title)
        return None

    # 3. Dedup check
    title_lower = title.strip().lower()
    if title_lower in blacklist["titles"]:
        log.info("[INFO] Duplicate detected: title '%s' already exists. Skipping.", title)
        return None
    slug = slugify(title)
    if slug.lower() in blacklist["slugs"]:
        log.info("[INFO] Duplicate detected: slug '%s' already exists. Skipping.", slug)
        return None

    # 4. Generate labels
    labels = generate_labels(topic)

    # 5. Build frontmatter
    frontmatter = build_frontmatter(title, labels, today, topic)

    # 6. Production validation
    if not body.strip():
        log.error("[ERROR] Validation FAILED: empty body for '%s'.", topic)
        return None

    if len(title) < MIN_TITLE_LENGTH:
        log.error("[ERROR] Validation FAILED: title too short (%d chars, needs ≥%d) for '%s'.",
                  len(title), MIN_TITLE_LENGTH, title)
        return None

    word_count = count_words(body)
    if word_count < MIN_BODY_WORDS:
        log.error("[ERROR] Validation FAILED: body too short (%d words, needs ≥%d) for '%s'.",
                  word_count, MIN_BODY_WORDS, topic)
        return None

    if len(labels) < MIN_LABELS:
        log.error("[ERROR] Validation FAILED: too few labels (%d, needs ≥%d) for '%s'.",
                  len(labels), MIN_LABELS, topic)
        return None

    if title == topic:
        log.warning("Could not extract H1 title; using topic as fallback for '%s'.", topic)

    # 7. Verify frontmatter YAML
    try:
        parsed = yaml.safe_load(frontmatter.split("---")[1].strip())
    except yaml.YAMLError as exc:
        log.error("[ERROR] Validation FAILED: frontmatter YAML error — %s", exc)
        return None
    if not isinstance(parsed, dict) or "title" not in parsed or not parsed["title"]:
        log.error("[ERROR] Validation FAILED: frontmatter missing title.")
        return None

    # 8. Assemble and save
    full_doc = f"{frontmatter}\n\n{body}\n"
    filename = f"{today}-{slug}.md"
    filepath = POSTS_DIR / filename
    counter = 1
    while filepath.exists():
        filename = f"{today}-{slug}-{counter}.md"
        filepath = POSTS_DIR / filename
        counter += 1
    filepath.write_text(full_doc, encoding="utf-8")

    # 9. Post-save validation
    if not validate_saved_file(filepath):
        log.error("[ERROR] Post-save validation FAILED for '%s'. Deleting corrupt file.", topic)
        try:
            filepath.unlink()
        except Exception:
            pass
        return None

    # 10. Update history
    save_history_entry(topic, title, slug)
    log.info("[INFO] Final title: %s", title)
    log.info("Generated unique article: %s | labels=%d | %d words",
             filepath.name, len(labels), word_count)
    return filepath


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    log.info("=" * 50)
    log.info("Starting content generation for Baby Names niche…")
    log.info("Requested articles: %d | Model: %s", ARTICLES_PER_RUN, MODEL)

    api_key = os.environ.get("AGNES_API_KEY")
    if not api_key:
        log.error("AGNES_API_KEY environment variable is not set.")
        sys.exit(1)

    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    blacklist = build_blacklist()
    client = OpenAI(api_key=api_key, base_url=AGNES_BASE_URL)

    topics = pick_topics(ARTICLES_PER_RUN, blacklist)
    if not topics:
        log.warning("No fresh topics available. All %d topics have been used.", len(TOPICS))
        # Exit 0 — not a failure, just nothing to generate
        print_summary(0, 0, 0, 0, 0, 0)
        sys.exit(0)

    log.info("Selected topics for today (post-dedup):")
    for i, t in enumerate(topics, 1):
        log.info("  %d. %s", i, t)

    # Counters
    generated = 0
    rejected = 0
    duplicates_skipped = 0
    quota_failures = 0
    validation_failures = 0

    for topic in topics:
        if is_quota_exhausted():
            log.warning("[WARNING] Agnes AI rate limit reached. Stopping further generation.")
            break

        log.info("Generating article for: %s", topic)
        article = generate_article_with_retry(client, topic)

        if article is None:
            if is_quota_exhausted():
                quota_failures += 1
                break
            rejected += 1
            log.warning("Skipping topic '%s' after generation/retry failure.", topic)
            continue

        filepath = save_and_validate(article, topic, blacklist)
        if filepath:
            generated += 1
            blacklist["titles"].add(filepath.stem.lower())
            blacklist["slugs"].add(re.sub(r"^\d{4}-\d{2}-\d{2}-", "", filepath.stem).lower())
        else:
            validation_failures += 1
            log.error("Validation failed for topic '%s'; article discarded.", topic)

    print_summary(
        topics_scanned=len(topics),
        requested=ARTICLES_PER_RUN,
        generated=generated,
        rejected=rejected,
        duplicates=duplicates_skipped,
        quota_failures=quota_failures,
        validation_failures=validation_failures,
    )

    # Success rules:
    #   - generated >= 1  → success (exit 0)
    #   - generated == 0 AND quota exhausted → success (exit 0)
    #   - generated == 0 AND NOT quota → failure (exit 1)
    if generated >= 1:
        log.info("[INFO] Continuing with publishing.")
        sys.exit(0)

    if is_quota_exhausted():
        log.warning("[WARNING] Generated 0 articles before quota limit.")
        log.info("[INFO] Continuing with publishing (workflow succeeds).")
        sys.exit(0)

    log.error("[ERROR] No articles were generated. Exiting with failure.")
    sys.exit(1)


def print_summary(topics_scanned: int, requested: int, generated: int,
                  rejected: int, duplicates: int, quota_failures: int,
                  validation_failures: int = 0):
    """Print a detailed generation summary."""
    log.info("=" * 50)
    log.info("GENERATION SUMMARY")
    log.info("==================")
    log.info("  Topics scanned:        %d", topics_scanned)
    log.info("  Articles requested:    %d", requested)
    log.info("  Articles generated:    %d", generated)
    log.info("  Articles rejected:     %d", rejected)
    log.info("  Duplicates skipped:    %d", duplicates)
    log.info("  Quota failures:        %d", quota_failures)
    log.info("  Validation failures:   %d", validation_failures)
    log.info("====================")


if __name__ == "__main__":
    main()
