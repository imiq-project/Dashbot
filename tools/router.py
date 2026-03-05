"""
Semantic tool router using embeddings. Routes user queries to relevant tools based on semantic similarity.
"""

import re
import numpy as np
from typing import Dict, Optional, Tuple, List
from sentence_transformers import SentenceTransformer


class ToolEmbeddingLoader:

    def __init__(self):
        self.embedder: Optional[SentenceTransformer] = None
        self.model_name: str = ""
        self.tool_embeddings: Dict[str, np.ndarray] = {}

    def load_or_compute(
        self,
        model_name: str,
        tool_descriptions: Dict[str, str],
        force_recompute: bool = False
    ) -> Tuple[SentenceTransformer, Dict[str, np.ndarray]]:
        print(f"Loading embedding model ({model_name})...")
        self.embedder = SentenceTransformer(model_name)
        self.model_name = model_name

        print(f"Computing embeddings for {len(tool_descriptions)} tools...")
        self.tool_embeddings = {}

        for name, desc in tool_descriptions.items():
            clean_desc = ' '.join(desc.split())
            embedding = self.embedder.encode(clean_desc, normalize_embeddings=True)
            self.tool_embeddings[name] = embedding

        print(f"Tool embeddings ready ({len(self.tool_embeddings)} tools)")
        return self.embedder, self.tool_embeddings


TOOL_DESCRIPTIONS = {
    "search_knowledge": """
        Knowledge base search. Project information, city details, team members.
        Background information, history, descriptions, explanations.

        Questions like:
        - "What is this project?"
        - "Tell me about Magdeburg"
        - "Who works on this?"
        - "What is IMIQ?"
        - "Explain the university"
        - "History of OVGU"
        - "What is the campus about?"

        General information queries, not navigation or real-time data.
    """,

    "query_campus_sensors": """
        Real-time sensor data. Current weather, parking, traffic, air quality conditions.

        Questions like:
        - "What's the weather right now?"
        - "Is it raining?"
        - "Current temperature"
        - "Is there parking available?"
        - "How busy is the traffic?"
        - "Parking at north park"
        - "Air quality"
        - "PM2.5 levels"

        Current conditions, not forecasts or navigation.
    """,

    "get_weather_forecast": """
        Future weather prediction. Tomorrow, next week, upcoming days.

        Questions like:
        - "Weather forecast"
        - "Will it rain tomorrow?"
        - "Weather this weekend"
        - "Next 3 days weather"
        - "Should I bring umbrella tomorrow?"

        Future weather only, not current conditions.
    """,

    "get_mobility": """
        Navigation and travel between locations. Distance, time, routes, duration.
        Walking, cycling, driving, tram, bus - all transport options.

        PUBLIC TRANSIT: Provides estimated journey duration based on typical patterns
        (2 minutes per stop, 5 minutes per transfer, 3 minutes initial wait).
        Returns which tram/bus lines to take, transfer points, and estimated time.

        WALKING/CYCLING/DRIVING: Provides actual distance and travel time from routing API.

        Questions like:
        - "How do I get to Hauptbahnhof?"
        - "How long does it take by tram to Reform?"
        - "How far is the university from Alter Markt?"
        - "How long to walk to mensa?"
        - "Distance from A to B"
        - "Which tram goes to Reform?"
        - "I'm at Reform, how to get to Wissenschaftshafen?"
        - "Route from library to station"
        - "Travel time to city center"
        - "Can I walk there?"
        - "Best way to get to campus"
        - "How many kilometers to downtown?"
        - "How long will the journey take?"

        Any question about getting from one place to another.
        Origin and destination. From X to Y. Travel, route, directions, duration.
    """,

    "get_building": """
        Campus building information. Building details, facilities inside.

        Questions like:
        - "Where is building 29?"
        - "What's in the library building?"
        - "Find the mensa"
        - "Computer science building"
        - "Buildings near the library"

        Building info, not navigation between places.
    """,

    "get_transit_info": """
        Transit system information. Stop details, line routes, schedules.

        Questions like:
        - "What lines stop at Hauptbahnhof?"
        - "Where does Tram 5 go?"
        - "All stops on line 9"
        - "Transfer hubs"
        - "Nearest tram to library"

        Transit system info, not routing between places.
    """,

    "get_landmark_info": """
        Campus landmarks and points of interest. Monuments, notable places.

        Questions like:
        - "Where is the campus tower?"
        - "Tell me about landmarks"
        - "Meeting points on campus"
        - "Notable places"
    """,

    "find_places": """
        Restaurants, cafes, food, eating, dining, mensa, supermarkets, shopping, vegan, vegetarian.
        Where to eat, what to eat, food options, menu, cuisine, lunch, dinner, breakfast.

        Questions like:
        - "Where can I eat?"
        - "Find restaurants near me"
        - "Italian restaurants"
        - "Pizza nearby"
        - "What's for lunch at mensa?"
        - "Mensa menu today"
        - "Coffee shops near campus"
        - "Supermarket near university"
        - "Asian food options"
        - "Where to get coffee?"
        - "Best pizza place"
        - "Greek restaurant"
        - "Cafeteria on campus"
        - "Places to eat near building 29"
        - "Food near Hauptbahnhof"
        - "Breakfast options"
        - "Ice cream"
        - "Bubble tea"
        - "Vegan restaurants"
        - "Vegetarian food"
        - "Where can I get lunch?"
        - "Any good restaurants nearby?"
        - "Food options"
        - "Somewhere to eat"

        Any question about food, restaurants, cafes, eating, menu, cuisine, or shopping.
    """
}


