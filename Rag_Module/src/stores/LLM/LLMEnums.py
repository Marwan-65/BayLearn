from enum import Enum


class LLMEnum(str, Enum):
    LLAMA_2 = "llama2"
    MISTRAL = "mistral"


class LLMBackendEnum(str, Enum):
    LOCAL = "LOCAL"
    GROQ = "GROQ"


class ChatRoleEnum(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class DocumentTypeEnum(str, Enum):
    DOCUMENT = "document"
    QUERY = "query"