import json
import threading
import textwrap
import re
import warnings
import time  # Ensure time is imported
from mistralai import SDKError, Mistral
from key import MistraAIKey as api_key
from typing import Any, cast  # added import

warnings.filterwarnings("ignore")

class MistralInterface:
    def __init__(self):
        """
        Initialize the MistralInterface class.
        The class is responsible for managing sentiment analysis using a language model.
        """
        # Removed cache-related variables
        # Using a semaphore for thread-safe access to the LLM
        # Limiting the number of concurrent requests to 6, because
        # Mistral has a limit of 6 concurrent requests per API key
        self.llmSemaphore = threading.Semaphore(6)
        # Initialize the Mistral client
        self.genAI_Client = Mistral(api_key=api_key)

    def invokeLLM(self,
        _prompt: str,
        _format: str = "text",
        _temperature: float = 0.7,
        attempts: int = 5) -> tuple[str, bool]:
        """
        Invoke the LLM with the given prompt and data.
        Input:
        - prompt: The text prompt to send to the LLM.
        - format: The format to use for the response (e.g., "text", "json").
        - temperature: The temperature to use for sampling (0.0 - 1.0).
        - attempts: The number of attempts to make in case of failure.
        Return:
        - a tuple containing the LLM response and a boolean indicating
            if the invocation was successful.
        """
        response: str = ""
        success: bool = False
        _model: str = "mistral-large-latest"
#        _model: str = "mistral-small-latest"
        retry_counter: int = 0
        while retry_counter < attempts:
            try:
                with self.llmSemaphore:
                    # Cast the response_format dict to Any to satisfy the type checker
                    result = self.genAI_Client.chat.complete(
                        model=_model,
                        temperature=_temperature,
                        messages=[{"role": "user", "content": _prompt }],
                        response_format=cast(Any, {"type" : _format})
                    )
                # Safely extract content, supporting both SDK objects and plain dicts
                content = None
                try:
                    # Try object-style access first
                    choices = getattr(result, "choices", None)
                    if not choices and isinstance(result, dict):
                        # fallback to dict-style access
                        choices = result.get("choices")
                    if choices and len(choices) > 0:
                        first = choices[0]
                        message = getattr(first, "message", None) if not isinstance(first, dict) else first.get("message")
                        if message:
                            content = getattr(message, "content", None) if not isinstance(message, dict) else message.get("content")
                except Exception:
                    content = None

                if content:
                    response = content.strip()
                    success = True
                    break
                else:
                    # Treat missing content as transient failure and retry
                    retry_counter += 1
                    time.sleep(0.15 * retry_counter)
            except SDKError as e:
                retry_counter += 1
                time.sleep(0.15 * retry_counter)  # Exponential backoff
            except Exception as e:
                print(f"Unexpected error occurred: {e}")
                break
        return response, success