class CompoundQueryDetector:

    COMPOUND_PATTERNS = [
        r'\band\b',
        r'\balso\b',
        r'\bplus\b',
        r'\bas well\b',
        r'\btoo\b',
        r'\?.*\?',
        r',\s*(are there|where|what|is there|can I|find)',
    ]

    TOOL_KEYWORDS = {
        "find_places": [
            "restaurant", "restaurants", "cafe", "cafes", "coffee",
            "food", "eat", "eating", "lunch", "dinner", "breakfast",
            "mensa", "menu", "supermarket", "shop", "pizza", "burger",
            "vegan", "vegetarian", "asian", "italian", "greek", "chinese",
            "ice cream", "bubble tea", "cuisine", "hungry", "snack"
        ],
        "get_mobility": [
            "how to get", "get to", "go to", "route", "directions",
            "from", "to", "walk", "bike", "drive", "tram", "bus",
            "distance", "how far", "how long", "travel", "transit"
        ],
        "query_campus_sensors": [
            "weather", "temperature", "rain", "parking", "traffic",
            "air quality", "pm2.5", "humidity", "sensor"
        ],
        "get_weather_forecast": [
            "forecast", "tomorrow", "weekend", "next week", "will it rain"
        ],
        "get_building": [
            "building", "where is", "located", "find the", "faculty"
        ],
        "search_knowledge": [
            "what is", "tell me about", "explain", "who", "history"
        ]
    }

    @classmethod
    def is_compound_query(cls, query: str) -> bool:
        query_lower = query.lower()

        for pattern in cls.COMPOUND_PATTERNS:
            if re.search(pattern, query_lower):
                return True

        return False

    @classmethod
    def detect_required_tools(cls, query: str) -> List[str]:
        query_lower = query.lower()
        required_tools = set()

        for tool_name, keywords in cls.TOOL_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    required_tools.add(tool_name)
                    break

        return list(required_tools)

    @classmethod
    def split_query(cls, query: str) -> List[str]:
        parts = re.split(r'\band\b|\balso\b|\bplus\b|,\s*(?=are there|where|what|is there|can I|find)',
                        query, flags=re.IGNORECASE)

        cleaned = []
        for part in parts:
            part = part.strip()
            if part and len(part) > 5:
                cleaned.append(part)

        return cleaned if len(cleaned) > 1 else [query]


