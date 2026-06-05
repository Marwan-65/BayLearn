import uuid
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent, Section, Chunk

_whisper_model = None
WHISPER_MODEL_SIZE = "base"  


def _get_whisper_model():
    """Load and cache the Whisper model on first use."""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _whisper_model


# Number of Whisper segments to put into a single chunk for rag module chuncking
SEGMENTS_PER_CHUNK = 5


class AudioParser(BaseParser):
    """
    Parses audio files into structured ParsedContent ready for RAG / LLM pipelines.

    Pipeline:
        preprocess  ->validates and returns the file path
        extract     ->transcribes with OpenAI Whisper (free, local)
                      returns the full result dict (text + segments with timestamps)
        structure   ->groups Whisper segments into Chunks with timestamp metadata,
                      wrapped in Sections that mirror the rest of the parser family
    """

    def preprocess(self, file_path: str) -> str:
        """Validate the file exists, stash the filename, and return the path."""
        import os
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        # remove extension and underscores/dashes for a clean title
        # tested example "einstein_theory_of_relativity.mp3" ->"Einstein Theory Of Relativity"
        raw_name = os.path.splitext(os.path.basename(file_path))[0]
        self._title = raw_name.replace("_", " ").replace("-", " ").title()
        return file_path

    def extract(self , file_path: str) -> dict:
        """
        Transcribe the audio with Whisper.

        Returns the full Whisper result dict so that `structure` can access
        both the plain text and the time-stamped segments.
        """
        model =   _get_whisper_model()
        res = model.transcribe(file_path)
        return res

    def structure(self ,  whisper_result: dict) -> ParsedContent:
        """
        Convert a Whisper result dict into a ParsedContent with Sections and Chunks.

        Each chunk groups SEGMENTS_PER_CHUNK consecutive Whisper segments so
        that the resulting chunks are meaningful paragraph-sized units for RAG.
        Timestamp metadata (start/end seconds) is stored on every chunk so
        downstream modules can link answers back to the audio position.
        """
        segments = whisper_result.get("segments", [])
        full_text = whisper_result.get("text", "").strip()
        detected_language = whisper_result.get("language", "unknown")

        # Build chunks by grouping consecutive segments tgthr
        chunks: list[Chunk] = []
        chunk_index = 0

        for group_start in range(0, max(len(segments), 1), SEGMENTS_PER_CHUNK):
            group = segments[group_start: group_start + SEGMENTS_PER_CHUNK]

            if group:
                group_text = " ".join(seg.get("text", "").strip() for seg in group).strip()
                start_time = group[0].get("start", 0.0)
                end_time = group[-1].get("end", 0.0)
            else:
                # No segments returned try using the full text as a single chunk
                group_text = full_text
                start_time = 0.0
                end_time = 0.0

            if not group_text:
                continue

            chunks.append(Chunk(
                id=str(uuid.uuid4()),
                content=group_text,
                chunk_index=chunk_index,
                metadata={
                    "chunk_type": "transcript_segment",
                    "start_seconds": round(start_time, 2),
                    "end_seconds": round(end_time, 2),
                    "language": detected_language,
                },
            ))
            chunk_index += 1

        # Edge case whisper returned text but no segments list just one chunck with full txt
        if not chunks and full_text:
            chunks.append(Chunk(
                id=str(uuid.uuid4()),
                content=full_text,
                chunk_index=0,
                metadata={
                    "chunk_type": "transcript_full",
                    "language": detected_language,
                },
            ))

        # pu chuncks in one sec
        title = getattr(self, "_title", "Audio Transcript")
        section = Section(
            id=str(uuid.uuid4()),
            heading=title,
            page=None,          # 7atenha for compatability 
            chunks=chunks,
        )

        return ParsedContent(
            source_type="audio",
            title=title,
            sections=[section],
            total_chunks=len(chunks),
        )
