import argparse
from pathlib import Path


def parse_arguments():
    parser = argparse.ArgumentParser(description="ATRIUM - Lindat Translation Wrapper")

    # Source file
    parser.add_argument("input_file", type=Path, help="Path to the source file (.pdf, .xml, .txt)")

    # Optional Output and Target Language
    parser.add_argument("--output", type=Path, default=None,
                        help="Path to save the translated text. Defaults to '<input_name>_<target_lang>.txt'")
    parser.add_argument("--target_lang", type=str, default="en",
                        help="Target language code (e.g., 'en', 'cs', 'fr'). Default: 'en'")

    args = parser.parse_args()

    # ---------------------------------------------------------
    # AUTOMATIC OUTPUT NAMING LOGIC
    # ---------------------------------------------------------
    if args.output is None:
        # Extract the base name without extension (e.g., 'document' from 'document.pdf')
        base_name = args.input_file.stem

        # Create the new filename with the target language suffix
        new_filename = f"{base_name}_{args.target_lang}.txt"

        # Save it in the same directory as the input file
        args.output = args.input_file.with_name(new_filename)

    return args


def main():
    args = parse_arguments()

    print(f"Translating: {args.input_file}")
    print(f"Target Language: {args.target_lang}")
    print(f"Output will be saved to: {args.output}")

    # 1. Extract Text (Layout Analysis)
    print("Initializing LayoutReader and extracting text...")
    extractor = LayoutExtractor()
    raw_text = extractor.extract(args.input_file)

    if not raw_text.strip():
        print("No text extracted.")
        return

    # 2. Identify Language
    print("Identifying source language...")
    identifier = LanguageIdentifier()
    src_lang, lang_score = identifier.detect(raw_text)

    # UPDATED: Check confidence score
    # If confidence is low (< 0.4), assume data is inadequate for detection and default to Czech
    if lang_score < 0.4:
        print(f"Warning: Language detection confidence low ({round(lang_score, 3)} < 0.4).")
        print("Defaulting source language to 'cs' (Czech).")
        src_lang = 'cs'
    else:
        print(f"Detected Language: {src_lang} - Confidence: {round(lang_score * 100, 3)}%")

    # 3. Translate
    if src_lang == args.target_lang:
        print("Source matches target. Skipping translation.")
        final_text = raw_text
    else:
        print(f"Translating from {src_lang} to {args.target_lang}...")
        translator = LindatTranslator()
        final_text = translator.translate(raw_text, src_lang, args.target_lang)

    # 4. Output
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(final_text)

    print(f"Done! Translation saved to {args.output}")


if __name__ == "__main__":
    main()