"""Extract morphological annotations from the Reader PDF (NION Part II).

Text I (Hrólfs saga kraka) has comprehensive word-by-word grammatical
commentary that serves as a gold-standard validation corpus.
"""

from pathlib import Path


def extract_annotations(pdf_path: Path) -> list[dict]:
    """Parse Text I annotations and return a list of annotation dicts.

    Each dict has keys matching the annotations schema.
    Not yet implemented.
    """
    raise NotImplementedError
