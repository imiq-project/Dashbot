"""
Configuration module for the Magdeburg Campus Assistant application.
Loads environment variables and provides configuration constants for all external services
(FIWARE, OpenAI, Neo4j, OpenRouteService, TomTom) and application settings.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)


def _parse_bool(value: str) -> bool:
    """Parse boolean from environment variable string, case-insensitive."""
    return value.strip().lower() in ("true", "1", "yes")


def _parse_int(value: str, default: int) -> int:
    """Safely parse int from environment variable string."""
    try:
        return int(value)
    except (ValueError, TypeError):
        print(f"WARNING: Invalid integer value '{value}', using default {default}")
        return default


def _parse_float(value: str, default: float) -> float:
    """Safely parse float from environment variable string."""
    try:
        return float(value)
    except (ValueError, TypeError):
        print(f"WARNING: Invalid float value '{value}', using default {default}")
        return default

FIWARE_BASE_URL = os.getenv("FIWARE_BASE_URL", "https://imiq-public.et.uni-magdeburg.de/api/orion")
FIWARE_API_KEY = os.getenv("FIWARE_API_KEY", "")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://chat-ai.academiccloud.de/v1")

NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

ORS_API_KEY = os.getenv("ORS_API_KEY", "")
ORS_BASE_URL = os.getenv("ORS_BASE_URL", "https://api.openrouteservice.org")

TOMTOM_API_KEY = os.getenv("TOMTOM_API_KEY", "")
TOMTOM_TIMEOUT = _parse_int(os.getenv("TOMTOM_TIMEOUT", "10"), 10)

MODEL = os.getenv("MODEL", "qwen3-30b-a3b-instruct-2507")

KNOWLEDGE_DIR = os.getenv("KNOWLEDGE_DIR", "data/knowledge")

MAX_CONVERSATION_HISTORY = _parse_int(os.getenv("MAX_CONVERSATION_HISTORY", "6"), 6)
MAX_TOOL_ITERATIONS = _parse_int(os.getenv("MAX_TOOL_ITERATIONS", "5"), 5)

HTTP_TIMEOUT = _parse_int(os.getenv("HTTP_TIMEOUT", "10"), 10)

MAGDEBURG_LAT = _parse_float(os.getenv("MAGDEBURG_LAT", "52.1205"), 52.1205)
MAGDEBURG_LON = _parse_float(os.getenv("MAGDEBURG_LON", "11.6276"), 11.6276)


ENABLE_AGENTIC_MODE = _parse_bool(os.getenv("ENABLE_AGENTIC_MODE", "false"))

ROUTER_AGENT_MODEL = os.getenv("ROUTER_AGENT_MODEL", "qwen3-30b-a3b-instruct-2507")
NEO4J_AGENT_MODEL = os.getenv("NEO4J_AGENT_MODEL", "qwen3-30b-a3b-instruct-2507")
FIWARE_AGENT_MODEL = os.getenv("FIWARE_AGENT_MODEL", "qwen3-30b-a3b-instruct-2507")
SYNTHESIZER_AGENT_MODEL = os.getenv("SYNTHESIZER_AGENT_MODEL", "qwen3-30b-a3b-instruct-2507")

ROUTER_AGENT_TIMEOUT = _parse_int(os.getenv("ROUTER_AGENT_TIMEOUT", "5"), 5)
NEO4J_AGENT_TIMEOUT = _parse_int(os.getenv("NEO4J_AGENT_TIMEOUT", "10"), 10)
FIWARE_AGENT_TIMEOUT = _parse_int(os.getenv("FIWARE_AGENT_TIMEOUT", "8"), 8)
SYNTHESIZER_AGENT_TIMEOUT = _parse_int(os.getenv("SYNTHESIZER_AGENT_TIMEOUT", "15"), 15)

AGENT_MAX_RETRIES = _parse_int(os.getenv("AGENT_MAX_RETRIES", "2"), 2)
AGENT_RETRY_DELAY = _parse_float(os.getenv("AGENT_RETRY_DELAY", "0.5"), 0.5)

ROUTER_MIN_CONFIDENCE = _parse_float(os.getenv("ROUTER_MIN_CONFIDENCE", "0.7"), 0.7)

ROUTER_AGENT_TEMPERATURE = _parse_float(os.getenv("ROUTER_AGENT_TEMPERATURE", "0.1"), 0.1)
NEO4J_AGENT_TEMPERATURE = _parse_float(os.getenv("NEO4J_AGENT_TEMPERATURE", "0.0"), 0.0)
FIWARE_AGENT_TEMPERATURE = _parse_float(os.getenv("FIWARE_AGENT_TEMPERATURE", "0.1"), 0.1)
SYNTHESIZER_AGENT_TEMPERATURE = _parse_float(os.getenv("SYNTHESIZER_AGENT_TEMPERATURE", "0.3"), 0.3)

ROUTER_AGENT_MAX_TOKENS = _parse_int(os.getenv("ROUTER_AGENT_MAX_TOKENS", "500"), 500)
NEO4J_AGENT_MAX_TOKENS = _parse_int(os.getenv("NEO4J_AGENT_MAX_TOKENS", "1000"), 1000)
FIWARE_AGENT_MAX_TOKENS = _parse_int(os.getenv("FIWARE_AGENT_MAX_TOKENS", "800"), 800)
SYNTHESIZER_AGENT_MAX_TOKENS = _parse_int(os.getenv("SYNTHESIZER_AGENT_MAX_TOKENS", "2000"), 2000)

AGENT_PARALLEL_EXECUTION = _parse_bool(os.getenv("AGENT_PARALLEL_EXECUTION", "true"))

AGENT_VERBOSE_LOGGING = _parse_bool(os.getenv("AGENT_VERBOSE_LOGGING", "false"))
AGENT_LOG_PROMPTS = _parse_bool(os.getenv("AGENT_LOG_PROMPTS", "false"))

def validate_config():
    required_vars = {
        "FIWARE_API_KEY": FIWARE_API_KEY,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "NEO4J_PASSWORD": NEO4J_PASSWORD,
        "ORS_API_KEY": ORS_API_KEY,
        "TOMTOM_API_KEY": TOMTOM_API_KEY,
    }

    missing = [key for key, value in required_vars.items() if not value]

    if missing:
        print("WARNING: Missing required environment variables:")
        for var in missing:
            print(f"   - {var}")
        print("\nCreate a .env file with these variables or set them in your environment.")
        print("   See .env.example for a template.\n")
        return False

    return True


if __name__ != "__main__":
    validate_config()


if __name__ == "__main__":
    print("=" * 60)
    print("Configuration Settings")
    print("=" * 60)

    print("\nFIWARE:")
    print(f"   Base URL: {FIWARE_BASE_URL}")
    print(f"   API Key: {'Set' if FIWARE_API_KEY else 'Missing'}")

    print("\nOpenAI:")
    print(f"   Base URL: {OPENAI_BASE_URL}")
    print(f"   API Key: {'Set' if OPENAI_API_KEY else 'Missing'}")
    print(f"   Model: {MODEL}")

    print("\nNeo4j:")
    print(f"   URI: {NEO4J_URI}")
    print(f"   Username: {NEO4J_USERNAME}")
    print(f"   Password: {'Set' if NEO4J_PASSWORD else 'Missing'}")
    print(f"   Database: {NEO4J_DATABASE}")

    print("\nOpenRouteService:")
    print(f"   Base URL: {ORS_BASE_URL}")
    print(f"   API Key: {'Set' if ORS_API_KEY else 'Missing'}")

    print("\nTomTom:")
    print(f"   API Key: {'Set' if TOMTOM_API_KEY else 'Missing'}")
    print(f"   Timeout: {TOMTOM_TIMEOUT}s")

    print("\nApplication:")
    print(f"   Knowledge Dir: {KNOWLEDGE_DIR}")
    print(f"   Max History: {MAX_CONVERSATION_HISTORY}")
    print(f"   Max Iterations: {MAX_TOOL_ITERATIONS}")
    print(f"   HTTP Timeout: {HTTP_TIMEOUT}s")

    print("\nMagdeburg:")
    print(f"   Latitude: {MAGDEBURG_LAT}")
    print(f"   Longitude: {MAGDEBURG_LON}")

    print("\nMulti-Agent System:")
    print(f"   Agentic Mode: {'Enabled' if ENABLE_AGENTIC_MODE else 'Disabled'}")
    if ENABLE_AGENTIC_MODE:
        print(f"   Router Model: {ROUTER_AGENT_MODEL}")
        print(f"   Neo4j Model: {NEO4J_AGENT_MODEL}")
        print(f"   FIWARE Model: {FIWARE_AGENT_MODEL}")
        print(f"   Synthesizer Model: {SYNTHESIZER_AGENT_MODEL}")
        print(f"   Parallel Execution: {'Yes' if AGENT_PARALLEL_EXECUTION else 'No'}")
        print(f"   Verbose Logging: {'Yes' if AGENT_VERBOSE_LOGGING else 'No'}")

    print("\n" + "=" * 60)

    print("\nValidation:")
    if validate_config():
        print("All required environment variables are set!")
    else:
        print("Some required environment variables are missing.")
