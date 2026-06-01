from app.parsers.pdf_parser import PDFParser

class ParserFactory:

    @staticmethod
    def get_parser(file_type):

        if file_type == "pdf":
            return PDFParser()

        elif file_type == "image":
            from app.parsers.image_parser import ImageParser
            return ImageParser()

        elif file_type == "audio":
            from app.parsers.audio_parser import AudioParser
            return AudioParser()

        elif file_type == "video":
            from app.parsers.video_parser import VideoParser
            return VideoParser()

        else:
            raise ValueError("Unsupported file type")
