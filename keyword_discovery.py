#!/usr/bin/env python3
"""
Keyword Discovery Engine — Unlimited Combinatorial Topic Generator v3

Fixes applied:
- Deduplicated all cluster pools (removed ~400 duplicate items)
- Relaxed quotas from 25% to 35% with two-phase filling
- Capped pronunciation_spelling dominance (max 20%)
- Improved uncategorized resolution with better fallback chain
- Fixed diversity scoring to be batch-aware
- Expanded dimension pools for 100K+ unique topics

Dimensions (20+):
  Meaning, Origin, Gender, Popularity, Religion, Nature, Animals,
  Flowers, Colors, Season, Letter, Ending, Middle Names, Sibling Names,
  Twin Names, Nicknames, Rare, Vintage, Modern, Country, Language,
  Mythology, Occupation, Celebrity Trend, Current Year, Space, Science,
  Literature, Movies, Fantasy, History, Royalty, Music, Seasons,
  Ancient Civilizations, Japanese, Chinese, Irish, Scottish, Arabic,
  African, Biblical, Minimalist, Luxury, Elegant, Cute, Strong,
  Powerful, Unique, Short, Long, Pronunciation, Spelling, Popularity,
  Surname Ideas, Culture, Theme
"""

import hashlib
import logging
import math
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from collections import Counter

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hierarchical Top-Level Clusters
# These are used for daily diversity enforcement (Rule 5 & 6).
# Topics sharing a top-level cluster cannot appear in the same batch.
# All duplicates have been removed from these lists.
# ---------------------------------------------------------------------------

