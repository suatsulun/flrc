"""Download names for report PDFs, ZIPs and class sheets (ADR-077).

Names are the school's own wording — ``8-A İngilizce Karne 2026-2027 1. Dönem.pdf`` — whatever
the interface language, so a file is named the same wherever it was requested. Turkish letters
and spaces stay; ``/`` in class names becomes ``-`` and characters Windows refuses in a file
name are dropped.
"""

import re
import unicodedata
from typing import Literal
from urllib.parse import quote

CARD_LABELS = {
    "english_elementary": "İngilizce Karne",
    "english_middle": "İngilizce Karne",
    "german_karne": "Almanca Karne",
    "french_karne": "Fransızca Karne",
}
WHOLE_SCHOOL = "Tüm Okul"
SELECTED_STUDENTS = "Seçili Öğrenciler"
SELECTED_CLASSES = "Seçili Sınıflar"
CLASS_SHEET = "Sınıf Raporu"
CLASS_SHEETS = "Sınıf Raporları"
FALLBACK_NAME = "download"

# Characters Windows refuses in a file name, plus every control character.
_UNSAFE = re.compile(r'[<>:"\\|?*\x00-\x1f\x7f]')
# Dotless/dotted i have no decomposition; everything else folds through NFKD.
_ASCII_LETTERS = str.maketrans({"ı": "i", "İ": "I"})


def clean_filename(value: str) -> str:
    """A file name every desktop accepts, keeping spaces and Turkish letters."""
    cleaned = _UNSAFE.sub("", value.replace("/", "-"))
    return " ".join(cleaned.split()).strip(" .")


def term_label(year_label: str, semester_number: int) -> str:
    return f"{year_label} {semester_number}. Dönem"


def student_scope(class_name: str, school_number: int | None, student_name: str) -> str:
    """``8-A 123 Ali Yılmaz``; a student without a number is named by class and name."""
    number = str(school_number) if school_number else ""
    return " ".join(part for part in (class_name, number, student_name) if part)


def report_filename(
    scope: str,
    kind: str,
    year_label: str,
    semester_number: int,
    extension: Literal["pdf", "zip"],
) -> str:
    stem = f"{scope} {CARD_LABELS[kind]} {term_label(year_label, semester_number)}"
    return f"{clean_filename(stem)}.{extension}"


def class_sheet_filename(class_names: list[str], year_label: str, semester_number: int) -> str:
    scope = f"{class_names[0]} {CLASS_SHEET}" if len(class_names) == 1 else CLASS_SHEETS
    return f"{clean_filename(f'{scope} {term_label(year_label, semester_number)}')}.pdf"


def part_filename(filename: str, number: int) -> str:
    """``… 1. Dönem (Bölüm 2).zip``: one of the numbered parts of a set too large for one file."""
    stem, _, extension = filename.rpartition(".")
    return f"{stem} (Bölüm {number}).{extension}"


def ascii_filename(value: str) -> str:
    """The ``filename=`` fallback for clients without RFC 5987: Turkish letters folded.

    Folding turns compatibility characters such as fullwidth ``＂`` and ``＼`` into ASCII
    quotes and backslashes, so the folded name is cleaned again before it is quoted.
    """
    folded = unicodedata.normalize("NFKD", value.translate(_ASCII_LETTERS))
    ascii_only = "".join(
        char if char.isascii() else "_" for char in folded if not unicodedata.combining(char)
    )
    return clean_filename(ascii_only) or FALLBACK_NAME


def content_disposition(filename: str | None, *, inline: bool = False) -> str:
    """An RFC 6266 header with an ASCII fallback and the UTF-8 name as ``filename*``."""
    name = clean_filename(filename or "") or FALLBACK_NAME
    disposition = "inline" if inline else "attachment"
    return (
        f'{disposition}; filename="{ascii_filename(name)}"; '
        f"filename*=UTF-8''{quote(name, safe='')}"
    )
