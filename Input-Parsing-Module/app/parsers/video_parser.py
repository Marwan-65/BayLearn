import os
import uuid
import subprocess
import tempfile

from app.parsers.base_parser import BaseParser
from app.parsers.audio_parser import AudioParser, _get_whisper_model
from app.models.unified_content_schema import ParsedContent, Section, Chunk

# Reuse the same segment grouping constant as AudioParser for consistency
from app.parsers.audio_parser import SEGMENTS_PER_CHUNK


class VideoParser(BaseParser):
    """
    Parses video files into structured ParsedContent ready for RAG / LLM pipelines.

    Pipeline:
        preprocess  → extracts audio track from video to a temp WAV file via ffmpeg
        extract     → transcribes the WAV with Whisper (shared model with AudioParser)
        structure   → identical to AudioParser: groups segments into Chunks with
                      timestamp metadata, wrapped in a Section

    The temp WAV file is created in the system temp directory and deleted
    automatically after extraction, so no stray files are left next to uploads.
    """

    # ------------------------------------------------------------------ #
    # BaseParser interface                                                 #
    # ------------------------------------------------------------------ #

    def preprocess(self, file_path: str) -> str:
        """
        Extract the audio track from the video into a temporary WAV file.
        Stashes the video filename as the title (same pattern as AudioParser).
        """
        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Video file not found: {file_path}")

        # Build a clean title from the video filename
        raw_name = os.path.splitext(os.path.basename(file_path))[0]
        self._title = raw_name.replace("_", " ").replace("-", " ").title()

        # Write audio to a uniquely named temp file so parallel uploads never collide
        tmp_dir = tempfile.gettempdir()
        audio_path = os.path.join(tmp_dir, f"video_audio_{uuid.uuid4().hex}.wav")

        result = subprocess.run(
            [
                "ffmpeg",
                "-y",           # overwrite if file somehow exists
                "-i", file_path,
                "-vn",          # drop video stream
                "-acodec", "pcm_s16le",  # WAV-compatible codec
                "-ar", "16000", # 16 kHz — what Whisper expects
                "-ac", "1",     # mono
                audio_path,
            ],
            capture_output=True,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed to extract audio from video.\n"
                f"stderr: {result.stderr.decode(errors='replace')}"
            )

        # Stash so parse() can clean up after extraction
        self._tmp_audio_path = audio_path
        return audio_path

    def extract(self, audio_path: str) -> dict:
        """
        Transcribe the extracted audio with Whisper.
        Cleans up the temp WAV file immediately after transcription.
        """
        try:
            model = _get_whisper_model()
            result = model.transcribe(audio_path)
        finally:
            # Always delete the temp file, even if transcription fails
            if os.path.exists(audio_path):
                os.remove(audio_path)

        return result

    def structure(self, whisper_result: dict) -> ParsedContent:
        """
        Identical logic to AudioParser.structure — groups Whisper segments
        into paragraph-sized Chunks with timestamp metadata.
        source_type is set to 'video' to distinguish from pure audio uploads.
        """
        segments = whisper_result.get("segments", [])
        full_text = whisper_result.get("text", "").strip()
        detected_language = whisper_result.get("language", "unknown")

        chunks: list[Chunk] = []
        chunk_index = 0

        for group_start in range(0, max(len(segments), 1), SEGMENTS_PER_CHUNK):
            group = segments[group_start: group_start + SEGMENTS_PER_CHUNK]

            if group:
                group_text = " ".join(seg.get("text", "").strip() for seg in group).strip()
                start_time = group[0].get("start", 0.0)
                end_time = group[-1].get("end", 0.0)
            else:
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

        title = getattr(self, "_title", "Video Transcript")
        section = Section(
            id=str(uuid.uuid4()),
            heading=title,
            page=None,
            chunks=chunks,
        )

        return ParsedContent(
            source_type="video",
            title=title,
            sections=[section],
            total_chunks=len(chunks),
        )
