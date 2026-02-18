import requests


class LindatTranslator:
    BASE_URL = "https://lindat.mff.cuni.cz/services/translation/api/v2"

    def __init__(self):
        self.supported_models = self._fetch_models()

    def _fetch_models(self):
        """Dynamically fetch supported language pairs."""
        try:
            resp = requests.get(f"{self.BASE_URL}/models")
            resp.raise_for_status()
            # Returns list of available models, e.g., ["en-cs", "fr-en", ...]
            return resp.json()
        except Exception:
            # Fallback hardcoded list if API discovery fails
            return ["fr-en", "cs-en", "de-en", "uk-en", "ru-en", "pl-en"]

    def translate(self, text, src_lang, tgt_lang="en"):
        if src_lang == tgt_lang:
            return text

        model_name = f"{src_lang}-{tgt_lang}"

        # Check if model exists (e.g., 'fr-en')
        if model_name not in self.supported_models:
            # Try to see if there is a generic model or handle error
            print(f"Warning: Direct model {model_name} not found. Available: {self.supported_models}")
            # Depending on API, might fallback to transformer logic or fail
            # For this draft, we proceed hoping the API handles it or we return original
            if model_name not in self.supported_models:
                return f"[ERROR: Model {model_name} not supported]"

        # Chunk text to avoid 100KB limit
        chunks = self._chunk_text(text)
        translated_chunks = []

        for chunk in chunks:
            data = {"input_text": chunk}
            response = requests.post(
                f"{self.BASE_URL}/models/{model_name}/translate",
                data=data
            )

            if response.status_code == 200:
                # The API returns extracted translated text (usually just raw string or json field)
                # Usually extraction needed: response.json()[0] or similar.
                # Inspecting docs: It returns simple text/plain usually if Accept header not set to json?
                # Let's assume text response for simplicity or simple list.
                translated_chunks.append(response.text.strip())
            else:
                translated_chunks.append(f"[Translation Failed: {response.status_code}]")

        return "\n".join(translated_chunks)

    def _chunk_text(self, text, chunk_size=5000):
        """Split text into chunks smaller than API limit."""
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]