"""Tests de navigation de l'interface moderne StudyPilot."""

import importlib.util
import re
import unittest
from unittest.mock import patch


FLASK_AVAILABLE = (
    importlib.util.find_spec("flask")
    is not None
)


if FLASK_AVAILABLE:
    import app as webapp
else:
    webapp = None


COURSE = {
    "schema_version": 1,
    "course_id": "cours-test-1234567890",
    "title": "Cours test",
    "source_filename": "cours.pdf",
    "file_hash": "a" * 64,
    "page_count": 4,
    "original_filename": "Cours test.pdf",
    "uploaded_at": None,
    "part_count": 2,
    "plan_available": True,
}


PLAN = {
    "plan_version": 1,
    "filename": "cours.pdf",
    "file_hash": "a" * 64,
    "page_count": 4,

    "parts": [
        {
            "id": "part-1",
            "number": "1",
            "title": "Introduction",
            "page_start": 1,
            "page_end": 2,

            "overview": {
                "status": "draft",
                "summary": (
                    "Résumé de la première partie."
                ),
                "key_concepts": [
                    "Notion A"
                ],
                "prerequisites": [],
                "why_important": "",
            },
        },

        {
            "id": "part-2",
            "number": "2",
            "title": "Suite",
            "page_start": 3,
            "page_end": 4,

            "overview": {
                "status": "pending",
            },
        },
    ],
}


@unittest.skipUnless(
    FLASK_AVAILABLE,
    "Flask non disponible dans cet environnement de test",
)
class AppNavigationTests(
    unittest.TestCase
):

    def setUp(self):

        webapp.app.config.update(
            TESTING=True
        )

        self.client = (
            webapp.app.test_client()
        )


    def test_home_is_chat_first_and_links_to_course(
        self,
    ):
        """
        La home moderne n'est plus un catalogue
        détaillé de cours.

        Elle doit présenter le chat principal tout
        en donnant accès aux vrais cours.
        """

        with patch.object(
            webapp.course_service,
            "list_courses",
            return_value=[COURSE],
        ):

            response = self.client.get(
                "/"
            )


        text = response.get_data(
            as_text=True
        )


        self.assertEqual(
            response.status_code,
            200,
        )


        self.assertIn(
            "Sur quoi veux-tu avancer",
            text,
        )


        self.assertIn(
            "Demander à StudyPilot",
            text,
        )


        self.assertIn(
            "Cours test",
            text,
        )


        self.assertIn(
            (
                "/course/"
                "cours-test-1234567890"
            ),
            text,
        )


        # Ancienne UI catalogue :
        # elle ne doit plus être requise.
        self.assertNotIn(
            "4 pages · 2 parties",
            text,
        )


    def test_course_route_opens_learning_path_and_question_still_opens_chat(self):
        with patch.object(webapp.course_service,'load_course',return_value=COURSE), patch.object(webapp.course_service,'load_course_plan',return_value=PLAN):
            response=self.client.get('/course/cours-test-1234567890')
            self.assertEqual(response.status_code,200)
            text=response.get_data(as_text=True)
            self.assertIn('data-course-panel',text)
            for label in ('Apprendre', 'Mes documents', 'Ma progression'):
                self.assertIn(label,text)
            self.assertIn('id="course-tutor"',text)
            self.assertIn('id="notions"',text)
            self.assertIn('Vérifier la couverture',text)
            question=self.client.get('/course/cours-test-1234567890?q=Pourquoi')
            self.assertEqual(question.status_code,302)
            self.assertTrue(question.headers['Location'].endswith('/part/1?q=Pourquoi'))

    def test_part_page_is_available(
        self,
    ):
        """
        Une vraie partie du cours reste directement
        accessible dans le workspace.
        """

        with (
            patch.object(
                webapp.course_service,
                "load_course",
                return_value=COURSE,
            ),
            patch.object(
                webapp.course_service,
                "load_course_plan",
                return_value=PLAN,
            ),
            patch.object(
                webapp.course_service,
                "load_part_cards",
                return_value=[],
            ),
        ):

            response = self.client.get(
                (
                    "/course/"
                    "cours-test-1234567890"
                    "/part/1"
                )
            )


        text = response.get_data(
            as_text=True
        )


        self.assertEqual(
            response.status_code,
            200,
        )


        self.assertIn(
            "Introduction",
            text,
        )


        self.assertIn(
            "Cours test",
            text,
        )


        self.assertNotIn(
            "plan-preview",
            text,
        )


    def test_revision_selects_requested_course_and_handles_empty_library(self):
        other = dict(COURSE, course_id='second-course', title='Second cours test')
        cases = [
            ([COURSE, other], 'second-course', 'second-course'),
            ([COURSE, other], 'unknown-course', COURSE['course_id']),
            ([], 'unknown-course', None),
        ]
        for courses, requested, expected in cases:
            with self.subTest(courses=len(courses), requested=requested):
                with patch.object(webapp.course_service, 'list_courses', return_value=courses):
                    response = self.client.get('/revision', query_string={'course_id': requested})
                self.assertEqual(response.status_code, 200)
                text = response.get_data(as_text=True)
                selected = re.findall(r'<option\s+value="([^"]+)"\s+selected', text)
                self.assertEqual(selected, [expected] if expected else [])
                if expected:
                    self.assertIn(f'/course/{expected}#documents', text)
                else:
                    self.assertIn('Ajoute un cours pour préparer une session.', text)


if __name__ == "__main__":
    unittest.main()