TOP_LEVEL_CLUSTERS = {
    "origin": [
        "Irish", "Japanese", "Korean", "French", "Italian", "Spanish", "German",
        "Arabic", "Greek", "Scandinavian", "Celtic", "Nordic", "Russian",
        "Polish", "Dutch", "Hawaiian", "African", "Indian", "Persian", "Chinese",
        "Hebrew", "Latin", "Slavic", "Portuguese", "Turkish", "Egyptian",
        "Mayan", "Aztec", "Sanskrit", "Welsh", "Scottish", "English",
        "Norman", "Basque", "Finnish", "Estonian", "Lithuanian", "Ukrainian",
        "Albanian", "Armenian", "Belarusian", "Bengali", "Bosnian",
        "Bulgarian", "Burmese", "Cambodian", "Croatian", "Cuban", "Danish",
        "Ethiopian", "Filipino", "Georgian", "Gujarati", "Hungarian", "Icelandic",
        "Indonesian", "Iranian", "Iraqi", "Israeli", "Kazakh", "Khmer",
        "Kurdish", "Kyrgyz", "Laotian", "Latvian", "Lebanese", "Liberian",
        "Macedonian", "Malay", "Maltese", "Mongolian", "Moroccan", "Nepali",
        "Nigerian", "Norwegian", "Pakistani", "Palestinian", "Romanian",
        "Serbian", "Sinhalese", "Somali", "Slovak", "Slovenian", "Swedish",
        "Swiss", "Tajik", "Tamil", "Thai", "Tibetan", "Tongan",
        "Trinidadian", "Tunisian", "Turkmen", "Uruguayan", "Yemeni", "Zimbabwean",
    ],
    "meaning": [
        "love", "hope", "light", "peace", "joy", "strength", "grace", "wisdom",
        "miracle", "blessing", "dream", "star", "brave", "courage", "faith",
        "truth", "honor", "victory", "freedom", "kindness", "beauty", "power",
        "valor", "noble", "gentle", "pure", "bright", "swift",
        "calm", "serene", "radiant", "divine", "eternal", "wise", "strong",
        "fierce", "bold", "free", "wild", "sweet", "soft", "warm", "cool",
        "fair", "just", "true", "good", "kind", "dear", "precious", "rare",
        "happiness", "serenity", "tranquility", "harmony", "balance", "unity",
        "compassion", "empathy", "patience", "humility", "integrity", "loyalty",
        "devotion", "gratitude", "generosity", "forgiveness", "mercy", "charity",
        "bravery", "heroism", "majesty", "regality", "splendor", "glory",
        "magnificence", "grandeur", "excellence", "perfection", "innocence",
        "purity", "cleansing", "renewal", "rebirth", "resurrection",
        "awakening", "illumination", "enlightenment", "transcendence", "ascension",
        "immortality", "infinity", "forever", "everlasting", "joyful", "cheerful",
        "merry", "gleeful", "delighted", "elated", "blissful", "content",
        "passionate", "fervent", "zealous", "ardent", "enthusiastic",
        "creative", "imaginative", "inventive", "innovative", "artistic",
        "inspiring", "motivating", "uplifting", "empowering", "strengthening",
        "flourish", "prosperity", "abundance", "wealth", "fortune", "luck",
        "knowledge", "understanding", "clarity", "vision", "insight",
        "curiosity", "wonder", "amazement", "awe", "reverence",
    ],
    "nature": [
        "flower", "tree", "ocean", "mountain", "river", "lake", "sea",
        "forest", "garden", "meadow", "field", "valley", "hill", "cliff",
        "canyon", "desert", "island", "beach", "shore", "wave", "tide",
        "stream", "brook", "pond", "spring", "glacier", "volcano", "crater",
        "earth", "fire", "water", "wind", "sky", "moon", "sun", "comet",
        "nebula", "galaxy", "cosmos", "aurora", "eclipse", "meteor", "rainbow",
        "thunder", "lightning", "storm", "blizzard", "tsunami", "earthquake",
        "landslide", "avalanche", "geyser", "hot spring", "waterfall",
        "cave", "cavern", "grotto", "lagoon", "reef", "atoll", "peninsula",
        "isthmus", "delta", "estuary", "bay", "strait", "channel", "fjord",
        "plateau", "mesa", "butte", "ridge", "peak", "summit", "crest",
        "shoreline", "coastline", "seaboard", "littoral", "tidal",
    ],
    "animals": [
        "bird", "eagle", "hawk", "falcon", "owl", "raven", "dove", "swan",
        "crane", "heron", "sparrow", "robin", "lark", "thrush", "finch",
        "lion", "tiger", "wolf", "bear", "fox", "deer", "stag", "hare",
        "rabbit", "horse", "panther", "leopard", "cheetah", "jaguar",
        "fish", "dolphin", "whale", "shark", "salmon", "trout", "bass",
        "dragon", "phoenix", "griffin", "unicorn", "centaur", "satyr",
        "snake", "turtle", "butterfly", "moth", "bee", "ant", "spider",
        "scorpion", "crab", "lobster", "octopus", "seal", "otter", "badger",
        "elephant", "giraffe", "zebra", "gorilla", "kangaroo", "koala",
        "panda", "penguin", "platypus", "armadillo", "sloth", "anteater",
        "buffalo", "bison", "moose", "caribou", "elk", "antelope", "gazelle",
        "impala", "wildebeest", "hyena", "jackal", "coyote", "bobcat", "lynx",
        "cougar", "ocelot", "serval", "caracal", "mongoose", "meerkat",
        "ferret", "weasel", "stoat", "skunk", "raccoon", "possum", "opossum",
        "piglet", "walrus", "manatee", "hippo", "rhino",
    ],
    "flowers": [
        "rose", "lily", "daisy", "violet", "jasmine", "tulip", "orchid",
        "lavender", "lotus", "iris", "peony", "hibiscus", "magnolia",
        "azalea", "camellia", "chrysanthemum", "sunflower", "poppy",
        "marigold", "blossom", "petal", "fern", "ivy", "willow", "birch",
        "maple", "oak", "pine", "cedar", "elm", "ash", "sycamore",
        "cherry", "plum", "apple", "pear", "mango", "banana", "fig",
        "cactus", "succulent", "bonsai", "bamboo", "palm", "cypress",
        "juniper", "sage", "mint", "basil", "thyme", "rosemary", "dill",
        "parsley", "cilantro", "chive", "tarragon", "coriander", "fennel",
        "gardenia", "hydrangea", "begonia", "zinnia", "petunia", "geranium",
        "dahlia", "gladiolus", "snapdragon", "cosmos", "aster",
    ],
    "mythology": [
        "greek", "roman", "norse", "egyptian", "celtic", "hindu",
        "japanese", "korean", "chinese", "mesopotamian", "babylonian",
        "persian", "aztec", "maya", "inca", "polynesian", "welsh",
        "irish", "scottish", "finnish", "slavic", "tibetan", "thai",
        "sumerian", "akkadian", "phoenician", "etruscan", "gothic", "vandals",
        "visigothic", "ostrogothic", "frankish", "saxon", "anglo-saxon",
        "norman", "borgundian", "lotharingian", "westphalian",
        "othoman", "seljuk", "ghaznavid", "safavid", "mughal", "rajput",
        "maratha", "vedic",
    ],
    "style": [
        "popular", "trending", "classic", "modern", "vintage",
        "unique", "rare", "obscure", "rising", "timeless",
        "traditional", "contemporary", "minimalist", "luxury", "elegant",
        "cute", "strong", "powerful", "bohemian", "rustic",
        "industrial", "art deco", "baroque", "rococo", "neoclassical",
        "famous", "well-known", "common", "uncommon", "extraordinary",
        "remarkable", "notable", "distinguished", "prominent", "esteemed",
        "renowned", "legendary", "iconic", "seminal", "groundbreaking",
        "trailblazing", "cutting-edge", "state-of-the-art", "avant-garde",
        "futuristic", "forward-thinking", "visionary", "revolutionary",
        "transformative", "premium", "exclusive", "special", "distinctive",
        "signature", "world-class", "top-tier", "hidden gem", "fresh", "new",
    ],
    "religion": [
        "biblical", "christian", "hebrew", "muslim", "hindu",
        "buddhist", "jewish", "catholic", "orthodox", "spiritual",
        "saint", "angelic", "monastic", "pagan", "druid",
        "zoroastrian", "shinto", "taoist", "confucian", "sikh",
        "jain", "druze", "manichaean", "gnostic", "mormon",
        "lutheran", "methodist", "presbyterian", "anglican", "baptist",
        "evangelical", "protestant", "cathar", "valdensian", "wiccana",
    ],
    "colors": [
        "red", "blue", "green", "gold", "silver", "ivory", "pearl", "ruby",
        "emerald", "sapphire", "diamond", "amber", "coral", "jade", "bronze",
        "crimson", "scarlet", "azure", "teal", "violet", "indigo", "mauve",
        "lavender", "ochre", "sienna", "umber", "ebony", "cream",
        "burgundy", "turquoise", "mint", "blush", "taupe",
        "rust", "mahogany", "walnut", "hazel", "chestnut", "copper",
        "brass", "nickel", "platinum", "chrome", "steel", "iron", "tin",
        "zinc", "cobalt", "magenta", "cyan", "yellow", "orange", "pink",
        "purple", "brown", "white", "black", "gray", "grey", "beige", "tan",
        "khaki", "navy", "maroon", "olive", "mustard", "peach", "apricot",
        "berry", "plum", "wine", "sherry", "port",
    ],
    "seasons": [
        "spring", "summer", "autumn", "winter", "seasonal",
        "solstice", "equinox", "monsoon", "harvest", "bloom",
        "frost", "snow", "rain", "thunder", "lightning",
    ],
    "occupations": [
        "king", "queen", "prince", "princess", "noble", "royal",
        "warrior", "knight", "soldier", "guardian", "protector",
        "scholar", "teacher", "healer", "artist", "musician",
        "poet", "writer", "singer", "dancer", "painter",
        "hunter", "fisher", "weaver", "smith", "builder",
        "leader", "chief", "ruler", "ranger", "scout",
        "doctor", "engineer", "scientist", "astronomer", "philosopher",
        "explorer", "adventurer", "captain", "admiral", "general",
        "judge", "lawyer", "architect", "chef", "farmer",
        "priest", "monk", "nun", "rabbi", "imam", "pastor",
        "bishop", "cardinal", "deacon", "minister", "missionary",
        "merchant", "banker", "broker", "dealer",
        "tailor", "baker", "butcher", "cobbler", "carpenter", "mason",
        "plumber", "electrician", "mechanic", "driver", "pilot", "sailor",
        "marine", "firefighter", "paramedic", "nurse",
        "physician", "surgeon", "dentist", "psychologist", "sociologist",
        "anthropologist", "historian", "geographer", "economist", "politician",
        "diplomat", "ambassador", "journalist", "reporter", "editor",
        "photographer", "cinematographer", "filmmaker", "director", "producer",
        "curator", "librarian", "archivist", "professor", "lecturer",
    ],
    "celebrity_trends": [
        "celebrity", "influencer", "instagram", "tiktok", "viral",
        "hollywood", "pop star", "rock star", "superhero", "movie star",
        "tv star", "streaming", "podcast", "youtube", "twitch",
        "athlete", "champion", "olympian", "medalist", "award winner",
        "streamer", "gamer", "esports", "record holder", "nominee", "laureate",
        "nobel", "pulitzer", "oscar", "emmy", "grammy", "tony", "bafta",
    ],
    "space_science": [
        "cosmic", "stellar", "lunar", "solar", "galactic", "nebular",
        "orbital", "cometary", "planetary", "astro", "quantum",
        "atomic", "molecular", "celestial", "meteoric", "supernova",
        "pulsar", "quasar", "void", "eclipse", "aurora", "zodiac",
        "constellation", "andromeda", "orion", "pleiades", "ursa",
        "lyra", "cygnus", "draco", "pegasus", "aquarius", "libra",
        "leo", "virgo", "scorpio", "sagittarius", "capricorn",
        "aries", "taurus", "gemini", "cancer", "aquila", "phoenix",
        "grus", "telescopium", "horologium", "volans", "mensa", "norma",
        "cassiopeia", "hydra", "centaurus", "corona",
        "equuleus", "carina", "vela", "puppis", "pyxis", "antlia",
        "circinus", "musca", "apus",
    ],
    "literature_fantasy": [
        "fantasy", "mythical", "legendary", "epic", "heroic",
        "enchanted", "magical", "arcane", "ethereal", "mystic",
        "wizard", "sorcerer", "witch", "elf", "dwarf", "dragon",
        "fairy", "troll", "goblin", "vampire", "werewolf",
        "medieval", "renaissance", "high fantasy", "steampunk", "cyberpunk",
        "dystopian", "utopian", "post-apocalyptic", "sherlock", "arthur",
        "tolkien", "holmes", "dracula", "frankenstein", "gatsby",
        "scout", "atticus", "huck", "tom", "becky",
        "winnie", "pooh", "piglet", "eeyore", "tigger",
        "robinson", "defoe", "swift", "gulliver", "verne", "jules",
    ],
    "history_ancient": [
        "ancient", "classical", "medieval", "renaissance", "baroque",
        "romantic", "victorian", "edwardian", "georgian", "colonial",
        "revolutionary", "imperial", "dynastic", "feudal", "tribal",
        "pharaonic", "samurai", "viking", "celtic", "roman empire",
        "byzantine", "ottoman", "mongol", "carolingian", "habsburg",
        "tudor", "stuart", "hanoverian", "plantagenet", "windsor",
        "bonaparte", "hohenzollern", "wittelsbach", "medici", "borghese",
        "farnese", "sforza", "borgia", "strozzi", "vespucci",
        "da vinci", "michelangelo", "raphael", "donatello",
        "borgundian", "lotharingian", "westphalian", "othoman",
        "seljuk", "ghaznavid", "safavid", "mughal", "rajput", "maratha",
        "vedic", "assyrian", "babylonian", "sumerian", "akkadian",
        "etruscan", "gothic", "vandals", "visigothic", "ostrogothic",
        "frankish", "saxon", "anglo-saxon", "norman",
    ],
    "countries_cities": [
        "american", "british", "australian", "canadian", "brazilian",
        "mexican", "argentinian", "chilean", "colombian", "peruvian",
        "thai", "vietnamese", "indonesian", "malaysian", "filipino",
        "london", "paris", "rome", "tokyo", "beijing", "sydney",
        "barcelona", "venice", "prague", "vienna", "berlin", "moscow",
        "cairo", "mumbai", "seoul", "bangkok", "istanbul", "dubai",
        "new york", "los angeles", "chicago", "toronto", "vancouver",
        "manchester", "liverpool", "bristol", "birmingham", "glasgow",
        "edinburgh", "cardiff", "dublin", "oslo", "stockholm", "copenhagen",
        "helsinki", "reykjavik", "lisbon", "madrid", "athens", "sofia",
        "bucharest", "budapest", "warsaw", "zurich", "geneva",
    ],
    "pronunciation_spelling": [
        "easy to pronounce", "simple spelling", "short name", "long name",
        "one syllable", "two syllables", "three syllables", "four syllables",
        "starts with vowel", "ends with consonant", "double letter",
        "silent letter", "accented", "diacritical", "phonetic",
        "unusual spelling", "traditional spelling", "modern spelling",
        "easy reading", "hard to spell", "straightforward", "complex",
        "basic", "advanced", "elementary", "sophisticated",
    ],
    "family_relationships": [
        "middle name", "sibling name", "twin name", "nickname",
        "surname", "last name", "first name", "birth name",
        "maiden name", "family name", "generational", "patronymic",
        "matronymic", "clan name", "tribal name", "household name",
        "brother", "sister", "cousin", "uncle", "aunt",
        "nephew", "niece", "grandfather", "grandmother", "grandson",
        "son", "daughter", "parents", "child", "infant", "toddler",
        "baby", "newborn", "expectant", "pregnant", "motherhood", "fatherhood",
    ],
    "traits_qualities": [
        "cute", "beautiful", "handsome", "elegant", "refined",
        "gentle", "strong", "powerful", "fierce", "bold",
        "courageous", "fearless", "brave", "noble", "wise",
        "kind", "compassionate", "merciful", "just", "honest",
        "loyal", "faithful", "devoted", "humble", "gracious",
        "charming", "delightful", "enchanting", "mysterious", "enigmatic",
        "adventurous", "spirited", "vivacious", "radiant", "luminous",
        "dynamic", "energetic", "vibrant", "resilient", "tenacious",
        "persistent", "determined", "relentless", "innovative", "creative",
        "imaginative", "inventive", "original", "versatile", "flexible",
        "adaptable", "resourceful", "ingenious", "clever",
        "expert", "masterful", "skilled", "talented", "gifted",
        "brilliant", "genius", "scholarly", "academic", "intellectual",
        "well-known", "renowned", "famous", "legendary", "iconic",
        "seminal", "groundbreaking", "trailblazing", "cutting-edge",
        "state-of-the-art", "avant-garde", "futuristic", "visionary",
        "revolutionary", "transformative", "premium", "exclusive",
        "special", "distinctive", "signature", "world-class", "top-tier",
        "hidden gem", "fresh", "new", "modern", "timeless", "classic",
        "dear", "precious", "cherished", "beloved", "treasured",
    ],
}

