import fasttext
from huggingface_hub import hf_hub_download


class LanguageIdentifier:
    def __init__(self):
        model_path = hf_hub_download(repo_id="facebook/fasttext-language-identification", filename="model.bin")
        self.model = fasttext.load_model(model_path)

    def detect(self, text):
        # FastText expects single line usually, so we replace newlines for detection
        clean_text = text.replace('\n', ' ')[:1000]  # Check first 1000 chars
        labels, scores = self.model.predict(clean_text)

        # Label format is __label__xx
        lang_code = labels[0].replace("__label__", "")
        return lang_code