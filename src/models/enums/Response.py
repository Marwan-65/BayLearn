from enum import Enum
class Response_Signal(Enum):
    
    FILE_EXTENSION_ERROR = "File not supported"
    FILE_SIZE_ERROR = "File size exceeds the limit"
    FILE_UPLOAD_SUCCESS = "File uploaded successfully"
    FILE_UPLOAD_FAILURE = "File upload failed"
    FILE_VALIDATION_SUCCESS = "File validated successfully"
    