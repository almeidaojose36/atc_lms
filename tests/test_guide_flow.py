"""The chosen guide (Helena or Miguel) is global and personalises every screen."""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from test_personalisation import app

COURSES = Path(app.COURSES_DIR)
PLATFORM = Path(app.PLATAFORMA_DIR)


class GuideFlowTests(unittest.TestCase):
    def setUp(self):
        self.con = app.sqlite3.connect(':memory:')
        self.con.row_factory = app.sqlite3.Row
        self.con.executescript(app.SCHEMA)
        self.con.execute("INSERT INTO users(id,name,email,role,pw_hash,created) VALUES(1,'Ana','a@x','formando','x','2026')")
        self.r = SimpleNamespace(user={'id': 1, 'role': 'formando'}, con=self.con, data={}, query={}, csrf='t',
                                 is_staff=lambda: False, course_for=lambda slug, need_access=True: {'id': 1, 'slug': slug, 'title': slug})

    def test_choice_is_global_and_persists_across_courses(self):
        self.assertIsNone(app.selected_presenter(self.r))
        app.set_presenter(self.r, 'miguel')
        for cid in (1, 2, 99):
            self.assertEqual(app.selected_presenter(self.r, cid), 'miguel')
        app.set_presenter(self.r, 'helena')
        self.assertEqual(app.selected_presenter(self.r), 'helena')

    def test_old_per_course_choice_is_adopted(self):
        self.con.execute("INSERT INTO courses(id,slug,title,status,sort) VALUES(1,'informatica','Info','publicado',1)")
        self.con.execute("INSERT INTO course_presenters VALUES(1,1,'miguel','2026')")
        self.assertEqual(app.selected_presenter(self.r), 'miguel')
        self.assertEqual(self.con.execute("SELECT presenter FROM learner_presenter WHERE user_id=1").fetchone()[0], 'miguel')

    def test_onboarding_runs_in_order(self):
        order = [s for s, _ in app.ONBOARD]
        self.assertEqual(app.onboarding_next(self.r), 'guia')
        app.set_presenter(self.r, 'helena')
        for step in order[1:]:
            self.assertEqual(app.onboarding_next(self.r), step)
            app.onboarding_mark(self.r, step)
        self.assertIsNone(app.onboarding_next(self.r))

    def test_every_guide_has_every_clip_with_subtitles_and_no_burned_in_captions_file(self):
        flow = json.loads((COURSES / 'informatica' / 'apresentadores' / 'fluxo.json').read_text(encoding='utf-8'))
        course = set(flow['introducao']) | {flow['manual']} | {n for v in flow['aulas'].values() for n in v}
        for key in app.PRESENTERS:
            for name in app.ONBOARD_CLIP.values():
                for ext in ('mp4', 'vtt'):
                    self.assertTrue((PLATFORM / key / f'{name}.{ext}').is_file(), (key, name, ext))
            for name in course:
                for ext in ('mp4', 'vtt'):
                    self.assertTrue((COURSES / 'informatica' / 'apresentadores' / key / f'{name}.{ext}').is_file(), (key, name, ext))

    def test_clip_html_uses_player_subtitles_and_text(self):
        html = app.platform_clip_html('miguel', 'boas-vindas')
        self.assertIn('<track kind="subtitles"', html)
        self.assertIn('/plataforma/miguel/boas-vindas.mp4', html)
        self.assertIn('Miguel', html)
        self.assertNotIn('helena', html.lower())

    def test_manual_figures_follow_the_chosen_guide(self):
        blocks = [{'figure': 'a/helena.png', 'variants': {'helena': 'a/helena.png', 'miguel': 'a/miguel.png'}}]
        self.assertIn('a/miguel.png', app.render_blocks(blocks, '/f', 'miguel'))
        self.assertIn('a/helena.png', app.render_blocks(blocks, '/f', 'helena'))
        self.assertIn('a/helena.png', app.render_blocks(blocks, '/f', None))

    def test_next_url_must_stay_on_site(self):
        self.assertEqual(app.safe_next('//evil.example/x'), '/')
        self.assertEqual(app.safe_next('https://evil.example'), '/')
        self.assertEqual(app.safe_next('/cursos/word'), '/cursos/word')


if __name__ == '__main__':
    unittest.main()
