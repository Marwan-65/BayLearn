from app.parsers.pdf_parser import PDFParser
#from app.parsers.handwritten_parser import HandwrittenParser
#from app.parsers.audio_parser import AudioParser
#from app.parsers.video_parser import VideoParser

class ParserFactory:

    @staticmethod
    def get_parser(file_type):

        if file_type == "pdf":
            return PDFParser()

        elif file_type == "image":
            return HandwrittenParser()

        elif file_type == "audio":
            return AudioParser()

        elif file_type == "video":
            return VideoParser()

        else:
            raise ValueError("Unsupported file type")