# ---------------------------------------------------------------------------
# Expanded dimension pools (deduplicated)
# ---------------------------------------------------------------------------

MEANINGS = [
    "love", "hope", "light", "peace", "joy", "strength", "grace", "wisdom",
    "miracle", "blessing", "dream", "star", "brave", "courage", "faith",
    "truth", "honor", "victory", "freedom", "kindness", "beauty", "power",
    "valor", "noble", "gentle", "pure", "bright", "swift",
    "calm", "serene", "radiant", "divine", "eternal", "wise", "strong",
    "fierce", "bold", "free", "wild", "sweet", "soft", "warm", "cool",
    "fair", "just", "true", "good", "kind", "dear", "precious", "rare",
    "happiness", "serenity", "tranquility", "harmony", "balance", "unity",
    "compassion", "empathy", "patience", "humility", "integrity", "loyalty",
    "devotion", "gratitude", "generosity", "forgiveness", "mercy", "charity",
    "bravery", "heroism", "majesty", "regality", "splendor", "glory",
    "magnificence", "grandeur", "excellence", "perfection", "innocence",
    "purity", "cleansing", "renewal", "rebirth", "resurrection",
    "awakening", "illumination", "enlightenment", "transcendence", "ascension",
    "immortality", "infinity", "forever", "everlasting", "joyful", "cheerful",
    "merry", "gleeful", "delighted", "elated", "blissful", "content",
    "passionate", "fervent", "zealous", "ardent", "enthusiastic",
    "creative", "imaginative", "inventive", "innovative", "artistic",
    "inspiring", "motivating", "uplifting", "empowering", "strengthening",
    "flourish", "prosperity", "abundance", "wealth", "fortune", "luck",
    "knowledge", "understanding", "clarity", "vision", "insight",
    "curiosity", "wonder", "amazement", "awe", "reverence",
]

ORIGINS = [
    "Irish", "Japanese", "Korean", "French", "Italian", "Spanish", "German",
    "Arabic", "Greek", "Scandinavian", "Celtic", "Nordic", "Russian",
    "Polish", "Dutch", "Hawaiian", "African", "Indian", "Persian", "Chinese",
    "Hebrew", "Latin", "Slavic", "Portuguese", "Turkish", "Egyptian",
    "Mayan", "Aztec", "Sanskrit", "Welsh", "Scottish", "English",
    "Norman", "Basque", "Finnish", "Estonian", "Lithuanian", "Ukrainian",
    "Albanian", "Armenian", "Belarusian", "Bengali", "Bosnian",
    "Bulgarian", "Burmese", "Cambodian", "Croatian", "Cuban", "Danish",
    "Ethiopian", "Filipino", "Georgian", "Gujarati", "Hungarian", "Icelandic",
    "Indonesian", "Iranian", "Iraqi", "Israeli", "Kazakh", "Khmer",
    "Kurdish", "Kyrgyz", "Laotian", "Latvian", "Lebanese", "Liberian",
    "Macedonian", "Malay", "Maltese", "Mongolian", "Moroccan", "Nepali",
    "Nigerian", "Norwegian", "Pakistani", "Palestinian", "Romanian",
    "Serbian", "Sinhalese", "Somali", "Slovak", "Slovenian", "Swedish",
    "Swiss", "Tajik", "Tamil", "Thai", "Tibetan", "Tongan",
    "Trinidadian", "Tunisian", "Turkmen", "Uruguayan", "Yemeni", "Zimbabwean",
]

GENGENDERS = ["baby", "boy", "girl", "unisex", "gender-neutral"]

POPULARITY = [
    "popular", "trending", "classic", "modern", "vintage",
    "unique", "rare", "obscure", "rising", "timeless",
    "traditional", "contemporary", "minimalist", "luxury", "elegant",
    "famous", "well-known", "common", "uncommon", "extraordinary",
    "remarkable", "notable", "distinguished", "prominent", "esteemed",
    "renowned", "legendary", "iconic", "seminal", "groundbreaking",
    "trailblazing", "cutting-edge", "state-of-the-art", "avant-garde",
    "futuristic", "forward-thinking", "visionary", "revolutionary",
    "transformative", "premium", "exclusive", "special", "distinctive",
    "signature", "world-class", "top-tier", "hidden gem", "fresh", "new",
]

RELIGIONS = [
    "biblical", "christian", "hebrew", "muslim", "hindu",
    "buddhist", "jewish", "catholic", "orthodox", "spiritual",
    "saint", "angelic", "monastic", "pagan", "druid",
    "zoroastrian", "shinto", "taoist", "confucian", "sikh",
    "jain", "druze", "manichaean", "gnostic", "mormon",
    "lutheran", "methodist", "presbyterian", "anglican", "baptist",
    "evangelical", "protestant", "cathar", "valdensian", "wiccana",
]

NATURE = [
    "flower", "tree", "ocean", "mountain", "river", "lake", "sea",
    "forest", "garden", "meadow", "field", "valley", "hill", "cliff",
    "canyon", "desert", "island", "beach", "shore", "wave", "tide",
    "stream", "brook", "pond", "spring", "glacier", "volcano", "crater",
    "earth", "fire", "water", "wind", "sky", "moon", "sun", "comet",
    "nebula", "galaxy", "cosmos", "aurora", "eclipse", "meteor", "rainbow",
    "thunder", "lightning", "storm", "blizzard", "tsunami", "earthquake",
    "landslide", "avalanche", "geyser", "hot spring", "waterfall",
    "cave", "cavern", "grotto", "lagoon", "reef", "atoll", "peninsula",
    "isthmus", "delta", "estuary", "bay", "strait", "channel", "fjord",
    "plateau", "mesa", "butte", "ridge", "peak", "summit", "crest",
    "shoreline", "coastline", "seaboard", "littoral", "tidal",
]

