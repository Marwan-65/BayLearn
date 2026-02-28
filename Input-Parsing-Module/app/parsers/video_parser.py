import subprocess
from app.parsers.base_parser import BaseParser
from app.parsers.audio_parser import AudioParser

class VideoParser(BaseParser):

    def preprocess(self, file_path):
        audio_path = file_path + ".wav"
        subprocess.call([
            "ffmpeg",
            "-i", file_path,
            "-q:a", "0",
            "-map", "a",
            audio_path
        ])
        return audio_path

    def extract(self, audio_path):
        audio_parser = AudioParser()
        return audio_parser.extract(audio_path)

    def structure(self, raw_text):
        return {
            "source_type": "video",
            "title": "Video Transcript",
            "sections": [{
                "heading": "Transcript",
                "content": raw_text,
                "page": None
            }]
        }
