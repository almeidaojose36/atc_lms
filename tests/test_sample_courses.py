"""Sample courses (Word, Excel, PowerPoint, Outlook) are open, complete and never issue certificates."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from test_personalisation import app

SAMPLES = ('word', 'excel', 'powerpoint', 'outlook')
COURSES = Path(app.COURSES_DIR)


class SampleCourseTests(unittest.TestCase):
    def test_packs_are_samples_with_a_manual_figures_and_quiz(self):
        for slug in SAMPLES:
            meta = json.loads((COURSES / slug / 'curso.json').read_text(encoding='utf-8'))
            self.assertEqual(meta['status'], 'amostra')
            mod = meta['modules'][0]
            manual = json.loads((COURSES / slug / mod['manual_json']).read_text(encoding='utf-8'))
            figures = [b['figure'] for s in manual['modules'][0]['sections'] for b in s['blocks'] if 'figure' in b]
            self.assertTrue(figures)
            for name in figures:
                self.assertTrue((COURSES / slug / mod['manual_figures'] / name).is_file(), (slug, name))
            questions = app.parse_gift((COURSES / slug / mod['quiz']['gift']).read_text(encoding='utf-8-sig'))
            self.assertGreaterEqual(len(questions), 6)
            for q in questions:
                self.assertIn(q['correct'], range(len(q['options'])))

    def test_sample_courses_are_open_to_any_signed_in_account(self):
        req = SimpleNamespace(is_staff=lambda: False, user={'id': 1}, con=None)
        self.assertTrue(app.Handler.can_access(req, {'status': 'amostra', 'id': 1}))

    def test_sample_courses_never_issue_certificates(self):
        con = SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchone=lambda: None))
        req = SimpleNamespace(course_for=lambda slug: {'status': 'amostra', 'id': 1}, con=con, user={'id': 1})
        with self.assertRaises(app.HttpError):
            app.cert_issue(req, 'word')

    def test_coming_soon_courses_stay_closed(self):
        meta = json.loads((COURSES / 'comptia-a-plus' / 'curso.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['status'], 'em_breve')
        req = SimpleNamespace(is_staff=lambda: False, user={'id': 1},
                              con=SimpleNamespace(execute=lambda *a, **k: SimpleNamespace(fetchone=lambda: None)))
        self.assertFalse(app.Handler.can_access(req, {'status': 'em_breve', 'id': 2}))


if __name__ == '__main__':
    unittest.main()