ANIMALS = [
    "bird", "eagle", "hawk", "falcon", "owl", "raven", "dove", "swan",
    "crane", "heron", "sparrow", "robin", "lark", "thrush", "finch",
    "lion", "tiger", "wolf", "bear", "fox", "deer", "stag", "hare",
    "rabbit", "horse", "panther", "leopard", "cheetah", "jaguar",
    "fish", "dolphin", "whale", "shark", "salmon", "trout", "bass",
    "dragon", "phoenix", "griffin", "unicorn", "centaur", "satyr",
    "snake", "turtle", "butterfly", "moth", "bee", "ant", "spider",
    "scorpion", "crab", "lobster", "octopus", "seal", "otter", "badger",
    "elephant", "giraffe", "zebra", "gorilla", "kangaroo", "koala",
    "panda", "penguin", "platypus", "armadillo", "sloth", "anteater",
    "buffalo", "bison", "moose", "caribou", "elk", "antelope", "gazelle",
    "impala", "wildebeest", "hyena", "jackal", "coyote", "bobcat", "lynx",
    "cougar", "ocelot", "serval", "caracal", "mongoose", "meerkat",
    "ferret", "weasel", "stoat", "skunk", "raccoon", "possum", "opossum",
    "piglet", "walrus", "manatee", "hippo", "rhino",
]

FLOWERS = [
    "rose", "lily", "daisy", "violet", "jasmine", "tulip", "orchid",
    "lavender", "lotus", "iris", "peony", "hibiscus", "magnolia",
    "azalea", "camellia", "chrysanthemum", "sunflower", "poppy",
    "marigold", "blossom", "petal", "fern", "ivy", "willow", "birch",
    "maple", "oak", "pine", "cedar", "elm", "ash", "sycamore",
    "cherry", "plum", "apple", "pear", "mango", "banana", "fig",
    "cactus", "succulent", "bonsai", "bamboo", "palm", "cypress",
    "juniper", "sage", "mint", "basil", "thyme", "rosemary", "dill",
    "parsley", "cilantro", "chive", "tarragon", "coriander", "fennel",
    "gardenia", "hydrangea", "begonia", "zinnia", "petunia", "geranium",
    "dahlia", "gladiolus", "snapdragon", "cosmos", "aster",
]

COLORS = [
    "red", "blue", "green", "gold", "silver", "ivory", "pearl", "ruby",
    "emerald", "sapphire", "diamond", "amber", "coral", "jade", "bronze",
    "crimson", "scarlet", "azure", "teal", "violet", "indigo", "mauve",
    "lavender", "ochre", "sienna", "umber", "ebony", "cream",
    "burgundy", "turquoise", "mint", "blush", "taupe",
    "rust", "mahogany", "walnut", "hazel", "chestnut", "copper",
    "brass", "nickel", "platinum", "chrome", "steel", "iron", "tin",
    "zinc", "cobalt", "magenta", "cyan", "yellow", "orange", "pink",
    "purple", "brown", "white", "black", "gray", "grey", "beige", "tan",
    "khaki", "navy", "maroon", "olive", "mustard", "peach", "apricot",
    "berry", "plum", "wine", "sherry", "port",
]

SEASONS = ["spring", "summer", "autumn", "winter", "seasonal"]

LETTERS = list("abcdefghijklmnopqrstuvwxyz")

ENDINGS = [
    "a", "ia", "ea", "oa", "ua",
    "o", "io", "eo", "ao",
    "er", "or", "ar", "ir", "ur",
    "ley", "leigh", "ly", "ney",
    "wood", "worth", "ton", "field", "dale", "gate",
    "ette", "elle", "ine",
    "wen", "lyn", "ynn", "ren",
    "ith", "iel",
    "son", "sen", "zen", "den", "ben",
    "ford", "burg", "berg", "stein", "feld",
    "heim", "dorf", "stadt", "haven",
    "wick", "bury", "chester", "caster",
    "bridge", "brook", "well", "park",
    "shire", "ham", "stead", "ville",
    "court", "place", "road", "lane",
]

YEARS = [str(y) for y in range(2025, 2040)]

MYTHOLOGIES = [
    "greek", "roman", "norse", "egyptian", "celtic", "hindu",
    "japanese", "korean", "chinese", "mesopotamian", "babylonian",
    "persian", "aztec", "maya", "inca", "polynesian", "welsh",
    "irish", "scottish", "finnish", "slavic", "tibetan", "thai",
    "sumerian", "akkadian", "phoenician", "etruscan", "gothic", "vandals",
    "visigothic", "ostrogothic", "frankish", "saxon", "anglo-saxon",
    "norman", "borgundian", "lotharingian", "westphalian",
    "othoman", "seljuk", "ghaznavid", "safavid", "mughal", "rajput",
    "maratha", "vedic",
]

OCCUPATIONS = [
    "king", "queen", "prince", "princess", "noble", "royal",
    "warrior", "knight", "soldier", "guardian", "protector",
    "scholar", "teacher", "healer", "artist", "musician",
    "poet", "writer", "singer", "dancer", "painter",
    "hunter", "fisher", "weaver", "smith", "builder",
    "leader", "chief", "ruler", "ranger", "scout",
    "doctor", "engineer", "scientist", "astronomer", "philosopher",
    "explorer", "adventurer", "captain", "admiral", "general",
    "judge", "lawyer", "architect", "chef", "farmer",
    "priest", "monk", "nun", "rabbi", "imam", "pastor",
    "bishop", "cardinal", "deacon", "minister", "missionary",
    "merchant", "banker", "broker", "dealer",
    "tailor", "baker", "butcher", "cobbler", "carpenter", "mason",
    "plumber", "electrician", "mechanic", "driver", "pilot", "sailor",
    "marine", "firefighter", "paramedic", "nurse",
    "physician", "surgeon", "dentist", "psychologist", "sociologist",
    "anthropologist", "historian", "geographer", "economist", "politician",
    "diplomat", "ambassador", "journalist", "reporter", "editor",
    "photographer", "cinematographer", "filmmaker", "director", "producer",
    "curator", "librarian", "archivist", "professor", "lecturer",
]

CELEBRITY_TRENDS = [
    "celebrity", "influencer", "instagram", "tiktok", "viral",
    "hollywood", "pop star", "rock star", "superhero", "movie star",
    "tv star", "streaming", "podcast", "youtube", "twitch",
    "streamer", "gamer", "esports", "athlete", "champion", "olympian",
    "record holder", "medalist", "award winner", "nominee", "laureate",
    "nobel", "pulitzer", "oscar", "emmy", "grammy", "tony", "bafta",
]

SPACE_SCIENCE = [
    "cosmic", "stellar", "lunar", "solar", "galactic", "nebular",
    "orbital", "cometary", "planetary", "astro", "quantum",
    "atomic", "molecular", "celestial", "meteoric", "supernova",
    "pulsar", "quasar", "void", "eclipse", "aurora", "zodiac",
    "constellation", "andromeda", "orion", "pleiades", "ursa",
    "lyra", "cygnus", "draco", "pegasus", "aquarius", "libra",
    "leo", "virgo", "scorpio", "sagittarius", "capricorn",
    "aries", "taurus", "gemini", "cancer", "aquila", "phoenix",
    "grus", "telescopium", "horologium", "volans", "mensa", "norma",
    "cassiopeia", "hydra", "centaurus", "corona",
    "equuleus", "carina", "vela", "puppis", "pyxis", "antlia",
    "circinus", "musca", "apus",
]

LITERATURE_FANTASY = [
    "fantasy", "mythical", "legendary", "epic", "heroic",
    "enchanted", "magical", "arcane", "ethereal", "mystic",
    "wizard", "sorcerer", "witch", "elf", "dwarf", "dragon",
    "fairy", "troll", "goblin", "vampire", "werewolf",
    "medieval", "renaissance", "high fantasy", "steampunk", "cyberpunk",
    "dystopian", "utopian", "post-apocalyptic", "sherlock", "arthur",
    "tolkien", "holmes", "dracula", "frankenstein", "gatsby",
    "scout", "atticus", "huck", "tom", "becky",
    "winnie", "pooh", "piglet", "eeyore", "tigger",
    "robinson", "defoe", "swift", "gulliver", "verne", "jules",
]

