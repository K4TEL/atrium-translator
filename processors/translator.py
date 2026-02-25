import requests
import sys

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
        try:
            resp = requests.get(f"{self.BASE_URL}/models")
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, dict) and '_embedded' in data:
                return [item['model'] for item in data['_embedded'].get('item', [])]
            elif isinstance(data, list):
                return data
            else:
                return []
        except requests.exceptions.RequestException as e:
            print(f"[WARN] Network error fetching models ({e}). Using default list.")
            return ["fr-en", "cs-en", "de-en", "uk-en", "ru-en", "pl-en"]
        except ValueError as e:
            print(f"[WARN] Invalid JSON response ({e}). Using default list.")
            return ["fr-en", "cs-en", "de-en", "uk-en", "ru-en", "pl-en"]

    def translate(self, text, src_lang, tgt_lang="en"):
        if not text or not text.strip() or src_lang == tgt_lang:
            return text

        if src_lang == "auto":
            src_lang = "cs"
        model_name = f"{src_lang}-{tgt_lang}"

        if self.supported_models and model_name not in self.supported_models:
            print(f"[ERROR] Model '{model_name}' not found. Available models: {', '.join(self.supported_models)}")
            return f"[ERROR: Model {model_name} not supported]"

        chunks = self._chunk_text(text)
        translated_chunks = []

        chunk_iter = tqdm(chunks, desc="Translating long text chunks", leave=False) if len(chunks) > 1 else chunks

        for i, chunk in enumerate(chunk_iter):
            data = {"input_text": chunk}

            try:
                response = requests.post(
                    f"{self.BASE_URL}/models/{model_name}?src={src_lang}&tgt={tgt_lang}",
                    data=data
                )

                if response.status_code == 200:
                    # CRITICAL FIX: Force UTF-8 before reading text to prevent
                    # mangling of Czech characters with special accents.
                    response.encoding = 'utf-8'
                    translated_chunks.append(response.text.strip())
                else:
                    error_msg = f"[Translation Failed: HTTP {response.status_code}]"
                    print(error_msg)
                    translated_chunks.append(error_msg)
            except requests.exceptions.RequestException as e:
                error_msg = f"[Network Error: {e}]"
                print(error_msg)
                translated_chunks.append(error_msg)

        return "\n".join(translated_chunks)

    def _chunk_text(self, text, chunk_size=5000):
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]