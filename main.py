import argparse
import sys
import csv
import re
import configparser
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
                sys.stdout.write(f"\r[INFO] {desc}: {i}/{total} ({(i / total) * 100:.1f}%)")
            else:
                sys.stdout.write(f"\r[INFO] {desc}: {i} items")
            sys.stdout.flush()
            yield item
        print()

from processors.identifier import LanguageIdentifier
from processors.translator import LindatTranslator
from utils import process_alto_xml, process_amcr_xml


def parse_arguments():
    parser = argparse.ArgumentParser(description="ATRIUM - Lindat Translation Wrapper (XML Focused)")
    parser.add_argument("input_path", type=Path, nargs='?', default=None,
                        help="Path to a single XML file or a directory containing XML files.")
    parser.add_argument("--output", "-o", type=Path, default=None,
                        help="Output file path (for single) or output directory (for batch mode).")
    parser.add_argument("--source_lang", "-src", type=str, default="cs",
                        help="Source language code (e.g., 'cs', 'fr'). Default: 'cs'")
    parser.add_argument("--target_lang", "-tgt", type=str, default="en",
                        help="Target language code (e.g., 'en', 'cs', 'fr'). Default: 'en'")
    parser.add_argument("--config", "-c", type=Path, default=Path("config.txt"),
                        help="Path to configuration file. Settings here override console flags.")

    # ALTO Mode
    parser.add_argument("--alto", action="store_true",
                        help="Flag to enable ALTO XML in-place translation mode.")

    # AMCR Mode
    parser.add_argument("--xpaths", type=Path, default=None,
                        help="Path to a .txt file containing XPaths for AMCR metadata translation.")
    parser.add_argument("--xsd", type=str, default=None,
                        help="Optional URL or local path to XSD file for AMCR output validation.")

    args = parser.parse_args()

    # Prioritize config file over console flags using configparser
    if args.config and args.config.exists():
        config = configparser.ConfigParser()

        # Read file, clean artifacts (like ""), and inject a [DEFAULT] section header
        with open(args.config, 'r', encoding='utf-8') as f:
            cleaned_lines = ['[DEFAULT]\n']
            for line in f:
                # Remove tags and leading/trailing whitespace
                cleaned_line = re.sub(r'^\[.*?\]\s*', '', line.strip())
                if cleaned_line and not cleaned_line.startswith('#'):
                    cleaned_lines.append(cleaned_line + '\n')

        # Parse the cleaned string representation of the config file
        config.read_string(''.join(cleaned_lines))
        defaults = config['DEFAULT']

        # Override console arguments with config values
        if 'input_path' in defaults:
            args.input_path = Path(defaults['input_path'])
        if 'output' in defaults:
            args.output = Path(defaults['output'])
        if 'source_lang' in defaults:
            args.source_lang = defaults['source_lang']
        if 'target_lang' in defaults:
            args.target_lang = defaults['target_lang']
        if 'fields' in defaults:
            args.xpaths = Path(defaults['fields'])  # Map config 'fields' to 'xpaths' argument

    return args


def generate_output_path(input_file, base_output, args, is_batch=False):
    # Fix for double extensions (e.g., .alto.xml -> _en.alto.xml instead of .alto_en.xml)
    if input_file.name.endswith(".alto.xml"):
        base_name = input_file.name[:-9]  # Removes the ".alto.xml" part
        new_filename = f"{base_name}_{args.target_lang}.alto.xml"
    else:
        new_filename = f"{input_file.stem}_{args.target_lang}{input_file.suffix}"

    if is_batch:
        return base_output / new_filename
    if base_output:
        if base_output.is_dir():
            return base_output / new_filename
        return base_output
    return input_file.with_name(new_filename)


def main():
    args = parse_arguments()

    print(f"\n{'=' * 60}")
    print(f" ATRIUM XML TRANSLATOR ".center(60, "="))
    print(f"{'=' * 60}")

    input_path = args.input_path

    if not input_path or (not input_path.is_dir() and not input_path.is_file()):
        print(f"[ERROR] Input path does not exist or was not provided. Please provide a valid file or directory.")
        return

    if not args.alto and not args.xpaths:
        print("[ERROR] You must specify either the --alto flag or provide an --xpaths file/fields in config.")
        return

    translator = LindatTranslator()

    # Load XPaths if applicable
    xpaths_list = []
    if args.xpaths and args.xpaths.exists():
        with open(args.xpaths, 'r', encoding='utf-8') as f:
            xpaths_list = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    # --- BATCH DIRECTORY PROCESSING ---
    if input_path.is_dir():
        files_to_process = [f for f in input_path.rglob('*.xml') if f.is_file()]

        if not files_to_process:
            print(f"[WARN] No valid XML files found in {input_path}")
            return

        out_dir = args.output if args.output else input_path / f"translated_{args.target_lang}"
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"[INFO] Batch Mode: Found {len(files_to_process)} XML files.")
        print(f"[INFO] Mode: {'ALTO' if args.alto else 'AMCR'}")

        for i, file_path in enumerate(files_to_process, 1):
            print(f"\n[FILE {i}/{len(files_to_process)}] Processing: {file_path.name}")
            output_file = generate_output_path(file_path, out_dir, args, is_batch=True)

            # Generate CSV log for EVERY file, regardless of ALTO or AMCR mode
            csv_path = out_dir / f"{file_path.name.split('.')[0]}_log.csv"
            csv_file = open(csv_path, "w", encoding="utf-8", newline="")
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(
                ["file", "page_num", "line_num", f"text_{args.source_lang}", f"text_{args.target_lang}"])

            try:
                if args.alto:
                    process_alto_xml(file_path, output_file, translator, args.source_lang, args.target_lang, csv_writer)
                else:
                    process_amcr_xml(file_path, output_file, xpaths_list, translator, args.source_lang,
                                     args.target_lang, args.xsd, csv_writer)
            except Exception as e:
                print(f"[ERROR] Failed processing {file_path.name}: {e}")

            if csv_file:
                csv_file.close()

    # --- SINGLE FILE PROCESSING ---
    else:
        output_file = generate_output_path(input_path, args.output, args)
        print(f"[INFO] Single File Mode: {input_path.name}")

        # Generate CSV log for single files universally as well
        csv_path = output_file.with_name(f"{input_path.name.split('.')[0]}_log.csv")
        csv_file = open(csv_path, "w", encoding="utf-8", newline="")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow(
            ["file", "page_num", "line_num", f"text_{args.source_lang}", f"text_{args.target_lang}"])

        try:
            if args.alto:
                process_alto_xml(input_path, output_file, translator, args.source_lang, args.target_lang, csv_writer)
            else:
                process_amcr_xml(input_path, output_file, xpaths_list, translator, args.source_lang, args.target_lang,
                                 args.xsd, csv_writer)
        except Exception as e:
            print(f"[ERROR] Failed processing {input_path.name}: {e}")

        if csv_file:
            csv_file.close()

    print(f"\n{'=' * 60}")
    print(f" PROCESSING COMPLETE ".center(60, "="))
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()