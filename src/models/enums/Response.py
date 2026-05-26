from enum import Enum


class Response_Signal(Enum):

    # -----------------------------
    # Project
    # -----------------------------
    PROJECT_NOT_FOUND_ERROR = "Project not found"

    # -----------------------------
    # Vector Indexing
    # -----------------------------
    INSERT_INTO_VECTORDB_SUCCESS = "Project indexed successfully"
    INSERT_INTO_VECTORDB_ERROR = "Failed to index project into vector database"

    # -----------------------------
    # Semantic Search
    # -----------------------------
    SEARCH_VECTORDB_COLLECTION_SUCCESS = "Search completed successfully"
    SEARCH_VECTORDB_COLLECTION_Failure = "Search failed or no results found"

    # -----------------------------
    # Vector DB Info
    # -----------------------------
    GET_VECTORDB_COLLECTION_INFO_SUCCESS = "Collection info retrieved successfully"

    # -----------------------------
    # RAG - Augmented Answers
    # -----------------------------
    AUGMENTED_ANSWER_SUCCESS = "Augmented answer generated successfully"
    AUGMENTED_ANSWER_FAILURE = "Failed to generate augmented answer"