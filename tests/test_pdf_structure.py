import unittest

from src.pdf.structure import extract_sections


class PdfStructureTests(unittest.TestCase):
    def test_example_and_result_lines_are_teaching_content_not_discarded_headers(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        import pymupdf
        from src.courses.planner import extract_document
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'nouveau.pdf'
            with pymupdf.open() as document:
                page = document.new_page()
                page.insert_text((40, 50), 'Example: doubler(3) returns 6.\nResult: the value is returned, not printed.')
                document.save(path)
            page = extract_document(path)['pages'][0]
        for field in ('raw_text', 'analysis_text', 'evidence_text'):
            self.assertIn('Example: doubler(3) returns 6.', page[field])
            self.assertIn('Result: the value is returned, not printed.', page[field])
        self.assertIn('Example:', '\n'.join(unit['native_text'] for unit in page['source_units']))
    def test_parser_keeps_first_course_line(self):
        pages = [{"page": 8, "text": (
            "4.2\nEspace propre\nDéfinition. On appelle vecteur propre de A "
            "le vecteur non nul v.\nSoit A une matrice carrée.\n"
            "4.3\nAutre section\nUne ligne importante."
        )}]
        sections = extract_sections(pages)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["title"], "Espace propre")
        self.assertIn("Définition.", sections[0]["content"])
        self.assertEqual(sections[0]["content_pages"][0]["page"], 8)
        self.assertIn("Une ligne importante.", sections[1]["content"])

    def test_no_numbered_heading_does_not_lose_pdf(self):
        sections = extract_sections([
            {"page": 2, "text": "La situation évolue.\nLes acteurs interviennent."}
        ])
        self.assertEqual(sections[0]["number"], "1")
        self.assertIn("La situation évolue.", sections[0]["content"])


if __name__ == "__main__":
    unittest.main()
