_whisper_model = None
WHISPER_MODEL_SIZE = "base"  


def _get_whisper_model():
    """Load and cache the Whisper model on first use."""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        _whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
    return _whisper_model