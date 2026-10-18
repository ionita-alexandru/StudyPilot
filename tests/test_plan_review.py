"""Tests sans Ollama : PDF quelconque, cache, segmentation, garde-fous."""
import json
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from src.config import STUDY_MODEL
from src.courses.planner import _id, extract_document, restore_preview
from src.courses.plan_review import (accepted_preview, build_theme_index, build_prompt,
                             create_candidate, page_digest, preview_fingerprint,
                             validate_proposals)


class PlanReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pdf = Path(self.tmp.name) / "cours-synthetique.pdf"
        with pymupdf.open() as pdf:
            for i in range(1, 11):
                page = pdf.new_page()
                topic = "Ondes électromagnétiques" if i <= 4 else "Algèbre linéaire" if i <= 7 else "Géographie"
                page.insert_text((40, 65), f"{topic} : méthodes de la page {i}.")
                page.insert_text((40, 90), "Définition, démonstration et exemples.")
                page.insert_text((40, 115), f"Conclusion et application de la page {i}.")
            pdf.save(self.pdf)
        self.document = extract_document(self.pdf)
        h = self.document["file_hash"]
        self.saved = {"plan_version": 1, "filename": self.pdf.name, "file_hash": h,
                      "page_count": 10, "mode": "thematic_ai_draft", "status": "draft",
                      "warnings": [], "page_diagnostics": [], "model": STUDY_MODEL, "parts": []}
        for i, (a, b, title) in enumerate(((1, 4, "Ondes électromagnétiques"),
                                          (5, 10, "Algèbre et géographie")), 1):
            self.saved["parts"].append({"id": _id(h, f"pages:{a}:{b}"), "number": str(i),
                                         "title": title, "page_start": a, "page_end": b,
                                         "title_origin": "ai_proposal", "source_pages": list(range(a, b+1)),
                                         "overview": {"status": "draft", "summary": "Ancienne synthèse"}})
        self.cache = Path(self.tmp.name) / "index.json"
        self.reply = {"parts": [{"start_page": 1, "end_page": 4, "title": "Ondes électromagnétiques"},
                                 {"start_page": 5, "end_page": 7, "title": "Applications de l'algèbre"},
                                 {"start_page": 8, "end_page": 10, "title": "Géographie des régions"}]}

    def tearDown(self):
        self.tmp.cleanup()

    def fake_call(self, prompt, model):
        if "INDEX PAGE PAR PAGE" in prompt:
            self.assertIn("p.10:", prompt)
            self.assertNotIn("Algèbre et géographie", prompt)  # ancien titre absent
            return self.reply
        numbers = [int(x) for x in re.findall(r"PAGE PHYSIQUE (\d+)", prompt)]
        return {"pages": [{"page": number, "topics": ["Ondes électromagnétiques" if number <= 4
                          else "Algèbre linéaire" if number <= 7 else "Géographie des régions"]} for number in numbers]}

    def test_page_excerpt_includes_last_zone(self):
        page = {"page": 1, "headings": ["Titre principal"],
                "analysis_text": "\n".join(f"Information descriptive numéro {i} et exemple" for i in range(60))}
        digest = page_digest(page)
        self.assertIn("numéro 0", digest)
        self.assertIn("numéro 30", digest)
        self.assertIn("numéro 59", digest)

    def test_index_batches_cache_reuse_and_distinctive_plan(self):
        calls = []
        def fake(prompt, model):
            calls.append(prompt)
            return self.fake_call(prompt, model)
        candidate = create_candidate(self.saved, self.document, ai_call=fake, index_cache=self.cache)
        self.assertEqual(len(calls), 4)  # 3 lots de 4 pages + plan
        self.assertEqual([p["page_end"] for p in candidate["parts"]], [4, 7, 10])
        self.assertEqual(candidate["parts"][0]["overview"], self.saved["parts"][0]["overview"])
        self.assertEqual(candidate["parts"][1]["overview"], {"status": "pending"})
        self.assertEqual(self.saved["parts"][1]["overview"]["status"], "draft")
        merged = accepted_preview(candidate, self.saved, self.document)
        restore_preview(merged, self.document)
        calls.clear()
        create_candidate(self.saved, self.document, ai_call=fake, index_cache=self.cache)
        self.assertEqual(len(calls), 1)  # aucun lot IA supplémentaire

    def test_partial_cache_survives_interrupted_generation(self):
        count = 0
        def fails_second_batch(prompt, model):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError("Ollama arrêté")
            return self.fake_call(prompt, model)
        with self.assertRaisesRegex(RuntimeError, "arrêté"):
            build_theme_index(self.document, ai_call=fails_second_batch, cache_path=self.cache)
        self.assertEqual(len(json.loads(self.cache.read_text())["pages"]), 4)
        subsequent_calls = []
        def resumed(prompt, model):
            subsequent_calls.append(prompt)
            return self.fake_call(prompt, model)
        index = build_theme_index(self.document, ai_call=resumed, cache_path=self.cache)
        self.assertEqual(len(index["pages"]), 10)
        self.assertEqual(len(subsequent_calls), 2)

    def test_reject_generic_titles_with_recurrent_subject(self):
        generic = [{"start_page": 1, "end_page": 3, "title": "Gestion des marges et couleurs"},
                   {"start_page": 4, "end_page": 6, "title": "Gestion des marges et images"},
                   {"start_page": 7, "end_page": 10, "title": "Gestion des marges et mises en page"}]
        with self.assertRaisesRegex(ValueError, "Titres génériques"):
            validate_proposals(generic, self.document)
        with self.assertRaisesRegex(ValueError, "manquantes"):
            validate_proposals([{"start_page": 1, "end_page": 4, "title": "Ondes"},
                                {"start_page": 6, "end_page": 10, "title": "Algèbre"}], self.document)
        long_part = validate_proposals(
            [{"start_page": 1, "end_page": 8, "title": "Ondes"},
             {"start_page": 9, "end_page": 10, "title": "Algèbre"}],
            self.document,
        )
        self.assertEqual(long_part[0]["end_page"], 8)

    def test_invalid_index_and_incompatible_model(self):
        def bad(prompt, model):
            return {"pages": [{"page": 999, "topics": ["Sujet"]} for _ in range(4)]}
        with self.assertRaisesRegex(ValueError, "absente de la réponse"):
            build_theme_index(self.document, ai_call=bad, cache_path=self.cache)
        self.assertFalse(self.cache.exists())
        build_theme_index(self.document, ai_call=self.fake_call, cache_path=self.cache)
        with self.assertRaisesRegex(ValueError, "incompatible"):
            build_theme_index(self.document, model="autre-modele", ai_call=self.fake_call, cache_path=self.cache)

    def test_stale_candidate_and_overview_injection_refused(self):
        candidate = create_candidate(self.saved, self.document, ai_call=self.fake_call, index_cache=self.cache)
        copy = json.loads(json.dumps(self.saved))
        copy["warnings"].append("changé")
        with self.assertRaisesRegex(ValueError, "base a changé"):
            accepted_preview(candidate, copy, self.document)
        candidate["parts"][1]["overview"] = {"status": "draft", "summary": "faux"}
        merged = accepted_preview(candidate, self.saved, self.document)
        self.assertEqual(merged["parts"][1]["overview"], {"status": "pending"})
        candidate["parts"][0]["id"] = "invalide"
        with self.assertRaisesRegex(ValueError, "ID"):
            accepted_preview(candidate, self.saved, self.document)

    def test_six_topics_are_accepted_without_truncation_or_retry(self):
        calls = []
        def answer(prompt, model):
            calls.append(prompt)
            pages = [int(x) for x in re.findall(r"PAGE PHYSIQUE (\d+)", prompt)]
            return {"pages": [{"page": n, "topics": [f"Thème distinct {i}" for i in range(1, 7)]}
                              for n in pages]}
        index = build_theme_index(self.document, ai_call=answer, cache_path=self.cache)
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(index["pages"][9]["topics"]), 6)

    def test_invalid_page_is_retried_once_and_earlier_pages_saved(self):
        calls = []
        retries = []
        def answer(prompt, model):
            pages = [int(x) for x in re.findall(r"PAGE PHYSIQUE (\d+)", prompt)]
            calls.append(pages)
            return {"pages": [{"page": n, "topics": ["Sujet de la page"] if n != 6 or len(pages) == 1
                               else [{"title": "Erreur de format"}]} for n in pages]}
        index = build_theme_index(self.document, ai_call=answer, cache_path=self.cache,
                                  retry_callback=lambda n, err: retries.append((n, err)))
        self.assertEqual(len(index["pages"]), 10)
        self.assertEqual(retries[0][0], 6)
        self.assertEqual(calls, [[1, 2, 3, 4], [5, 6, 7, 8], [6], [9, 10]])
        self.assertEqual(len(json.loads(self.cache.read_text())["pages"]), 10)

    def test_failed_single_retry_diagnoses_and_preserves_prefix_for_resume(self):
        calls = []
        def invalid(prompt, model):
            pages = [int(x) for x in re.findall(r"PAGE PHYSIQUE (\d+)", prompt)]
            calls.append(pages)
            return {"pages": [{"page": n, "topics": ["Sujet valide"] if n != 6 else [0]}
                              for n in pages]}
        with self.assertRaisesRegex(ValueError, "thème 1 non textuel"):
            build_theme_index(self.document, ai_call=invalid, cache_path=self.cache)
        self.assertEqual(calls, [[1, 2, 3, 4], [5, 6, 7, 8], [6]])
        self.assertEqual(len(json.loads(self.cache.read_text())["pages"]), 5)
        diagnostic = self.cache.with_name("index.diagnostic.json")
        self.assertEqual(json.loads(diagnostic.read_text())["page"], 6)
        self.assertEqual(len(build_theme_index(self.document, ai_call=self.fake_call,
                                                cache_path=self.cache)["pages"]), 10)
        self.assertFalse(diagnostic.exists())

    def test_last_batch_missing_page_recovered_without_reindexing(self):
        # Le bug réel : p.25–26, Ollama ne renvoie qu'une des deux pages.
        document = dict(self.document)
        document["page_count"] = 26
        document["pages"] = [dict(self.document["pages"][i % 10], page=i+1)
                             for i in range(26)]
        prefix = {"index_version": 1, "file_hash": document["file_hash"],
                  "filename": document["filename"], "page_count": 26,
                  "model": STUDY_MODEL,
                  "pages": [{"page": n, "topics": ["Sujet identifié"]} for n in range(1, 25)]}
        self.cache.write_text(json.dumps(prefix), encoding="utf-8")
        calls, retries = [], []
        def answer(prompt, model):
            numbers = [int(x) for x in re.findall(r"PAGE PHYSIQUE (\d+)", prompt)]
            calls.append(numbers)
            if numbers == [25, 26]:
                return {"pages": [{"page": 26, "topics": ["Navigation"]}]}
            return {"pages": [{"page": n, "topics": ["Liens et fragments"]} for n in numbers]}
        result = build_theme_index(document, ai_call=answer, cache_path=self.cache,
                                   retry_callback=lambda n, msg: retries.append((n,msg)))
        self.assertEqual(calls, [[25,26], [25]])
        self.assertEqual([p["page"] for p in result["pages"]], list(range(1,27)))
        self.assertEqual(result["pages"][25]["topics"], ["Navigation"])
        self.assertEqual(retries[0][0], 25)
        self.assertEqual(len(json.loads(self.cache.read_text())["pages"]),26)

    def test_missing_last_page_retried_and_first_page_preserved(self):
        calls = []
        def answer(prompt, model):
            numbers = [int(x) for x in re.findall(r"PAGE PHYSIQUE (\d+)",prompt)]
            calls.append(numbers)
            if numbers == [1,2,3,4]:
                return {"pages":[{"page": n,"topics":["Thème documenté"]} for n in [1,2,3]]}
            return {"pages":[{"page": n,"topics":["Thème documenté"]} for n in numbers]}
        result = build_theme_index(self.document, ai_call=answer, cache_path=self.cache)
        self.assertEqual(calls[:2], [[1,2,3,4],[4]])
        self.assertEqual([p["page"] for p in result["pages"]], list(range(1,11)))

    def test_duplicate_page_number_retried_not_silently_accepted(self):
        calls = []
        def answer(prompt, model):
            numbers = [int(x) for x in re.findall(r"PAGE PHYSIQUE (\d+)",prompt)]
            calls.append(numbers)
            if numbers == [1,2,3,4]:
                return {"pages":[{"page":n,"topics":["Thème présent"]} for n in [1,2,2,3,4]]}
            return {"page":numbers[0],"topics":["Thème ciblé"]} if numbers == [2] else {
                "pages":[{"page":n,"topics":["Thème présent"]} for n in numbers]}
        result = build_theme_index(self.document, ai_call=answer, cache_path=self.cache)
        self.assertEqual(calls[:2], [[1,2,3,4],[2]])
        self.assertEqual(result["pages"][1]["topics"], ["Thème ciblé"])
        self.assertEqual(len(result["pages"]),10)

    def test_failed_retry_after_missing_page_keeps_saved_prefix(self):
        def answer(prompt, model):
            numbers = [int(x) for x in re.findall(r"PAGE PHYSIQUE (\d+)",prompt)]
            if numbers == [1,2,3,4]:
                return {"pages":[{"page":1,"topics":["Premier thème"]},
                                 {"page":3,"topics":["Troisième thème"]},
                                 {"page":4,"topics":["Quatrième thème"]}]}
            if numbers == [2]:
                return {"pages":[]}
            return self.fake_call(prompt,model)
        with self.assertRaisesRegex(ValueError, "Index page 2"):
            build_theme_index(self.document, ai_call=answer, cache_path=self.cache)
        self.assertEqual([p["page"] for p in json.loads(self.cache.read_text())["pages"]],[1])
        self.assertTrue(self.cache.with_name("index.diagnostic.json").is_file())

    def test_numbered_guard(self):
        saved = json.loads(json.dumps(self.saved))
        saved["mode"] = "numbered"
        with patch("src.courses.plan_review.restore_preview", return_value=saved):
            with self.assertRaisesRegex(ValueError, "numéroté"):
                create_candidate(saved, self.document, ai_call=self.fake_call)


if __name__ == "__main__":
    unittest.main()
