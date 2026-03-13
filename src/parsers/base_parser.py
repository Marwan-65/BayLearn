from abc import ABC, abstractmethod

class BaseParser(ABC):

    @abstractmethod
    def preprocess(self, file_path):
        pass

    @abstractmethod
    def extract(self, processed_input):
        pass

    @abstractmethod
    def structure(self, raw_text):
        pass

    def parse(self, file_path):
        processed = self.preprocess(file_path)
        raw_text = self.extract(processed)
        structured = self.structure(raw_text)
        return structured