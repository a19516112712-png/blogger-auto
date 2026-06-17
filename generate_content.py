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
MIN_TITLE_LENGTH = 20       # characters
MIN_BODY_WORDS = 200        # words (~1200 chars typical)
MIN_LABELS = 4
MAX_LABELS = 6

# Quota tracking (module-level — survives across retries but not runs)
_quota_exhausted = False


# ---------------------------------------------------------------------------
# Expanded Topic Pool (200+ unique baby-name topics)
# ---------------------------------------------------------------------------
TOPICS = [
    # --- Biblical & Religious ---
    "Biblical baby names with timeless appeal",
    "Hebrew baby names and their profound meanings",
    "Christian baby names inspired by saints and scripture",
    "Angelic baby names from religious traditions",
    "Virtue baby names: faith, hope, grace and more",
    "Names from the Old Testament for modern families",
    "New Testament baby names for boys and girls",
    "Spiritual baby names from world religions",
    # --- Vintage & Classic ---
    "Vintage baby names making a stunning comeback",
    "Classic baby names that never go out of style",
    "Old-fashioned baby names with old-world charm",
    "Retro baby names from the roaring 1920s",
    "Victorian-era baby names for elegant boys and girls",
    "Edwardian baby names full of sophistication",
    "Timeless baby names from the 1950s",
    "Antique baby names being rediscovered today",
    # --- Nature-Inspired ---
    "Nature-inspired baby names for modern parents",
    "Earthy and botanical baby names for girls and boys",
    "Floral baby names blooming with beauty and meaning",
    "Tree and forest baby names rooted in nature",
    "Mountain-inspired baby names: strong and majestic",
    "Meadow and field baby names full of serenity",
    "Desert baby names: unique names with sandy charm",
    "River and stream baby names flowing with grace",
    "Garden-inspired baby names fresh and lovely",
    "Seasonal baby names: spring, summer, autumn, winter",
    # --- Ocean & Water ---
    "Ocean and water-inspired baby names for beach lovers",
    "Beach and coastal baby names from shores worldwide",
    "Sea creature baby names: unique and playful",
    "Sailor and nautical baby names with maritime spirit",
    "Island baby names from tropical paradises",
    "Lake-inspired baby names calm and reflective",
    # --- Celestial & Space ---
    "Celestial and space-inspired baby names",
    "Star and constellation baby names for starry-eyed parents",
    "Moon-inspired baby names: lunar and luminous",
    "Galaxy and cosmic baby names out of this world",
    "Astronomy baby names from planets and moons",
    "Sun-inspired baby names bright and radiant",
    "Zodiac and astrology baby names by star sign",
    # --- Mythological ---
    "Baby names inspired by Greek mythology",
    "Roman mythology baby names of gods and goddesses",
    "Norse mythology baby names: viking strength",
    "Egyptian mythology baby names from ancient pharaohs",
    "Celtic mythology baby names of legends and lore",
    "Hindu mythology baby names rich in tradition",
    "Japanese mythological baby names full of spirit",
    # --- Literary ---
    "Literary baby names from classic novels",
    "Shakespearean baby names: dramatic and timeless",
    "Poetic baby names inspired by famous poets",
    "Fairy tale baby names from beloved stories",
    "Jane Austen baby names: regency charm",
    "Fantasy novel baby names for imaginative parents",
    "Children book baby names that spark nostalgia",
    # --- Royal & Aristocratic ---
    "Royal and aristocratic baby names for little princes and princesses",
    "British royal family baby names: regal and refined",
    "European monarchy baby names of kings and queens",
    "Noble baby names from aristocratic bloodlines",
    "Regal baby names fit for royalty",
    "Crown-inspired baby names dripping with elegance",
    # --- Musical & Arts ---
    "Musical baby names for creative families",
    "Opera-inspired baby names for dramatic flair",
    "Jazz and blues baby names cool and soulful",
    "Rock and roll baby names with rebellious spirit",
    "Classical composer baby names harmonious and grand",
    "Art-inspired baby names from famous painters",
    "Dance-inspired baby names graceful and rhythmic",
    # --- International ---
    "International baby names that work in any language",
    "French baby names: chic and sophisticated",
    "Italian baby names: romantic and melodic",
    "Irish baby names full of Celtic charm",
    "Scottish baby names: strong and storied",
    "German baby names: sturdy and meaningful",
    "Spanish baby names: passionate and vibrant",
    "Greek baby names: ancient and enduring",
    "Russian baby names: distinctive and bold",
    "Scandinavian baby names: nordic and cool",
    "Japanese baby names: elegant and meaningful",
    "Korean baby names: modern and graceful",
    "Chinese baby names rich in symbolism",
    "Indian baby names: diverse and spiritual",
    "Arabic baby names: poetic and powerful",
    "Persian baby names: ancient and regal",
    "African baby names from diverse cultures",
    "Hawaiian baby names: island beauty",
    "Native American baby names: earthy and meaningful",
    "Australian Aboriginal baby names: unique and ancient",
    "Brazilian baby names: rhythmic and warm",
    "Swedish baby names: clean and modern",
    "Dutch baby names: distinctive and charming",
    "Polish baby names: strong and traditional",
    # --- Strong & Powerful ---
    "Strong baby boy names with deep meanings",
    "Powerful baby names meaning courage and bravery",
    "Warrior baby names for fearless little fighters",
    "Heroic baby names from history and legend",
    "Names with powerful meanings: strength, honor, wisdom",
    "Bold baby names that command attention",
    "Fearless baby names for adventurous spirits",
    # --- Elegant & Beautiful ---
    "Beautiful baby girl names from around the world",
    "Elegant baby girl names: sophisticated and graceful",
    "Feminine baby names with delicate charm",
    "Charming baby girl names parents adore",
    "Melodic baby girl names that sing",
    "Romantic baby names for dreamy parents",
    "Enchanting baby names with magical appeal",
    # --- Gender-Neutral ---
    "Gender-neutral baby names on the rise",
    "Unisex baby names: modern and flexible",
    "Modern baby names that break gender norms",
    "Trending gender-neutral baby names for progressive parents",
    "Androgynous baby names: stylish and inclusive",
    # --- Unique & Rare ---
    "Unique baby names parents haven't overused yet",
    "Rare baby names you won't find on every playground",
    "Uncommon baby names: stand out from the crowd",
    "Distinctive baby names that make a statement",
    "One-of-a-kind baby names for extraordinary children",
    "Hidden gem baby names waiting to be discovered",
    "Under-the-radar baby names quietly gaining popularity",
    # --- Short Names ---
    "Short and sweet one-syllable baby names",
    "Two-syllable baby names: the perfect balance",
    "Three-letter baby names: tiny but mighty",
    "Minimalist baby names for simple elegance",
    # --- Color & Nature ---
    "Color-inspired baby names: vibrant and bright",
    "Gemstone baby names: precious and rare",
    "Bird-inspired baby names: free and soaring",
    "Animal-inspired baby names wild and wonderful",
    "Weather-inspired baby names: storm, rain, and sky",
    "Rainbow baby names full of color and hope",
    # --- Trendy & Modern ---
    "Trending baby names for the current year",
    "Modern baby names defining a generation",
    "Popular baby names climbing the charts",
    "Celebrity baby names that set trends",
    "Social media-inspired baby names for the digital age",
    "Tech-inspired baby names for forward-thinking parents",
    "Hottest baby names right now worldwide",
    # --- Intellectual & STEM ---
    "Baby names inspired by famous scientists and inventors",
    "Philosopher baby names for deep thinkers",
    "Mathematician baby names: precise and elegant",
    "Explorer baby names for adventurous souls",
    "Astronaut baby names reaching for the stars",
    "Engineer baby names: innovative and strong",
    # --- BoHo & Artistic ---
    "Bohemian baby names with artistic flair",
    "Free-spirited baby names for wanderlust parents",
    "Hippie baby names: peace, love, and harmony",
    "Creative baby names for artistic families",
    "Eclectic baby names for unconventional parents",
    # --- Seasonal & Calendar ---
    "Spring baby names blooming with new life",
    "Summer baby names warm and radiant",
    "Autumn baby names rich and golden",
    "Winter baby names crisp and magical",
    "Holiday-inspired baby names for festive families",
    "Christmas baby names: joyful and meaningful",
    # --- Love & Emotion ---
    "Love-inspired baby names from around the world",
    "Names meaning love: romantic baby name ideas",
    "Joyful baby names radiating happiness",
    "Peaceful baby names: calm and serene",
    "Names meaning hope and faith for your little one",
    # --- Food & Nature ---
    "Food-inspired baby names: sweet and savory",
    "Spice baby names with warm, exotic flair",
    "Herb and plant baby names from the garden",
    "Fruit-inspired baby names: fresh and delightful",
    "Wine and vineyard baby names for connoisseurs",
    # --- Country & Western ---
    "Country baby names: southern charm and grace",
    "Western baby names with cowboy spirit",
    "Ranch-inspired baby names rugged and rustic",
    "Farmhouse baby names with wholesome appeal",
    # --- Fantasy & Pop Culture ---
    "Disney-inspired baby names: magical and beloved",
    "Movie character baby names from iconic films",
    "TV show baby names trending with fans",
    "Video game baby names for gamer parents",
    "Comic book baby names: superhero strength",
    "Anime baby names: Japanese pop culture gems",
    # --- Spiritual & Meaningful ---
    "Meditation-inspired baby names for peaceful souls",
    "Zen baby names: minimalist and meaningful",
    "Yoga-inspired baby names for balanced lives",
    "Soulful baby names with deep spiritual meaning",
    "Karmic baby names: destiny and purpose",
    "Nature spiritual baby names from indigenous traditions",
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
SYSTEM_PROMPT = """You are a professional SEO content writer specializing in baby names.
You write engaging, well-researched, and informative blog articles for expectant parents.

Return ONLY the article body in markdown. Do NOT include YAML frontmatter or fenced code blocks.

Structure:
- *First line* must be an H1 heading (# Title) — this becomes the post title
- Engaging introduction (2-3 paragraphs)
- Use H2 (##) for major sections and H3 (###) for subsections
- Include 4-5 H2 sections with substantive content
- At least one H2 section should be a list or comparison format
- End with an H2 FAQ section containing 4-5 questions with detailed answers
- Total length: 800-1200 words (at least 200 words minimum)
- Use bullet points and numbered lists where appropriate
- Bold key terms and baby names for emphasis
- Write in a warm, helpful tone suitable for parents"""


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


def build_frontmatter(title: str, labels: list[str], today: str) -> str:
    """Construct a valid YAML frontmatter block using yaml.dump."""
    data = {"title": title, "labels": labels, "date": today}
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
def save_and_validate(article_text: str, topic: str, blacklist: dict) -> Path | None:
    """Clean, extract, validate, and save an article.  Returns file path or None."""
    today = datetime.now().strftime("%Y-%m-%d")

    # 1. Clean the raw response
    cleaned = strip_fences(article_text)
    body = strip_existing_frontmatter(cleaned)

    # 2. Extract and sanitize title
    raw_title = extract_title(body, topic)
    title = sanitize_title(raw_title)

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
    frontmatter = build_frontmatter(title, labels, today)

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
