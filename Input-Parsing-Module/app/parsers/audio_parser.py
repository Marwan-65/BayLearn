import uuid
from app.parsers.base_parser import BaseParser
from app.models.unified_content_schema import ParsedContent, Section, Chunk

# Whisper model is loaded lazily to avoid slow startup and allow
# the model size to be configured at runtime.
_whisper_model = None
WHISPER_MODEL_SIZE = "base"  # Options: tiny, base, small, medium, large


def _get_whisper_model():
    """Load and cache the Whisper model on first use."""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _whisper_model


# Number of Whisper segments to group into a single RAG chunk.
# Whisper segments are roughly sentence-length, so 5 ≈ a short paragraph.
SEGMENTS_PER_CHUNK = 5


class AudioParser(BaseParser):
    """
    Parses audio files into structured ParsedContent ready for RAG / LLM pipelines.

    Pipeline:
        preprocess  → validates and returns the file path
        extract     → transcribes with OpenAI Whisper (free, local)
                      returns the full result dict (text + segments with timestamps)
        structure   → groups Whisper segments into Chunks with timestamp metadata,
                      wrapped in Sections that mirror the rest of the parser family
    """

    # ------------------------------------------------------------------ #
    # BaseParser interface                                                 #
    # ------------------------------------------------------------------ #

    def preprocess(self, file_path: str) -> str:
        """Validate the file exists, stash the filename, and return the path."""
        import os
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        # Strip extension and underscores/dashes for a clean title
        # e.g. "einstein_theory_of_relativity.mp3" → "Einstein Theory Of Relativity"
        raw_name = os.path.splitext(os.path.basename(file_path))[0]
        self._title = raw_name.replace("_", " ").replace("-", " ").title()
        return file_path

    def extract(self, file_path: str) -> dict:
        """
        Transcribe the audio with Whisper.

        Returns the full Whisper result dict so that `structure` can access
        both the plain text and the time-stamped segments.
        """
        model = _get_whisper_model()
        result = model.transcribe(file_path)
        return result

    def structure(self, whisper_result: dict) -> ParsedContent:
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

        # ---- Build chunks by grouping consecutive segments ---- #
        chunks: list[Chunk] = []
        chunk_index = 0

        for group_start in range(0, max(len(segments), 1), SEGMENTS_PER_CHUNK):
            group = segments[group_start: group_start + SEGMENTS_PER_CHUNK]

            if group:
                group_text = " ".join(seg.get("text", "").strip() for seg in group).strip()
                start_time = group[0].get("start", 0.0)
                end_time = group[-1].get("end", 0.0)
            else:
                # No segments returned (e.g. very short / silent audio) —
                # fall back to the plain text so we still produce a chunk.
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

        # Edge-case: Whisper returned text but no segments list
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

        # ---- Wrap chunks in a single Section ---- #
        title = getattr(self, "_title", "Audio Transcript")
        section = Section(
            id=str(uuid.uuid4()),
            heading=title,
            page=None,          # Audio has no pages; kept None for schema compatibility
            chunks=chunks,
        )

        return ParsedContent(
            source_type="audio",
            title=title,
            sections=[section],
            total_chunks=len(chunks),
        )