from qdrant_client import models, QdrantClient
from ..VectorDBInterface import VectorDBInterface
from VectorDBEnum import DistanceMethodEnum
import logging
from typing import List

class QdrantDB(VectorDBInterface):
    def __init__(self, db_path: str, distance_method: str):
        self.client = None
        self.db_path = db_path
        self.distance_method = None

        if distance_method == DistanceMethodEnum.COSINE.value:
            self.distance_method = models.Distance.COSINE
        elif distance_method == DistanceMethodEnum.DOT.value:
            self.distance_method = models.Distance.DOT
        else:
            raise ValueError(f"Unsupported distance method: {distance_method}")

        self.logger = logging.getLogger(__name__)

    def connect(self):
        self.client = QdrantClient(path=self.db_path)

    def disconnect(self):
        self.client = None

    def is_collection_existed(self, collection_name: str) -> bool:
        if self.client is None:
            self.logger.error("Qdrant client is not connected.")
            return False
        return self.client.collection_exists(collection_name=collection_name)

    def list_all_collections(self) -> List:
        if self.client is None:
            self.logger.error("Qdrant client is not connected.")
            return []
        return self.client.get_collections()
    
    def delete_collection(self, collection_name: str):
    #Delete the specified collection if it exists.
        if self.is_collection_existed(collection_name):
            return self.client.delete_collection(collection_name=collection_name)
        return False

    def create_collection(self,
                        collection_name: str,
                        embedding_size: int,
                        do_reset: bool = False):
        """
        Create a collection with the given embedding size and distance metric.

        If do_reset is True, delete the collection first (if it exists), then recreate.
        """
        if do_reset:
            _ = self.delete_collection(collection_name=collection_name)

        if not self.is_collection_existed(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=embedding_size,
                    distance=self.distance_method
                )
            )
            return True

        return False
    def insert_one(self, collection_name: str, text: str, vector: list, metadata: dict = None,record_id: str = None) -> bool:
        """
        Insert a single record into the specified collection.
        Returns True on success, False on failure.
        """
        if not self.is_collection_existed(collection_name):
            self.logger.error(
                f"Can not insert new record to non-existed collection: {collection_name}"
            )
            return False

        self.client.upload_records(
            collection_name=collection_name,
            records=[
                models.Record(
                    vector=vector,
                    payload={
                        "text": text,
                        "metadata": metadata
                    }
                )
            ]
        )

        return True
    def insert_many(self,collection_name: str,texts: list,vectors: list,metadata: list = None,record_ids: list = None,batch_size: int = 100,) -> bool:
        """
        Insert multiple documents in batches into a collection.

        - texts: list of text strings
        - vectors: corresponding list of vectors
        - metadata: optional per-item metadata list
        - batch_size: size of each batch
        - record_ids: optional list of record IDs (if provided, must align with texts)
        """
        if len(texts) == 0:
            self.logger.info("No texts provided to insert.")
            return True

        if record_ids is None:
            record_ids = [None] * len(texts)

        if metadata is None:
            metadata = [None] * len(texts)

        if not (len(texts) == len(vectors) == len(metadata) == len(record_ids)):
            self.logger.error("Length mismatch among texts, vectors, metadata, and record_ids.")
            return False

        try:
            for i in range(0, len(texts), batch_size):
                batch_end = min(i + batch_size, len(texts))
                batch_texts = texts[i:batch_end]
                batch_vectors = vectors[i:batch_end]
                batch_metadatas = metadata[i:batch_end]
                batch_records = [
                    models.Record(
                        vector=batch_vectors[x],
                        payload={
                            "text": batch_texts[x],
                            "metadata": batch_metadatas[x]
                        }
                    )
                    for x in range(len(batch_texts))
                ]

                self.client.upload_records(
                    collection_name=collection_name,
                    records=batch_records
                )

            return True
        except Exception as e:
            self.logger.error(f"Error while inserting batch: {e}")
            return False
    def search_by_vector(self, collection_name: str, query_vector: list, top_k: int = 5) -> List[dict]:
        return self.client.search(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k,
        )