"""
OpenAI-compatible API client wrapper. Provides interface for LLM calls used by the multi-agent system.
"""

from openai import OpenAI
from typing import Optional


class OpenAIClientWrapper:

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1",
                 model: str = "gpt-4"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def chat_completion(self, messages: list, tools: Optional[list] = None,
                       tool_choice: Optional[str] = None, timeout: int = 90,
                       model: Optional[str] = None):
        model_to_use = model or self.model

        kwargs = {
            "model": model_to_use,
            "messages": messages,
            "timeout": timeout
        }

        if tools:
            kwargs["tools"] = tools

        if tool_choice:
            kwargs["tool_choice"] = tool_choice

        return self.client.chat.completions.create(**kwargs)

    def get_client(self):
        return self.client


_client_instance: Optional[OpenAIClientWrapper] = None


def initialize_client(api_key: str, base_url: str = "https://api.openai.com/v1",
                     model: str = "gpt-4") -> OpenAIClientWrapper:
    global _client_instance
    _client_instance = OpenAIClientWrapper(api_key, base_url, model)
    return _client_instance


def get_client() -> Optional[OpenAIClientWrapper]:
    return _client_instance


if __name__ == "__main__":
    import os

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        print("Set OPENAI_API_KEY environment variable")
        exit(1)

    client = OpenAIClientWrapper(api_key)

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello! What's the weather like?"}
    ]

    response = client.chat_completion(messages)
    print(response.choices[0].message.content)
