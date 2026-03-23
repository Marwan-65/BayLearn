from langchain_groq import ChatGroq
from groq import AsyncGroq, Groq


class GroqChatFixed(ChatGroq):
    """
    Patches langchain_groq to remove unsupported parameters
    at the actual HTTP request level, not at the kwargs level.
    
    WHY this approach?
    langchain_groq injects 'reasoning_format' directly into the
    API call parameters based on the model name, AFTER all our
    kwargs filtering. The only way to stop it is to override
    the actual client that makes the HTTP call.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Replace the async client with a patched version
        # that strips unsupported params before every request
        self.async_client = PatchedAsyncCompletions(
            self.async_client
        )
        self.client = PatchedSyncCompletions(
            self.client
        )
    def _create_chat_result(self, response, generation_info=None):
        chat_result = super()._create_chat_result(response)
        if chat_result.generations:
            chat_result.generations[0].generation_info = generation_info
        return chat_result
        

    def _get_request_payload(self, input_messages, stop=None, **kwargs):
        """Inject JSON system message into every RAGAS request."""
        payload = super()._get_request_payload(input_messages, stop, **kwargs)
        
        messages = payload.get("messages", [])
        
        # Check if there's already a system message
        has_system = any(m.get("role") == "system" for m in messages)
        
        if not has_system:
            # Inject strict JSON instruction as system message
            json_system = {
                "role": "system",
                "content": "You must respond with valid JSON only. No explanations, no markdown, no extra text. Return only the JSON object as specified."
            }
            payload["messages"] = [json_system] + messages
        
        return payload

class PatchedAsyncCompletions:
    """Wraps Groq's async completions to strip unsupported params."""

    def __init__(self, original_client):
        self._original = original_client

    async def create(self, **kwargs):
        # Strip every parameter Groq doesn't support
        kwargs.pop("reasoning_format", None)
        kwargs.pop("reasoning", None)
        if kwargs.get("n", 1) > 1:
            kwargs["n"] = 1
        return await self._original.create(**kwargs)


class PatchedSyncCompletions:
    """Wraps Groq's sync completions to strip unsupported params."""

    def __init__(self, original_client):
        self._original = original_client

    def create(self, **kwargs):
        kwargs.pop("reasoning_format", None)
        kwargs.pop("reasoning", None)
        if kwargs.get("n", 1) > 1:
            kwargs["n"] = 1
        return self._original.create(**kwargs)