HISTORY_ANCIENT = [
    "ancient", "classical", "medieval", "renaissance", "baroque",
    "romantic", "victorian", "edwardian", "georgian", "colonial",
    "revolutionary", "imperial", "dynastic", "feudal", "tribal",
    "pharaonic", "samurai", "viking", "celtic", "roman empire",
    "byzantine", "ottoman", "mongol", "carolingian", "habsburg",
    "tudor", "stuart", "hanoverian", "plantagenet", "windsor",
    "bonaparte", "hohenzollern", "wittelsbach", "medici", "borghese",
    "farnese", "sforza", "borgia", "strozzi", "vespucci",
    "da vinci", "michelangelo", "raphael", "donatello",
    "borgundian", "lotharingian", "westphalian", "othoman",
    "seljuk", "ghaznavid", "safavid", "mughal", "rajput", "maratha",
    "vedic", "assyrian", "babylonian", "sumerian", "akkadian",
    "etruscan", "gothic", "vandals", "visigothic", "ostrogothic",
    "frankish", "saxon", "anglo-saxon", "norman",
]

COUNTRIES_CITIES = [
    "american", "british", "australian", "canadian", "brazilian",
    "mexican", "argentinian", "chilean", "colombian", "peruvian",
    "thai", "vietnamese", "indonesian", "malaysian", "filipino",
    "london", "paris", "rome", "tokyo", "beijing", "sydney",
    "barcelona", "venice", "prague", "vienna", "berlin", "moscow",
    "cairo", "mumbai", "seoul", "bangkok", "istanbul", "dubai",
    "new york", "los angeles", "chicago", "toronto", "vancouver",
    "manchester", "liverpool", "bristol", "birmingham", "glasgow",
    "edinburgh", "cardiff", "dublin", "oslo", "stockholm", "copenhagen",
    "helsinki", "reykjavik", "lisbon", "madrid", "athens", "sofia",
    "bucharest", "budapest", "warsaw", "zurich", "geneva",
]

PRONUNCIATION_SPELLING = [
    "easy to pronounce", "simple spelling", "short name", "long name",
    "one syllable", "two syllables", "three syllables", "four syllables",
    "starts with vowel", "ends with consonant", "double letter",
    "silent letter", "accented", "diacritical", "phonetic",
    "unusual spelling", "traditional spelling", "modern spelling",
    "easy reading", "hard to spell", "straightforward", "complex",
    "basic", "advanced", "elementary", "sophisticated",
]

FAMILY_RELATIONSHIPS = [
    "middle name", "sibling name", "twin name", "nickname",
    "surname", "last name", "first name", "birth name",
    "maiden name", "family name", "generational", "patronymic",
    "matronymic", "clan name", "tribal name", "household name",
    "brother", "sister", "cousin", "uncle", "aunt",
    "nephew", "niece", "grandfather", "grandmother", "grandson",
    "son", "daughter", "parents", "child", "infant", "toddler",
    "baby", "newborn", "expectant", "pregnant", "motherhood", "fatherhood",
]

TRAITS_QUALITIES = [
    "cute", "beautiful", "handsome", "elegant", "refined",
    "gentle", "strong", "powerful", "fierce", "bold",
    "courageous", "fearless", "brave", "noble", "wise",
    "kind", "compassionate", "merciful", "just", "honest",
    "loyal", "faithful", "devoted", "humble", "gracious",
    "charming", "delightful", "enchanting", "mysterious", "enigmatic",
    "adventurous", "spirited", "vivacious", "radiant", "luminous",
    "dynamic", "energetic", "vibrant", "resilient", "tenacious",
    "persistent", "determined", "relentless", "innovative", "creative",
    "imaginative", "inventive", "original", "versatile", "flexible",
    "adaptable", "resourceful", "ingenious", "clever",
    "expert", "masterful", "skilled", "talented", "gifted",
    "brilliant", "genius", "scholarly", "academic", "intellectual",
    "well-known", "renowned", "famous", "legendary", "iconic",
    "seminal", "groundbreaking", "trailblazing", "cutting-edge",
    "state-of-the-art", "avant-garde", "futuristic", "visionary",
    "revolutionary", "transformative", "premium", "exclusive",
    "special", "distinctive", "signature", "world-class", "top-tier",
    "hidden gem", "fresh", "new", "modern", "timeless", "classic",
    "dear", "precious", "cherished", "beloved", "treasured",
]

# ---------------------------------------------------------------------------
# Template library -- expanded with cross-dimensional combinations
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

    # Occasion / Season
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

    # Cross-dimensional
    "{origin} {meaning} {gender} names",
    "{nature} {meaning} {gender} names",
    "{mythology} {meaning} {gender} names",
    "{color} {meaning} {gender} names",
    "{animal} {meaning} {gender} names",
    "{flower} {meaning} {gender} names",
    "{origin} {popularity} {gender} names",
    "{mythology} {popularity} {gender} names",
    "{nature} {popularity} {gender} names",
    "{popularity} {origin} {gender} names",
    "{popularity} {meaning} {gender} names",
    "{popularity} {nature} {gender} names",
    "{religion} {meaning} {gender} names",
    "{religion} {origin} {gender} names",
    "{space} {meaning} {gender} names",
    "{space} {origin} {gender} names",
    "{literature} {meaning} {gender} names",
    "{history} {origin} {gender} names",
    "{country} {meaning} {gender} names",
    "{country} {origin} {gender} names",
    "{trait} {origin} {gender} names",
    "{trait} {meaning} {gender} names",
    "{trait} {nature} {gender} names",
    "{trait} {mythology} {gender} names",
    "{pronunciation} {origin} {gender} names",
    "{pronunciation} {meaning} {gender} names",
    "{family} {origin} names for {gender}",
    "{family} {meaning} names for {gender}",
    "{celebrity} {gender} baby names",
    "{celebrity} inspired {gender} names",
    "{occupation} {gender} names",
    "{occupation} inspired {gender} baby names",

    # Multi-dimension deep combos
    "unique {origin} {meaning} {gender} names",
    "rare {mythology} {meaning} {gender} names",
    "modern {nature} {meaning} {gender} names",
    "vintage {color} {meaning} {gender} names",
    "classic {animal} {meaning} {gender} names",
    "popular {space} {origin} {gender} names",
    "trending {literature} {meaning} {gender} names",
    "famous {history} {origin} {gender} names",
    "best {country} {meaning} {gender} names",
    "top {trait} {nature} {gender} names",
    "beautiful {flower} {meaning} {gender} names",
    "strong {animal} {meaning} {gender} names",
    "cute {color} {meaning} {gender} names",
    "elegant {origin} {meaning} {gender} names",
    "powerful {occupation} {meaning} {gender} names",

   # Season-specific
    # Religion-specific
    "{religion} {gender} baby names",
    "traditional {religion} {gender} names",
    "{religion} inspired {gender} baby names",
    "modern {religion} {gender} names",

    # Countries/Cities-specific
    "{country} {gender} baby names",
    "{country} inspired {gender} names",
    "names from {country} for {gender}",
    "{country} style {gender} names",

    # Seasons-specific (expanded)
    "{season} {gender} baby names",
    "{season} born {gender} names",
    "{season} themed {gender} names",
    "{season} inspired {gender} baby names",

    # Space/Science-specific
    "{space} {gender} baby names",
    "cosmic {gender} baby names",
    "{space} inspired {gender} names",
    "stellar {gender} baby names",

    # Literature/Fantasy-specific
    "{literature} {gender} baby names",
    "fantasy {gender} baby names",
    "{literature} inspired {gender} names",
    "mythic {gender} baby names",

    # History/Ancient-specific
    "{history} {gender} baby names",
    "ancient {gender} baby names",
    "{history} inspired {gender} names",
    "historical {gender} baby names",

    # Celebrity/Trends-specific
    "{celebrity} {gender} baby names",
    "trending {gender} baby names",
    "{celebrity} inspired {gender} names",
    "viral {gender} baby names",

    # Style-specific (explicit)
    "minimalist {gender} baby names",
    "luxury {gender} baby names",
    "elegant {gender} baby names",
    "boho {gender} baby names",

    # Flowers-specific (explicit)
    "{flower} {gender} baby names",
    "floral {gender} baby names",
    "{flower} inspired {gender} names",

    # Occupations-specific (explicit)
    "{occupation} {gender} baby names",
    "professional {gender} baby names",
    "{occupation} inspired {gender} names",

    # Colors-specific (explicit)
    "{color} {gender} baby names",
    "colorful {gender} baby names",
    "{color} themed {gender} names",

    # Nature-specific (explicit)
    "{nature} {gender} baby names",
    "natural {gender} baby names",
    "{nature} inspired {gender} names",

    # Animals-specific (explicit)
    "{animal} {gender} baby names",
    "wild {gender} baby names",
    "{animal} inspired {gender} names",

    # Mythology-specific (explicit)
    "{mythology} {gender} baby names",
    "mythological {gender} baby names",
    "{mythology} inspired {gender} names",

    # Traits/Qualities-specific (explicit)
    "{trait} {gender} baby names",
    "{trait} inspired {gender} names",
    "strong {gender} baby names",
    "bold {gender} baby names",

    # Pronunciation/Spelling-specific (explicit)
    "{pronunciation} {gender} baby names",
    "phonetic {gender} baby names",
    "{pronunciation} inspired {gender} names",

    # Family Relationships-specific (explicit)
    "{family} {gender} baby names",
    "family {gender} baby names",
    "{family} inspired {gender} names"
    "{season} born {gender} names",
    "{season} {origin} {gender} names",
    "{season} {meaning} {gender} names",
    "{season} {nature} {gender} names",

    # Letter-specific
    "{origin} {gender} names starting with {letter}",
    "{meaning} {gender} names starting with {letter}",
    "{nature} {gender} names starting with {letter}",
    "{mythology} {gender} names starting with {letter}",
    "{color} {gender} names starting with {letter}",
    "{animal} {gender} names starting with {letter}",

    # Ending-specific
    "{origin} {gender} names ending with {ending}",
    "{meaning} {gender} names ending with {ending}",
    "{nature} {gender} names ending with {ending}",
    "{mythology} {gender} names ending with {ending}",
    "{color} {gender} names ending with {ending}",
]


