import base64
import anthropic
from sentismetric.config import settings
from sentismetric.extract.vision_backend import VisionBackend

PROMPT="""Transcribe this scanned page from an Indian SME company's stock-exchange filing into clean Markdown.
        Rules:
        - Preserve ALL text exactly as printed, including numbers , dates, names.
        - Render tables as Markdown pipe tables
        - Mark truly illegible fragments as [illegible]; NEVER guess at numbers.
        - Output only the markdown, no commentary."""
class ClaudeVision(VisionBackend):
    def __init__(self) -> None:
        self.client	=anthropic.Anthropic(api_key=settings.anthropic_api_key)
    def page_to_markdown(self, png_bytes: bytes) -> str:
        msg = self.client.messages.create(
            model= "claude-sonnet-4-6",
            max_tokens=4000,
            messages=[{"role":"user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/png",
                    "data": base64.b64encode(png_bytes).decode()}},
                {"type": "text","text": PROMPT},
            ]}],
        )
        return msg.content[0].text