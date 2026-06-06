# we modify things returened by groq judge to make it suitable for our project 
from langchain_groq import ChatGroq
class GroqChatFixed(ChatGroq):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.async_client = PatchedAsyncCompletions(
            self.async_client
        )
        self.client = PatchedSyncCompletions(
            self.client
        )
    def _create_chat_result(self, response, *args, **kwargs):
        return super()._create_chat_result(response, *args, **kwargs)
        

    def _get_request_payload(self, input_messages, stop=None, **kwargs):
        payload = super()._get_request_payload(input_messages, stop, **kwargs)
        messages = payload.get("messages", [])
        has_system = any(m.get("role") == "system" for m in messages)
        if not has_system:
            json_system = {
                "role": "system",
                "content": "You must respond with valid JSON only. No explanations, no markdown, no extra text. Return only the JSON object as specified"
            }
            payload["messages"] = [json_system] + messages 
        return payload


# wrapper to remove things added by langchain but groq do not support so cause failure
class PatchedAsyncCompletions:
    def __init__(self, original_client):
        self._original = original_client

    async def create(self, **kwargs):
        kwargs.pop("reasoning_format", None)
        kwargs.pop("reasoning", None)
        # we need only 1 responce
        if kwargs.get("n", 1) > 1:
            kwargs["n"] = 1
        return await self._original.create(**kwargs)


class PatchedSyncCompletions:
    def __init__(self, original_client):
        self._original = original_client

    def create(self, **kwargs):
        kwargs.pop("reasoning_format", None)
        kwargs.pop("reasoning", None)
        if kwargs.get("n", 1) > 1:
            kwargs["n"] = 1
        return self._original.create(**kwargs)