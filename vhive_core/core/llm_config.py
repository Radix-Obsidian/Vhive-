"""
Ollama LLM bindings for Vhive via CrewAI + LiteLLM.
Base URL: http://localhost:11434 (Ollama default)
Coding tasks: qwen2.5-coder, temp 0.1
Creative tasks: llama3.1:8b, temp 0.7
"""

from crewai import LLM

OLLAMA_BASE_URL = "http://localhost:11434"

# Coding LLM - low temperature for deterministic code generation
CODING_LLM = LLM(
    model="ollama/qwen2.5-coder:latest",
    base_url=OLLAMA_BASE_URL,
    temperature=0.1,
)

# Creative LLM - higher temperature for marketing copy, outreach
CREATIVE_LLM = LLM(
    model="ollama/llama3.1:8b",
    base_url=OLLAMA_BASE_URL,
    temperature=0.7,
)


def check_ollama_connectivity() -> bool:
    """Verify local Ollama instance is reachable."""
    try:
        import requests
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False
