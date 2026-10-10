"""Sample access must never expose unrelated paid-course files."""
from pathlib import Path
from types import SimpleNamespace
import unittest
from test_personalisation import app


class InstructionExamplesTests(unittest.TestCase):
    def request(self):
        return SimpleNamespace(course_for=lambda slug, need_access=True: {'title': slug},
                               render=lambda title, body: body, serve_file=lambda path: path)

    def test_samples_require_authenticated_routes(self):
        for fn in (app.examples_page, app.example_image):
            matches = [role for _, _, handler, role in app.ROUTES if handler is fn]
            self.assertEqual(matches, ['user'])

    def test_only_declared_images_are_served(self):
        r = self.request()
        served = []
        r.serve_file = served.append
        for slug in ('word', 'excel', 'powerpoint'):
            data = app.instruction_examples(slug)
            for s in data['sections']:
                for b in s['blocks']:
                    if 'figure' in b:
                        app.example_image(r, slug, b['figure'])
                        self.assertTrue(served[-1].is_file())
            for filename in ('../../dados/atc.db', 'office-replica-excel.png', 'atc-formula-soma.jpg', 'exemplos-atc.json'):
                with self.assertRaises(app.HttpError):
                    app.example_image(r, slug, filename)

    def test_samples_render_figures_and_instruction_steps(self):
        for slug in ('word', 'excel', 'powerpoint'):
            body = app.examples_page(self.request(), slug)
            self.assertEqual(body.count('<figure>'), 2)
            self.assertEqual(body.count("<ol class='steps'>"), 2)
            self.assertIn('/amostras-office/'+slug+'/', body)

if __name__ == '__main__':
    unittest.main()
