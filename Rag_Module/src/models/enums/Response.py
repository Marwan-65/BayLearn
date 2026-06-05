from enum import Enum
class Response_Signal(Enum):
    PROJECT_NOT_FOUND_ERROR = "Project not found"
    INSERT_INTO_VECTORDB_SUCCESS = "Project indexed successfully"
    INSERT_INTO_VECTORDB_ERROR = "Failed to index project into vector database"
    SEARCH_VECTORDB_COLLECTION_SUCCESS = "Search completed successfully"
    SEARCH_VECTORDB_COLLECTION_Failure = "Search failed or no results found"
    GET_VECTORDB_COLLECTION_INFO_SUCCESS = "Collection info retrieved successfully"
    AUGMENTED_ANSWER_SUCCESS = "Augmented answer generated successfully"
    AUGMENTED_ANSWER_FAILURE = "Failed to generate augmented answer"