class SmartToolRouter:

    RECOMMENDED_MODELS = [
        "BAAI/bge-base-en-v1.5",
        "intfloat/e5-base-v2",
        "all-mpnet-base-v2",
        "all-MiniLM-L6-v2",
    ]

    def __init__(
        self,
        tools: list,
        model_name: str = "BAAI/bge-base-en-v1.5",
        tool_descriptions: Dict[str, str] = None
    ):
        print("Setting up tool router...")

        self.tools = tools
        self.tool_map = {t["function"]["name"]: t for t in tools}
        self.model_name = model_name

        descriptions = tool_descriptions or TOOL_DESCRIPTIONS

        self.tool_descriptions = {
            name: desc for name, desc in descriptions.items()
            if name in self.tool_map
        }

        self._loader = ToolEmbeddingLoader()
        self.embedder, self.tool_embeddings = self._loader.load_or_compute(
            model_name=model_name,
            tool_descriptions=self.tool_descriptions
        )

        print(f"Tool router ready ({len(self.tool_embeddings)} tools, model: {model_name})")

    def get_relevant_tools(
        self,
        query: str,
        top_k: int = 4,
        threshold: float = 0.25
    ) -> Tuple[List[dict], Dict[str, float]]:
        is_compound = CompoundQueryDetector.is_compound_query(query)
        keyword_tools = CompoundQueryDetector.detect_required_tools(query)

        if is_compound or len(keyword_tools) > 1:
            print(f"   Compound query detected! Keywords suggest: {keyword_tools}")

        if "bge" in self.model_name.lower():
            query_text = f"Represent this sentence for searching relevant tools: {query}"
        else:
            query_text = query

        query_embedding = self.embedder.encode(query_text, normalize_embeddings=True)

        scores = {}
        for name, emb in self.tool_embeddings.items():
            score = float(np.dot(query_embedding, emb))
            if score >= threshold:
                scores[name] = score

        for tool_name in keyword_tools:
            if tool_name in scores:
                scores[tool_name] = min(0.95, scores[tool_name] + 0.15)
            elif tool_name in self.tool_embeddings:
                scores[tool_name] = threshold + 0.1

        effective_top_k = top_k
        if is_compound or len(keyword_tools) > 1:
            effective_top_k = max(top_k, len(keyword_tools) + 1, 5)

        sorted_tools = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:effective_top_k]

        selected_scores = {name: scores[name] for name in sorted_tools}
        selected_tools = [self.tool_map[name] for name in sorted_tools if name in self.tool_map]

        return selected_tools, selected_scores

    def get_all_scores(self, query: str) -> Dict[str, float]:
        if "bge" in self.model_name.lower():
            query_text = f"Represent this sentence for searching relevant tools: {query}"
        else:
            query_text = query

        query_embedding = self.embedder.encode(query_text, normalize_embeddings=True)

        scores = {}
        for name, emb in self.tool_embeddings.items():
            scores[name] = float(np.dot(query_embedding, emb))

        return scores

    def debug_query(self, query: str):
        if "bge" in self.model_name.lower():
            query_text = f"Represent this sentence for searching relevant tools: {query}"
        else:
            query_text = query

        query_embedding = self.embedder.encode(query_text, normalize_embeddings=True)

        is_compound = CompoundQueryDetector.is_compound_query(query)
        keyword_tools = CompoundQueryDetector.detect_required_tools(query)

        print(f"\nDebug: '{query}'")
        print(f"   Compound query: {is_compound}")
        print(f"   Keyword-detected tools: {keyword_tools}")
        print("-" * 50)

        scores = []
        for name, emb in self.tool_embeddings.items():
            score = float(np.dot(query_embedding, emb))
            boosted = name in keyword_tools
            scores.append((name, score, boosted))

        scores.sort(key=lambda x: x[1], reverse=True)

        for name, score, boosted in scores:
            bar = "=" * int(score * 30)
            boost_marker = " BOOSTED" if boosted else ""
            print(f"  {name:25} {score:.3f} {bar}{boost_marker}")

        return scores


__all__ = ['SmartToolRouter', 'ToolEmbeddingLoader', 'TOOL_DESCRIPTIONS', 'CompoundQueryDetector']