def _normalize(keyword: str) -> str:
    """Normalize a keyword for dedup comparison."""
    return re.sub(r"\s+", " ", keyword.strip().lower())


def _keyword_hash(keyword: str) -> str:
    """SHA-256 hash for content dedup."""
    return hashlib.sha256(_normalize(keyword).encode()).hexdigest()[:16]


# Structural filler phrases to strip before similarity comparison.
FILLER_PATTERNS = [
    r'\bbaby\s+names\b', r'\bnames\b', r'\bfor\s+\w+\b',
    r'\bthat\s+mean\b', r'\bwith\s+meaning\b',
    r'\bthat\s+end\b', r'\bending\s+with\b',
    r'\bstarting\s+with\b', r'\bbeginning\s+with\b',
    r'\bof\s+\w+\s+names\b', r'\bthe\s+rise\b',
    r'\bdiscovers?\b', r'\bperfect\b', r'\bchoices\b',
    r'\bparents\b', r'\blittle\s+\w+\b', r'\bafter\b',
    r'\baround\s+the\s+world\b', r'\bgreat\b', r'\bflair\b',
    r'\bfree\s+spirit\b', r'\bhero(?:ine)?\b', r'\bmaestro\b',
    r'\bearthy\b', r'\bbotanical\b', r'\bmonikers?\b',
    r'\bprof(?:ound|er)\b', r'\bin(?:spire|spiring)\b',
    r'\bend(?:earing|earing)?\b', r'\bflourish\b',
    r'\bjourney\b', r'\bfind(?:ing|s)?\b', r'\bexplore\b',
    r'\bcomprehensive\b', r'\bcurated\b', r'\blist\b',
    r'\bcollection\b', r'\bguide\b', r'\binsights?\b',
    r'\btips?\b', r'\bideas?\b', r'\bsuggestions?\b',
    r'\brecommendations?\b', r'\bessential\b', r'\bultimate\b',
]


def _strip_fillers(text: str) -> str:
    """Remove structural filler phrases so similarity compares actual topic content."""
    result = text.lower()
    for pattern in FILLER_PATTERNS:
        result = re.sub(pattern, ' ', result)
    return re.sub(r'\s+', ' ', result).strip()


# ---------------------------------------------------------------------------
# Similarity Engine (Rule 1: Never generate the same topic twice)
# ---------------------------------------------------------------------------

