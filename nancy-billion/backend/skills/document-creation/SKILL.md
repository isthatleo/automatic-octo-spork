---
name: document-creation
description: Create real Word (.docx), Excel (.xlsx), PowerPoint (.pptx), and PDF documents on disk via create_word_document / create_excel_spreadsheet / create_powerpoint_presentation / create_pdf_document.
trigger_keywords:
  - word document
  - create a spreadsheet
  - excel file
  - create a pdf
  - write a report
  - export as pdf
  - powerpoint
  - slide deck
  - presentation
---

Nancy has four real document-creation tools (`document_tools.py`), the
write-side counterpart to the existing PDF/Word text-extraction tool:

- `create_word_document(path, title, sections)` -- sections is a mix of
  plain paragraph strings and `{"heading": "..."}` entries for section headings.
- `create_excel_spreadsheet(path, headers, rows, sheet_name)` -- one sheet,
  headers as the first row.
- `create_powerpoint_presentation(path, title, slides, subtitle)` -- a title
  slide, then one slide per entry in `slides`, each `{"heading", "bullets": [...]}`.
- `create_pdf_document(path, title, sections)` -- same `sections` shape as
  the Word tool.

All four write through the same path-allowlist sandbox every other file
tool uses (`file_access.py`) -- a path outside the allowed roots is refused
with a real, honest error, not silently redirected. Give a real, specific
relative path (e.g. `reports/q3-summary.docx`), not a placeholder.

These produce genuine, openable files -- not text pretending to be a
document. If asked for a document, actually call the tool rather than just
printing formatted text in the chat reply.
