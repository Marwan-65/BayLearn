from qdrant_client import models, QdrantClient
from ..VectorDBInterface import VectorDBInterface
from ..DistanceMethodEnum import DistanceMethodEnum
import logging
from typing import List
import uuid


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

    def is_collection_exists(self, collection_name: str) -> bool:
        if self.client is None:
            self.logger.error("Qdrant client is not connected.")
            return False
        return self.client.collection_exists(collection_name=collection_name)

    def list_all_collections(self) -> List:
        if self.client is None:
            return []
        return self.client.get_collections()

    def delete_collection(self, collection_name: str):
        if self.is_collection_exists(collection_name):
            return self.client.delete_collection(collection_name=collection_name)
        return False

    def create_collection(self, collection_name: str,
                          embedding_size: int, do_reset: bool = False):
        if do_reset:
            self.delete_collection(collection_name=collection_name)

        if not self.is_collection_exists(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=embedding_size,
                    distance=self.distance_method
                )
            )
            return True
        return False

    def insert_one(self, collection_name: str, text: str, vector: list,
                   metadata: dict = None, record_id: str = None) -> bool:
        if not self.is_collection_exists(collection_name):
            self.logger.error(f"Collection {collection_name} does not exist.")
            return False
        try:
            point_id = int(record_id) if str(record_id).isdigit() else str(uuid.uuid4())
            self.client.upsert(
                collection_name=collection_name,
                points=[
                    models.PointStruct(id=point_id,vector=vector,
                        payload={"text": text, **(metadata or {})})])
            return True
        except Exception as e:
            self.logger.error(f"Error inserting record: {e}")
            return False

    def insert_many(self, collection_name: str, texts: list, vectors: list,
                    metadata: list = None, record_ids: list = None,
                    batch_size: int = 100) -> bool:
        if not texts:
            return True
        if not self.is_collection_exists(collection_name):
            self.logger.error(f"Collection {collection_name} does not exist.")
            return False
        if record_ids is None:
            record_ids = list(range(len(texts)))
        if metadata is None:
            metadata = [{}] * len(texts)
        if not (len(texts) == len(vectors) == len(metadata) == len(record_ids)):
            self.logger.error("Length mismatch among texts, vectors, metadata, record_ids.")
            return False
        try:
            for i in range(0, len(texts), batch_size):
                batch_end = min(i + batch_size, len(texts))
                batch_texts = texts[i:batch_end]
                batch_vectors = vectors[i:batch_end]
                batch_metadatas = metadata[i:batch_end]
                batch_record_ids = record_ids[i:batch_end]
                points = []
                for x in range(len(batch_texts)):
                    raw_id = batch_record_ids[x]
                    point_id = int(raw_id) if str(raw_id).isdigit() \
                            else str(raw_id)
                    points.append(models.PointStruct(id=point_id,vector=batch_vectors[x],
                            payload={"text": batch_texts[x],**(batch_metadatas[x] or {})}))

                self.logger.info(f"inserting batch {i//batch_size + 1}: "
                                f"{len(points)} points into {collection_name}")
                self.client.upsert(collection_name=collection_name,
                    points=points)
            self.logger.info(f"successfully inserted {len(texts)} records.")
            return True

        except Exception as e:
            self.logger.error(f"error while inserting batch: {e}")
            return False

    def search_by_vector(self, collection_name: str, query_vector: list,
                         limit: int = 5) -> list:
        if self.client is None:
            self.logger.error("Qdrant client is not connected.")
            return []
        if not self.is_collection_exists(collection_name):
            self.logger.error(f"Collection {collection_name} does not exist.")
            return []
        try:
            search_results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
            )
            results = []
            for scored_point in search_results.points:
                results.append({
                    "id": scored_point.id,
                    "score": scored_point.score,
                    "payload": scored_point.payload
                })
            return results
        except Exception as e:
            self.logger.error(f"Error during search: {e}")
            return []

    def get_collection_info(self, collection_name: str) -> dict:
        if self.client is None:
            return {}
        if not self.is_collection_exists(collection_name):
            return {}
        return self.client.get_collection(collection_name=collection_name)

    def scroll_all(self, collection_name: str) -> list:
        if self.client is None or not self.is_collection_exists(collection_name):
            return []
        results = []
        offset = None
        while True:
            points, next_offset = self.client.scroll(
                collection_name=collection_name,
                offset=offset,
                limit=200,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                results.append({"id": p.id, "payload": p.payload or {}})
            if next_offset is None:
                break
            offset = next_offset
        return results