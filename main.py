import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Graceful fallback for tqdm so the script works out-of-the-box
try:
    from tqdm import tqdm
except ImportError:
    def tqdm(iterable, *args, **kwargs):
        total = kwargs.get('total', len(iterable) if hasattr(iterable, '__len__') else None)
        desc = kwargs.get('desc', 'Processing')
        for i, item in enumerate(iterable, 1):
            if total:
                sys.stdout.write(f"\r[INFO] {desc}: {i}/{total} ({(i/total)*100:.1f}%)")
            else:
                sys.stdout.write(f"\r[INFO] {desc}: {i} items")
            sys.stdout.flush()
            yield item
        print() # Newline after loop

from processors.extractor import LayoutExtractor
from processors.identifier import LanguageIdentifier
from processors.translator import LindatTranslator
from utils import get_alto_textblocks


def parse_arguments():
    parser = argparse.ArgumentParser(description="ATRIUM - Lindat Translation Wrapper")
    parser.add_argument("input_file", type=Path, default=None, help="Path to the source file (.pdf, .xml, .txt)")
    parser.add_argument("--fields", type=Path, default="xml-fields.txt", help="Path to a .txt file containing XML tags to translate (one per line).")
    parser.add_argument("--output", type=Path, default=None, help="Path to save the translated text. Defaults to '<input_name>_<target_lang>.<ext>'")
    parser.add_argument("--target_lang", type=str, default="en", help="Target language code (e.g., 'en', 'cs', 'fr'). Default: 'en'")

    args = parser.parse_args()

    if args.output is None:
        base_name = args.input_file.stem
        ext = args.input_file.suffix if (args.fields and args.input_file.suffix.lower() == '.xml') else '.txt'
        new_filename = f"{base_name}_{args.target_lang}{ext}"
        args.output = args.input_file.with_name(new_filename)

    return args


def process_standard_file(args):
    """Original logic: Extracts all text and outputs to a flat .txt file."""
    print("[INFO] Initializing LayoutReader and extracting text...")
    extractor = LayoutExtractor()
    raw_text = extractor.extract(str(args.input_file))

    if not raw_text.strip():
        print("[WARN] No text extracted. Exiting.")
        return

    print("[INFO] Identifying source language...")
    identifier = LanguageIdentifier()
    src_lang, lang_score = identifier.detect(raw_text)

    if lang_score < 0.4:
        print(f"[WARN] Language detection confidence low ({round(lang_score, 3)} < 0.4). Defaulting to 'cs'.")
        src_lang = 'cs'
    else:
        print(f"[INFO] Detected Language: {src_lang.upper()} (Confidence: {round(lang_score * 100, 1)}%)")

    if src_lang == args.target_lang:
        print("[INFO] Source matches target. Skipping translation.")
        final_text = raw_text
    else:
        print(f"[INFO] Translating from {src_lang.upper()} to {args.target_lang.upper()}...")
        translator = LindatTranslator()
        final_text = translator.translate(raw_text, src_lang, args.target_lang)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(final_text)

    print(f"[SUCCESS] Translation saved to: {args.output}")


def process_xml_in_place(args):
    """New logic: Translates ALTO XML at the TextBlock level and preserves tree structure/coordinates."""
    print("[INFO] ALTO XML Mode: Extracting TextBlocks...")
    tree, root, namespace, blocks_data = get_alto_textblocks(args.input_file)

    if not tree:
        print("[ERROR] Failed to parse XML.")
        return

    if not blocks_data:
        print("[WARN] No matching TextBlocks found. Saving exact copy.")
        tree.write(args.output, encoding='utf-8', xml_declaration=True)
        return

    # Sample text for language detection
    sample_text = " ".join([data[1] for data in blocks_data[:20]])
    print("[INFO] Identifying source language from XML elements' content...")
    identifier = LanguageIdentifier()
    src_lang, lang_score = identifier.detect(sample_text)

    if lang_score < 0.4:
        print(f"[WARN] Language detection confidence low ({round(lang_score, 3)} < 0.4). Defaulting to 'cs'.")
        src_lang = 'cs'
    else:
        print(f"[INFO] Detected Language:\t{src_lang.upper()} (Confidence: {round(lang_score * 100, 1)}%)")

    if src_lang == args.target_lang:
        print("[INFO] Source matches target. Saving exact copy.")
        tree.write(args.output, encoding='utf-8', xml_declaration=True)
        return

    unique_blocks = list(set(d[1] for d in blocks_data))
    print(f"[INFO] Prepared {len(unique_blocks)} unique text blocks for translation.")

    translator = LindatTranslator()
    translation_cache = {}

    # Translate uniquely to minimize redundant API calls with Progress Bar
    for original_text in tqdm(unique_blocks, desc="Translating TextBlocks", unit="block"):
        translation_cache[original_text] = translator.translate(original_text, src_lang, args.target_lang)

    # Apply translations back to the elements proportionally
    print("[INFO] Reconstructing XML TextLines with translated content...")
    for block_elem, original_text, lines in tqdm(blocks_data, desc="Rebuilding XML", unit="block"):
        translated_text = translation_cache[original_text]
        words = translated_text.split()
        num_lines = len(lines)

        if num_lines == 0:
            continue

        # Distribute words roughly evenly across the original number of lines
        words_per_line = len(words) // num_lines
        remainder = len(words) % num_lines

        word_idx = 0
        for i, line_elem in enumerate(lines):
            # Calculate how many words go to this specific line
            count = words_per_line + (1 if i < remainder else 0)
            line_words = words[word_idx: word_idx + count]
            word_idx += count

            line_str = " ".join(line_words)

            # Remove old children (String, SP) to prepare for the single translated String
            # This is safer than .clear() as it preserves the TextLine's own attributes (HPOS/VPOS)
            for child in list(line_elem):
                line_elem.remove(child)

            if not line_str:
                continue

            # Create a single new String element for the line
            string_tag = f"{namespace}String" if namespace else "String"
            new_string = ET.Element(string_tag)

            # Inherit the bounding box of the entire TextLine to maintain layout
            new_string.attrib['HPOS'] = line_elem.attrib.get('HPOS', '0')
            new_string.attrib['VPOS'] = line_elem.attrib.get('VPOS', '0')
            new_string.attrib['WIDTH'] = line_elem.attrib.get('WIDTH', '0')
            new_string.attrib['HEIGHT'] = line_elem.attrib.get('HEIGHT', '0')
            new_string.attrib['CONTENT'] = line_str

            # Inject the new String back into the XML Tree
            line_elem.append(new_string)

    tree.write(args.output, encoding='utf-8', xml_declaration=True)
    print(f"[SUCCESS] Translated XML saved to: {args.output}")


def main():
    args = parse_arguments()

    print(f"\n{'='*50}")
    print(f" ATRIUM (ALTO.XML/TXT) LINDAT TRANSLATOR")
    print(f"{'='*50}")
    print(f"[INPUT]  {args.input_file}")
    print(f"[TARGET] Language: {args.target_lang.upper()}")
    print(f"[OUTPUT] {args.output}")
    print("-" * 50)

    if args.fields and args.input_file.suffix.lower() == '.xml':
        process_xml_in_place(args)
    else:
        process_standard_file(args)

    print("-" * 50)


if __name__ == "__main__":
    main()