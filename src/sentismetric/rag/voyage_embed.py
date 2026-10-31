import voyageai

from sentismetric.config import settings
from sentismetric.rag.embed_backend import EmbedBackend

class VoyageEmbed(EmbedBackend):
    def __init__(self) -> None:
        self.client = voyageai.Client(api_key=settings.voyage_api_key)
    def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        result= self.client.embed(texts, model="voyage-4", input_type=input_type)
        return result.embeddings