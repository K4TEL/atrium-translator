import requests
import sys

# Graceful fallback for tqdm inside the translator for large text chunks
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, *args, **kwargs):
        for item in iterable:
            yield item


class LindatTranslator:
    BASE_URL = "https://lindat.mff.cuni.cz/services/translation/api/v2"

    def __init__(self):
        self.supported_models = self._fetch_models()

    def _fetch_models(self):
        """Dynamically fetch supported language pairs."""
        try:
            resp = requests.get(f"{self.BASE_URL}/models")
            resp.raise_for_status()
            data = resp.json()

            # Fix: Handle Lindat's HAL JSON structure
            if isinstance(data, dict) and '_embedded' in data:
                return [item['model'] for item in data['_embedded'].get('item', [])]
            elif isinstance(data, list):
                return data
            else:
                return []
        except Exception as e:
            print(f"[WARN] Could not fetch models from API ({e}). Using default list.")
            return ["fr-en", "cs-en", "de-en", "uk-en", "ru-en", "pl-en"]

    def translate(self, text, src_lang, tgt_lang="en"):
        # Prevents unnecessary network calls for blanks
        if not text or not text.strip() or src_lang == tgt_lang:
            return text

        model_name = f"{src_lang}-{tgt_lang}"

        # Cleaned up model checking logic
        if self.supported_models:
            if model_name not in self.supported_models:
                print(f"[ERROR] Model '{model_name}' not found. Available models: {', '.join(self.supported_models)}")
                return f"[ERROR: Model {model_name} not supported]"
        else:
            print(f"[WARN] Proceeding with '{model_name}' (model validation unavailable).")

        # Chunk text to avoid 100KB limit
        chunks = self._chunk_text(text)
        translated_chunks = []

        # Only show a progress bar here if we actually have multiple chunks
        chunk_iter = tqdm(chunks, desc="Translating long text chunks", leave=False) if len(chunks) > 1 else chunks

        for chunk in chunk_iter:
            data = {"input_text": chunk}

            response = requests.post(
                f"{self.BASE_URL}/models/{model_name}?src={src_lang}&tgt={tgt_lang}",
                data=data
            )

            if response.status_code == 200:
                translated_chunks.append(response.text.strip())
            else:
                translated_chunks.append(f"[Translation Failed: {response.status_code} - {response.reason}]")

        return "\n".join(translated_chunks)

    def _chunk_text(self, text, chunk_size=5000):
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]