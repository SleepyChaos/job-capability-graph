import argparse
from pathlib import Path

import pypdfium2 as pdfium


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--dpi", type=int, default=144)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(args.pdf)
    scale = args.dpi / 72
    for index, page in enumerate(document, start=1):
        image = page.render(scale=scale).to_pil()
        image.save(args.output_dir / f"page-{index}.png")
    print(f"pages={len(document)}")


if __name__ == "__main__":
    main()
