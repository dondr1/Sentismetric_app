from abc import ABC, abstractmethod

class VisionBackend(ABC):
    @abstractmethod
    def page_to_markdown(self, png_bytes: bytes) -> str:
        """One	page	image	in	→	structured	markdown out	(tables	as pipes)."""
    def get_backend() -> "VisionBackend":
        from sentismetric.extract.claude_vision import ClaudeVision
        return ClaudeVision()