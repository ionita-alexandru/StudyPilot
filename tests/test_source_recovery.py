"""Contexte de listes, sources visuelles et reprise, sans modèle distant."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from src.courses import cards, inventory, illustrations
from src.courses.planner import extract_document
from src.courses.source_recovery import attach_illustrations, recover_document_evidence
from src.models.concept import Concept
from src.models.card import CardCollection
from src.storage.course_repository import CourseRepository


def concept(title, page=1, quote=None, kind="concept", anchor=None):
    return Concept(concept_id="notion-test", title=title, source_anchor=anchor,
        type=kind, primary_part_id="part-1", source_pages=[page],
        evidence=[{"page":page, "excerpt":quote or title}])


def list_page(lines):
    text = "\n".join(t for t, x in lines)
    return {"page":1, "raw_text":text, "analysis_text":text, "headings":[],
        "source_units":[{"heading":"", "excerpt":text,
            "native_lines":[{"text":t, "bbox":[x, 50+i*20, x+200, 65+i*20]} for i,(t,x) in enumerate(lines)]}]}


def visual_pages():
    return [
        {"page":1,"raw_text":"Montage expérimental","analysis_text":"Montage expérimental",
         "page_rect":[0,0,500,700],"image_regions":[],
         "source_units":[{"heading":"Montage expérimental", "excerpt":"Montage expérimental", "y":550}]},
        {"page":2,"raw_text":"Autre sujet","analysis_text":"Autre sujet",
         "page_rect":[0,0,500,700],"image_regions":[[60,60,300,240],[70,420,320,600]],
         "source_units":[{"heading":"Autre sujet", "excerpt":"Autre sujet", "native_text":"Autre sujet", "y":350}]},
    ]


class GenericSourceRecoveryTests(unittest.TestCase):
    def test_list_intro_recovers_biology_context_without_next_item_code(self):
        page=list_page([("Les organites suivants participent au fonctionnement de la cellule :",60),
                        ("Mitochondrie",90),("Chloroplaste",90),("Autre explication sans rapport avec la notion demandée",60)])
        c=concept("Mitochondrie")
        fixed=recover_document_evidence(c,[page])
        self.assertIsNone(fixed.evidence_issue)
        self.assertIn("fonctionnement de la cellule",fixed.evidence[0].excerpt)
        self.assertNotIn("Chloroplaste",fixed.evidence[0].excerpt)
        self.assertEqual(fixed,recover_document_evidence(fixed,[page]))

    def test_does_not_use_previous_item_definition_as_intro(self):
        page=list_page([("Mitochondrie : cet organite est décrit dans cette longue phrase",90),("Chloroplaste",90)])
        fixed=recover_document_evidence(concept("Chloroplaste"),[page])
        self.assertIsNotNone(fixed.evidence_issue)
        self.assertEqual(fixed.evidence[0].excerpt,"Chloroplaste")

    def test_bare_list_and_unrelated_page_stay_blocked(self):
        page=list_page([("Organites",60),("Mitochondrie",90),("Chloroplaste",90)])
        other=list_page([("Les organites suivants participent au fonctionnement de la cellule :",60),("Mitochondrie",90)])
        other["page"]=2
        fixed=recover_document_evidence(concept("Mitochondrie"),[page,other])
        self.assertIsNotNone(fixed.evidence_issue)
        self.assertEqual(fixed.source_pages,[1])

    def test_continuation_is_bounded_before_next_subject_even_without_ocr_text(self):
        pages=visual_pages(); attach_illustrations(pages)
        fixed=recover_document_evidence(concept("Montage expérimental"),pages)
        self.assertIsNone(fixed.evidence_issue)
        self.assertEqual(fixed.source_pages,[1,2])
        self.assertEqual(len(fixed.illustrations),1)
        self.assertLess(fixed.illustrations[0].bbox[3],350)
        self.assertEqual(fixed,recover_document_evidence(fixed,pages))
        with patch.object(cards,"chat_json") as generate, patch.object(cards,"audit_cards") as audit:
            result=cards._generate_batch({},pages,[fixed],model="modele-texte")
        generate.assert_not_called(); audit.assert_not_called()
        self.assertEqual(result[0].illustrations,fixed.illustrations)
        self.assertNotIn("courant",result[0].sections[0].content)

    def test_new_heading_or_native_prose_blocks_cross_page_attachment(self):
        for change in ("heading", "prose", "not_bottom", "not_adjacent"):
            pages=visual_pages()
            if change=="heading": pages[1]["source_units"][0]["y"]=30
            if change=="prose": pages[1]["source_units"].insert(0,{"heading":"","native_text":"Un texte sans rapport", "excerpt":"Un texte sans rapport","y":20})
            if change=="not_bottom": pages[0]["source_units"][0]["y"]=100
            if change=="not_adjacent": pages[1]["page"]=3
            attach_illustrations(pages)
            self.assertIsNotNone(recover_document_evidence(concept("Montage expérimental"),pages).evidence_issue,change)

    def test_modified_crop_and_foreign_heading_are_rejected(self):
        pages=visual_pages(); attach_illustrations(pages)
        fixed=recover_document_evidence(concept("Montage expérimental"),pages)
        for field,value in [("bbox",(1,1,490,690)),("heading","Autre sujet")]:
            image=fixed.illustrations[0].model_copy(update={field:value})
            forged=fixed.model_copy(update={"illustrations":[image]})
            with patch.object(cards,"chat_json") as call:
                with self.assertRaisesRegex(ValueError,"illustration absente"):
                    cards._generate_batch({},pages,[forged],model="modele-texte")
            call.assert_not_called()

    def test_v10_concept_hash_survives_empty_optional_field(self):
        c=concept("Mitochondrie")
        legacy=c.model_dump(mode="json");legacy.pop("illustrations")
        for field in ("relevance", "relevance_reason", "relevance_file_hash", "relevance_proof_hash", "learning_points", "card_role"):
            legacy.pop(field)
        expected=hashlib.sha256(json.dumps(legacy,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(cards._concept_hash(c),expected)

    def test_repair_saves_cross_page_provenance_and_is_idempotent(self):
        from src.models.concept import ConceptInventory
        pages=visual_pages();attach_illustrations(pages)
        sha="a"*64
        c=concept("Montage expérimental")
        saved=ConceptInventory(course_id="cours-test",file_hash=sha,model="modele-texte",concepts=[c])
        with tempfile.TemporaryDirectory() as folder:
            repo=CourseRepository(Path(folder))
            path=repo.save_inventory("cours-test",saved.model_dump(mode="json"));before=path.read_bytes()
            with patch.object(inventory,"load_course",return_value={"file_hash":sha,"source_filename":"cours.pdf"}),patch.object(inventory,"CourseRepository",return_value=repo),patch.object(inventory,"extract_document",return_value={"file_hash":sha,"pages":pages}),patch.object(inventory,"chat_json") as model:
                result,backup,count=inventory.repair_inventory_evidence("cours-test")
                self.assertEqual(count,1)
                self.assertEqual(Path(backup).read_bytes(),before)
                self.assertEqual(result.concepts[0].source_pages,[1,2])
                after=path.read_bytes()
                repeated,backup,count=inventory.repair_inventory_evidence("cours-test")
                self.assertEqual(count,0);self.assertIsNone(backup)
                self.assertEqual(path.read_bytes(),after)
                self.assertEqual(result,repeated)
            model.assert_not_called()

    def test_crop_renderer_route_and_template_show_original_pixels(self):
        pages=visual_pages();attach_illustrations(pages)
        fixed=recover_document_evidence(concept("Montage expérimental"),pages)
        card=cards._generate_batch({},pages,[fixed],model="modele-texte")[0]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);pdf=root/"source.pdf"
            doc=pymupdf.open();doc.new_page(width=500,height=700)
            second=doc.new_page(width=500,height=700)
            second.draw_rect(pymupdf.Rect(60,60,300,240),color=(1,0,0),fill=(1,0,0));doc.save(pdf);doc.close()
            sha=hashlib.sha256(pdf.read_bytes()).hexdigest()
            course={"course_id":"cours-test","source_filename":"source.pdf","file_hash":sha}
            repo=CourseRepository(root/"courses")
            collection=CardCollection(course_id="cours-test",file_hash=sha,inventory_hash="a"*64,model="modele-texte",cards=[card])
            repo.save_cards("cours-test",collection.model_dump(mode="json"))
            with patch.object(illustrations,"load_course",return_value=course),patch.object(illustrations,"COURSE_PDF_DIR",root),patch.object(illustrations,"CourseRepository",return_value=repo):
                png=illustrations.render_card_illustration("cours-test",card.card_id,0)
                pix=pymupdf.Pixmap(png)
                self.assertEqual(pix.pixel(pix.width//2,pix.height//2),(255,0,0))
                with self.assertRaises(FileNotFoundError):illustrations.render_card_illustration("cours-test",card.card_id,8)
                import app
                app.app.config["TESTING"]=True
                response=app.app.test_client().get(f"/course/cours-test/card/{card.card_id}/illustration/0")
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.mimetype,"image/png")
                with app.app.test_request_context():
                    template=app.app.jinja_env.get_template("part.html")
                    html=template.render(course={**course,"title":"Biologie"},courses=[],plan={"parts":[]},part={"id":"part-1","number":"1","title":"Montage","page_start":1,"page_end":2},cards=[card.model_dump(mode="json")],pdf_url="/source.pdf")
                self.assertIn(f"/card/{card.card_id}/illustration/0",html)
                self.assertIn("Extrait original",html)
                pdf.write_bytes(pdf.read_bytes()+b"\n")
                with self.assertRaisesRegex(ValueError,"correspond plus"):
                    illustrations.render_card_illustration("cours-test",card.card_id,0)


class RealSourceRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=Path(__file__).resolve().parents[1]/"data/pdfs/Cours-de-CSS-c41d0f1887.pdf"
        if not path.is_file():raise unittest.SkipTest("PDF de régression absent")
        cls.document=extract_document(path)

    def test_six_recoverable_cases_and_six_mentions_remain_distinct(self):
        cases=[("Propriété background-repeat",12,"By default, background images tile (repeat)","background-repeat","property"),
            ("Layout de page avec colonnes",21,"Two Column Page Layout","Two Column Page Layout","concept"),
            ("Propriété padding-right",9,"padding-right\n▪","padding-right","property")]
        cases += [(f"Éléments du wireframe : {name}",13,name,name,"concept") for name in ("Navigation","Content","Footer")]
        for title,n,quote,anchor,kind in cases:
            c=concept(title,n,quote,kind,anchor)
            fixed=recover_document_evidence(c,self.document["pages"])
            self.assertIsNone(fixed.evidence_issue,title)
            self.assertEqual(fixed.concept_id,c.concept_id)
            self.assertEqual(fixed.primary_part_id,c.primary_part_id)
            self.assertEqual(fixed,recover_document_evidence(fixed,self.document["pages"]))
        for name in ("background-color","font-height","margin","text-align","text-decoration","width"):
            c=concept(f"Propriété {name}",3,name,"property",name)
            fixed=recover_document_evidence(c,self.document["pages"])
            self.assertIsNotNone(fixed.evidence_issue,name)
            self.assertFalse(fixed.illustrations)
            self.assertEqual(fixed.evidence,c.evidence)
