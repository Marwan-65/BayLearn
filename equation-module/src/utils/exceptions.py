class MathEngineError(Exception):
    """Base exception for math engine errors."""

class InvalidOperationError(MathEngineError):
    """Raised when a requested operation is not supported."""

class EquationParsingError(MathEngineError):
    """Raised when equation parsing fails."""


class MatrixOperationError(MathEngineError):
    """Raised when matrix operation execution fails."""

class SymbolicComputationError(MathEngineError):
    """Raised when symbolic computation fails."""

class FormattingError(MathEngineError):
    """Raised when formatting output fails."""
    
class ValidationError(MathEngineError):
    """Raised when request validation fails."""
