from abc import ABC, abstractmethod

class EmbedBackend(ABC):
    @abstractmethod
    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        """ embed a group of texts.
            input_type: document or query"""

def get_backend() -> "EmbedBackend":
    from sentismetric.rag.voyage_embed import VoyageEmbed
    return VoyageEmbed()