def _jaccard_similarity(a: str, b: str) -> float:
    """Compute Jaccard similarity between two normalized strings."""
    a_clean = _strip_fillers(a)
    b_clean = _strip_fillers(b)

    set_a = set(a_clean.split())
    set_b = set(b_clean.split())
    if not set_a or not set_b:
        set_a = set(a.split())
        set_b = set(b.split())
        if not set_a or not set_b:
            return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _levenshtein_distance(a: str, b: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if len(a) < len(b):
        return _levenshtein_distance(b, a)
    if not b:
        return len(a)

    prev_row = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr_row = [i + 1]
        for j, cb in enumerate(b):
            insert_cost = prev_row[j + 1] + 1
            delete_cost = curr_row[j] + 1
            replace_cost = prev_row[j] + (ca != cb)
            curr_row.append(min(insert_cost, delete_cost, replace_cost))
        prev_row = curr_row
    return prev_row[-1]


def _levenshtein_similarity(a: str, b: str) -> float:
    """Compute similarity based on Levenshtein distance."""
    if not a or not b:
        return 0.0
    max_len = max(len(a), len(b))
    dist = _levenshtein_distance(a, b)
    return 1.0 - (dist / max_len)


def _topic_similarity(topic_a: str, topic_b: str) -> float:
    """Combined similarity score using Jaccard + Levenshtein."""
    norm_a = _normalize(topic_a)
    norm_b = _normalize(topic_b)

    if norm_a == norm_b:
        return 1.0

    a_clean = _strip_fillers(norm_a)
    b_clean = _strip_fillers(norm_b)

    if not a_clean and not b_clean:
        a_clean = norm_a
        b_clean = norm_b
    elif not a_clean or not b_clean:
        a_clean = norm_a
        b_clean = norm_b

    jaccard = _jaccard_similarity(a_clean, b_clean)
    levenshtein = _levenshtein_similarity(a_clean, b_clean)

    return 0.6 * jaccard + 0.4 * levenshtein


# ---------------------------------------------------------------------------
# Cluster classification (Rule 2: hierarchical clusters)
# ---------------------------------------------------------------------------

def _extract_top_level_cluster_v2(keyword: str) -> str:
    """Improved cluster extraction with structural pattern detection.

    Uses a tiered approach:
    1. Explicit structural patterns (letter-based, ending-based, etc.)
    2. Template-aware classification (matches known template patterns)
    3. Scoring with minimal filler exclusion
    4. Last resort: best-match on non-filler words
    """
    kw_lower = _normalize(keyword)
    words = kw_lower.split()

    # Tier 1: Explicit structural patterns
    if re.search(r'starting\s+with\s+[a-z]', kw_lower) or \
       re.search(r'beginning\s+with\s+[a-z]', kw_lower):
        return "pronunciation_spelling"

    if re.search(r'ending\s+(?:with|in)\s+[a-z]', kw_lower):
        return "pronunciation_spelling"

    if re.search(r'[0-9]+\s*syl[l]?lable', kw_lower):
        return "pronunciation_spelling"

    if 'middle name' in kw_lower:
        return "family_relationships"

    if any(w in kw_lower for w in ['sibling', 'twin', 'nickname']):
        return "family_relationships"

    if any(w in kw_lower for w in ['surname', 'last name', 'patronymic',
                                     'matronymic', 'clan name', 'tribal name']):
        return "family_relationships"

    # Tier 1b: Celebrity-specific keywords (before generic word matching)
    celebrity_keywords = ['trending', 'viral', 'influencer',
                          'famous', 'icon', 'legendary']
    if any(w in kw_lower for w in celebrity_keywords):
        # Check if it's NOT already classified as space_science
        space_items = [s.lower() for s in TOP_LEVEL_CLUSTERS["space_science"]
                       if re.search(r"\b" + re.escape(s.lower()) + r"\b", kw_lower)]
        if not space_items:
            return "celebrity_trends"

    # Tier 2: Template-aware classification (explicit pattern checks)
    origins_matched = [o for o in TOP_LEVEL_CLUSTERS["origin"]
                       if re.search(r"\b" + re.escape(o.lower()) + r"\b", kw_lower)]
    if origins_matched:
        return "origin"

    meanings_matched = [m for m in TOP_LEVEL_CLUSTERS["meaning"]
                        if re.search(r"\b" + re.escape(m.lower()) + r"\b", kw_lower)]
    if meanings_matched:
        return "meaning"

    traits_matched = [t for t in TOP_LEVEL_CLUSTERS["traits_qualities"]
                      if re.search(r"\b" + re.escape(t.lower()) + r"\b", kw_lower)]
    if traits_matched:
        return "traits_qualities"

    flowers_matched = [f for f in TOP_LEVEL_CLUSTERS["flowers"]
                       if re.search(r"\b" + re.escape(f.lower()) + r"\b", kw_lower)]
    if flowers_matched:
        return "flowers"

    animals_matched = [a for a in TOP_LEVEL_CLUSTERS["animals"]
                       if re.search(r"\b" + re.escape(a.lower()) + r"\b", kw_lower)]
    if animals_matched:
        return "animals"

    colors_matched = [c for c in TOP_LEVEL_CLUSTERS["colors"]
                      if re.search(r"\b" + re.escape(c.lower()) + r"\b", kw_lower)]
    if colors_matched:
        return "colors"

    nature_matched = [n for n in TOP_LEVEL_CLUSTERS["nature"]
                      if re.search(r"\b" + re.escape(n.lower()) + r"\b", kw_lower)]
    if nature_matched:
        return "nature"

    mythologies_matched = [m for m in TOP_LEVEL_CLUSTERS["mythology"]
                           if re.search(r"\b" + re.escape(m.lower()) + r"\b", kw_lower)]
    if mythologies_matched:
        return "mythology"

    space_matched = [s for s in TOP_LEVEL_CLUSTERS["space_science"]
                     if re.search(r"\b" + re.escape(s.lower()) + r"\b", kw_lower)]
    if space_matched:
        return "space_science"

    hist_matched = [h for h in TOP_LEVEL_CLUSTERS["history_ancient"]
                    if re.search(r"\b" + re.escape(h.lower()) + r"\b", kw_lower)]
    if hist_matched:
        return "history_ancient"

    lit_matched = [l for l in TOP_LEVEL_CLUSTERS["literature_fantasy"]
                   if re.search(r"\b" + re.escape(l.lower()) + r"\b", kw_lower)]
    if lit_matched:
        return "literature_fantasy"

    country_matched = [c for c in TOP_LEVEL_CLUSTERS["countries_cities"]
                        if re.search(r"\b" + re.escape(c.lower()) + r"\b", kw_lower)]
    if country_matched:
        return "countries_cities"

    seasons_matched = [s for s in TOP_LEVEL_CLUSTERS["seasons"]
                        if re.search(r"\b" + re.escape(s.lower()) + r"\b", kw_lower)]
    if seasons_matched:
        return "seasons"

    religions_matched = [r for r in TOP_LEVEL_CLUSTERS["religion"]
                          if re.search(r"\b" + re.escape(r.lower()) + r"\b", kw_lower)]
    if religions_matched:
        return "religion"

    occupations_matched = [o for o in TOP_LEVEL_CLUSTERS["occupations"]
                          if re.search(r"\b" + re.escape(o.lower()) + r"\b", kw_lower)]
    if occupations_matched:
        return "occupations"

    celeb_matched = [c for c in TOP_LEVEL_CLUSTERS["celebrity_trends"]
                    if re.search(r"\b" + re.escape(c.lower()) + r"\b", kw_lower)]
    if celeb_matched:
        return "celebrity_trends"

    style_matched = [s for s in TOP_LEVEL_CLUSTERS["style"]
                    if re.search(r"\b" + re.escape(s.lower()) + r"\b", kw_lower)]
    if style_matched:
        return "style"

    # Tier 3: Try scoring with minimal filler exclusion
    MINIMAL_FILLERS = {
        "baby", "names", "name", "for", "the", "of", "and", "with",
        "that", "to", "in", "is", "are", "it", "its",
        "discovering", "perfect", "choices", "inspire",
        "beautiful", "powerful", "strong", "cute", "timeless",
        "popular", "unique", "rare", "best", "top", "great",
        "modern", "classic", "vintage", "traditional",
        "them", "themed", "inspired", "ideas", "world",
        "around", "hottest", "right", "now", "comprehensive",
        "guide", "list", "collection", "flourish", "journey",
        "findings", "finding", "explore", "curated",
    }

    scores = {}
    for cluster_name, items in TOP_LEVEL_CLUSTERS.items():
        score = 0
        for item in items:
            item_lower = item.lower()
            if item_lower in MINIMAL_FILLERS:
                continue
            if ' ' in item_lower:
                if re.search(r'\b' + re.escape(item_lower) + r'\b', kw_lower):
                    score += 10
            else:
                for word in words:
                    clean_word = re.sub(r'[^a-z0-9]', '', word)
                    if clean_word == item_lower:
                        score += max(1, len(item_lower))
                        break
        if score > 0:
            scores[cluster_name] = score

    if scores:
        return max(scores.keys(), key=lambda k: (scores[k], k))

    # Tier 4: Best-match on non-filler words
    non_filler_words = set()
    for word in words:
        clean_word = re.sub(r'[^a-z0-9]', '', word).lower()
        if clean_word and clean_word not in MINIMAL_FILLERS and len(clean_word) > 2:
            non_filler_words.add(clean_word)

    if non_filler_words:
        best_score = 0
        best_cluster = None
        for cluster_name, items in TOP_LEVEL_CLUSTERS.items():
            for item in items:
                item_lower = item.lower()
                if item_lower in MINIMAL_FILLERS:
                    continue
                if item_lower in non_filler_words:
                    s = len(item_lower)
                    if s > best_score:
                        best_score = s
                        best_cluster = cluster_name

        if best_cluster:
            return best_cluster

    # Tier 5: Template-based fallback for structural patterns
    if 'names for' in kw_lower or 'names for babies' in kw_lower:
        for word in non_filler_words:
            if len(word) > 4:
                for cn, items in TOP_LEVEL_CLUSTERS.items():
                    for item in items:
                        if item.lower() == word:
                            return cn
    elif 'baby names that mean' in kw_lower:
        return "meaning"
    elif 'baby names that end' in kw_lower or 'baby names ending' in kw_lower:
        return "pronunciation_spelling"
    elif 'baby names beginning' in kw_lower or 'baby names start' in kw_lower:
        return "pronunciation_spelling"

    # Tier 6: If we have non-filler words, try to find the best match
    if non_filler_words:
        best_match = None
        best_len = 0
        for word in non_filler_words:
            if len(word) > best_len:
                best_len = len(word)
                best_match = word

        if best_match:
            for cn, items in TOP_LEVEL_CLUSTERS.items():
                for item in items:
                    if item.lower() == best_match:
                        return cn

    return "uncategorized"


# ---------------------------------------------------------------------------
# Keyword Discovery (Rules 3-8: expansion, randomization, diversity)
# ---------------------------------------------------------------------------

def discover_keywords(queue, count: int = 100,
                      history_blacklist=None,
                      similarity_threshold: float = 0.15) -> list:
    """Discover up to `count` unique keywords with relaxed quotas.

    Two-phase approach:
    Phase 1: Fill minimum per cluster (ensures all clusters represented)
    Phase 2: Free selection with relaxed max quota (allows flexibility)

    Also enforces a hard cap on pronunciation_spelling to prevent letter/ending
    template dominance.
    """
    seen = set()
    if history_blacklist:
        seen = {_normalize(h) for h in history_blacklist}

    db_keywords = set()
    try:
        existing = queue.conn.execute(
            "SELECT LOWER(keyword) FROM keywords WHERE status != 'pending'"
        ).fetchall()
        db_keywords = {r[0] for r in existing}
    except Exception:
        pass

    seen |= db_keywords

    num_clusters = len(TOP_LEVEL_CLUSTERS)
    min_per_cluster = max(3, count // num_clusters)  # at least 3 or equal share
    max_per_cluster = int(count * 0.35)  # relaxed from 25% to 35%

    # Hard cap for pronunciation_spelling (prevents letter/ending template dominance)
    max_pronunciation = int(count * 0.20)  # max 20% for pronunciation_spelling

    cluster_counts = {cl: 0 for cl in TOP_LEVEL_CLUSTERS}
    candidates = []
    attempts = 0
    max_attempts = count * 500

    random.seed()

    # Phase 1: Ensure minimum coverage per cluster
    # Build cluster->template index for targeted selection
    _placeholder_to_cluster = {
        '{origin}': 'origin', '{meaning}': 'meaning',
        '{nature}': 'nature', '{animal}': 'animals',
        '{flower}': 'flowers', '{color}': 'colors',
        '{season}': 'seasons', '{mythology}': 'mythology',
        '{space}': 'space_science', '{literature}': 'literature_fantasy',
        '{history}': 'history_ancient', '{country}': 'countries_cities',
        '{religion}': 'religion', '{occupation}': 'occupations',
        '{celebrity}': 'celebrity_trends', '{trait}': 'traits_qualities',
        '{pronunciation}': 'pronunciation_spelling',
        '{family}': 'family_relationships',
        '{letter}': 'pronunciation_spelling', '{ending}': 'pronunciation_spelling',
        '{gender}': 'family_relationships', '{popularity}': 'style',
        '{year}': 'style',
    }
    _cluster_templates = {cl: [] for cl in TOP_LEVEL_CLUSTERS}
    for _i, _tmpl in enumerate(TEMPLATES):
        _matched = set()
        for _ph, _cl in _placeholder_to_cluster.items():
            if _ph in _tmpl:
                _matched.add(_cl)
        for _cl in _matched:
            _cluster_templates[_cl].append(_i)

    while len(candidates) < count and attempts < max_attempts:
        attempts += 1

        # Prioritize underfilled clusters
        underfilled = [cl for cl, cnt in cluster_counts.items()
                       if cnt < min_per_cluster]

        if underfilled:
            # Pick a random underfilled cluster that has templates
            viable = [cl for cl in underfilled if _cluster_templates.get(cl)]
            if viable:
                target_cl = random.choice(viable)
                template = TEMPLATES[random.choice(_cluster_templates[target_cl])]
            else:
                template = random.choice(TEMPLATES)
        else:
            # Phase 2: Free selection
            template = random.choice(TEMPLATES)

        keyword = _fill_template(template)
        normalized = _normalize(keyword)

        if normalized in seen:
            continue

        # Similarity check against known topics
        is_similar = False
        for seen_kw in list(seen)[:200]:
            sim = _topic_similarity(normalized, seen_kw)
            if sim > similarity_threshold:
                is_similar = True
                break

        if is_similar:
            continue

        # Keyword blacklist: reject if normalized keyword contains any blacklisted term
        keyword_blacklist_terms = [
            "gender-neutral", "gender neutral", "biblical baby names",
            "musical baby names", "mythological monikers", "bohemian baby names",
            "gender neutral baby names", "gender-neutral baby names",
        ]
        is_blacklisted = False
        for term in keyword_blacklist_terms:
            if term in normalized:
                is_blacklisted = True
                break
        if is_blacklisted:
            continue

        intent, cluster, priority, difficulty, volume, cpc = _score_keyword(keyword)
        top_level = _extract_top_level_cluster_v2(keyword)

        # Enforce per-cluster quotas
        current_count = cluster_counts.get(top_level, 0)

        # Hard cap for pronunciation_spelling
        if top_level == "pronunciation_spelling" and current_count >= max_pronunciation:
            continue

        # Phase 1: Must fill minimum first
        if current_count < min_per_cluster:
            # Allow through even if over soft max during phase 1
            pass
        elif current_count >= max_per_cluster:
            continue

        seen.add(normalized)
        cluster_counts[top_level] = current_count + 1

        candidates.append((
            keyword, intent, cluster, priority, difficulty, volume, cpc,
            top_level,
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
        "{space}": random.choice(SPACE_SCIENCE),
        "{literature}": random.choice(LITERATURE_FANTASY),
        "{history}": random.choice(HISTORY_ANCIENT),
        "{country}": random.choice(COUNTRIES_CITIES),
        "{pronunciation}": random.choice(PRONUNCIATION_SPELLING),
        "{family}": random.choice(FAMILY_RELATIONSHIPS),
        "{trait}": random.choice(TRAITS_QUALITIES),
        "{celebrity}": random.choice(CELEBRITY_TRENDS),
    }

    keyword = template
    for placeholder, value in replacements.items():
        keyword = keyword.replace(placeholder, value)

    keyword = re.sub(r"\s+", " ", keyword).strip()
    return keyword


def _score_keyword(keyword: str) -> tuple:
    """Score a keyword for CPC, intent, cluster, priority, difficulty, volume."""
    kw = keyword.lower()

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
        "space": 1.30, "cosmic": 1.25, "stellar": 1.20,
        "fantasy": 1.40, "dragon": 1.35, "wizard": 1.30,
        "literature": 1.15, "book": 1.10, "novel": 1.05,
        "history": 1.10, "ancient": 1.05, "medieval": 1.00,
        "royalty": 1.50, "prince": 1.45, "princess": 1.45,
        "surname": 1.20, "last name": 1.15, "first name": 1.10,
        "twin": 1.45, "nickname": 1.30, "sibling": 1.25,
    }

    cpc = 0.50
    for term, value in cpc_map.items():
        if term in kw:
            cpc = max(cpc, value)

    if "meaning" in kw or "mean" in kw:
        intent = "LIST_INTENT"
    elif any(o.lower() in kw for o in ORIGINS):
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

    top_level = _extract_top_level_cluster_v2(keyword)

    leaf_parts = []
    for cluster_name, items in TOP_LEVEL_CLUSTERS.items():
        for item in items:
            item_lower = item.lower()
            if ' ' in item_lower:
                if item_lower in kw:
                    leaf_parts.append(item_lower)
                    break
            else:
                words = kw.split()
                for word in words:
                    clean_word = re.sub(r'[^a-z0-9]', '', word)
                    if clean_word == item_lower:
                        leaf_parts.append(item_lower)
                        break
                if item_lower in leaf_parts:
                    break

    if leaf_parts:
        leaf = max(leaf_parts, key=len)
        cluster = "%s_%s" % (top_level, leaf)
    else:
        cluster = "%s_general" % top_level

    priority = 50.0
    if cpc >= 2.0:
        priority = 80.0
    elif cpc >= 1.5:
        priority = 65.0
    if "unique" in kw or "rare" in kw:
        priority += 10
    if "middle" in kw or "sibling" in kw:
        priority += 5

    difficulty = 60.0
    if "baby names" in kw:
        difficulty = 75.0
    if "unique" in kw or "rare" in kw:
        difficulty = 40.0
    for o in ORIGINS:
        if o.lower() in kw:
            difficulty = min(difficulty, 35.0)
            break

    volume = 1000
    if cpc >= 2.0:
        volume = 10000
    elif cpc >= 1.5:
        volume = 5000
    if "unique" in kw or "rare" in kw:
        volume = max(volume, 3000)

    return intent, cluster, round(priority, 1), round(difficulty, 1), volume, round(cpc, 2)


def get_all_dimension_pool_sizes() -> dict:
    """Return the size of each dimension pool for validation."""
    sizes = {}
    for name in dir():
        val = globals().get(name)
        if isinstance(val, list) and len(val) > 5:
            sizes[name] = len(val)
    return sizes


def get_total_theoretical_combinations() -> int:
    """Calculate approximate total unique combinations across all dimensions."""
    sizes = get_all_dimension_pool_sizes()
    avg_size = sum(sizes.values()) / max(len(sizes), 1)
    single_ph = sum(1 for t in TEMPLATES if t.count("{") == 1)
    double_ph = sum(1 for t in TEMPLATES if t.count("{") == 2)
    triple_ph = sum(1 for t in TEMPLATES if t.count("{") >= 3)
    return int(single_ph * avg_size + double_ph * avg_size ** 2 +
               triple_ph * avg_size ** 3)
