"""Run: python3 -m unittest discover -s tests -v (from atc-lms)."""
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location('atc', Path(__file__).resolve().parents[1] / 'atc_lms.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class PersonalisationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_data, self.old_db = app.DATA_DIR, app.DB_PATH
        app.DATA_DIR = Path(self.temp.name)
        app.DB_PATH = app.DATA_DIR / 'test.db'
        app.init_db()
        self.con = app.db()
        app.import_all(self.con)
        self.uid = app.create_user(self.con, 'test@example.com', 'Nome Certificado', 'formando', 'password123')
        self.other = app.create_user(self.con, 'other@example.com', 'Outro Formando', 'formando', 'password123')
        self.c = self.con.execute("SELECT * FROM courses WHERE slug='informatica'").fetchone()
        self.con.execute('INSERT INTO enrolments VALUES(?,?,?)',(self.uid,self.c['id'],app.now()))
        self.r = SimpleNamespace(con=self.con,user=self.con.execute('SELECT * FROM users WHERE id=?',(self.uid,)).fetchone(),csrf='test-csrf',query={},data={})
        self.r.course_for = lambda slug: app.Handler.course_for(self.r,slug)
        self.r.can_access = lambda c: app.Handler.can_access(self.r,c)
        self.r.is_staff = lambda: False
        self.r.render = lambda title,body,**kwargs: app.page(title,body,self.r.user,self.r.csrf,profile=app.learner_profile(self.r),**kwargs)
        self.r.send = lambda code,body,*args,**kwargs: setattr(self.r,'response',(code,body))
        self.lesson = self.con.execute('SELECT * FROM lessons WHERE course_id=? ORDER BY sort LIMIT 1',(self.c['id'],)).fetchone()

    def tearDown(self):
        self.con.close()
        app.DATA_DIR,app.DB_PATH=self.old_data,self.old_db
        self.temp.cleanup()

    def choose(self,key):
        self.r.data={'presenter':key}
        with self.assertRaises(app.Redirect): app.presenter_save(self.r,'informatica')

    def test_idempotent_schema_and_existing_identity(self):
        self.con.commit();app.init_db();app.init_db()
        self.assertEqual(self.con.execute('SELECT name FROM users WHERE id=?',(self.uid,)).fetchone()[0],'Nome Certificado')
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM lessons').fetchone()[0],2)

    def test_profile_persists_escapes_and_preserves_certificate_name(self):
        self.r.data={'display_name':'<Ana>','occupation':'Administração','goal':'Aprender <Excel>','color':'green'}
        with self.assertRaises(app.Redirect): app.profile_save(self.r)
        self.con.commit()
        with app.db() as other: self.assertEqual(other.execute('SELECT display_name FROM learner_profiles WHERE user_id=?',(self.uid,)).fetchone()[0],'<Ana>')
        html=app.account(self.r)
        self.assertIn('&lt;Ana&gt;',html);self.assertIn('avatar-green',html)
        self.assertEqual(self.con.execute('SELECT name FROM users WHERE id=?',(self.uid,)).fetchone()[0],'Nome Certificado')
        self.assertIsNone(self.con.execute('SELECT * FROM learner_profiles WHERE user_id=?',(self.other,)).fetchone())

    def test_invalid_profile_rejected(self):
        for data in ({'display_name':' '},{'display_name':'a'*61},{'display_name':'Ana','color':'red;script'},{'display_name':'Ana','goal':'a'*301}):
            self.r.data=data
            with self.assertRaises(app.HttpError): app.profile_save(self.r)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM learner_profiles').fetchone()[0],0)

    def test_presenter_gate_change_and_account_isolation(self):
        with self.assertRaises(app.Redirect) as e: app.lesson_page(self.r,'informatica',self.lesson['slug'])
        self.assertTrue(e.exception.url.endswith('/apresentador'))
        self.choose('helena');self.assertEqual(app.selected_presenter(self.r,self.c['id']),'helena')
        self.assertIn('Olá, sou a Helena.',app.presenter_intro(self.r,'informatica'))
        self.choose('miguel');self.assertIn('Olá, sou o Miguel.',app.presenter_intro(self.r,'informatica'))
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM course_presenters').fetchone()[0],1)
        self.assertIsNone(self.con.execute('SELECT * FROM course_presenters WHERE user_id=?',(self.other,)).fetchone())

    def test_invalid_choice_and_unenrolled_course(self):
        self.r.data={'presenter':'../../bad'}
        with self.assertRaises(app.HttpError): app.presenter_save(self.r,'informatica')
        self.r.data={'presenter':'helena'}
        with self.assertRaises(app.HttpError) as e: app.presenter_save(self.r,'excel')
        self.assertEqual(e.exception.code,403)

    def test_fallback_and_optional_media(self):
        self.choose('helena')
        medium=app.lesson_media('informatica',self.lesson,'helena')
        self.assertEqual(medium['key'],'original')
        with patch.object(app,'ollama_available',return_value=False): html=app.lesson_page(self.r,'informatica',self.lesson['slug'])
        self.assertIn('Vídeo de demonstração comum',html)
        with patch.object(Path,'is_file',return_value=True),patch.object(app,'mp4_duration',return_value=75):
            medium=app.lesson_media('informatica',self.lesson,'helena')
        self.assertEqual(medium['key'],'helena');self.assertEqual(medium['duration'],75)
        self.assertEqual(medium['video'],'apresentadores/helena/aula-1-1.mp4')

    def test_variant_progress_does_not_mix_timelines(self):
        with patch.object(app,'lesson_media',side_effect=lambda slug,l,key:dict(key=key,duration=100)):
            for key,seen in [('helena','1'*50+'0'*50),('miguel','0'*50+'1'*50)]:
                self.r.data=dict(lesson=self.lesson['id'],media=key,pos=50,seen=seen,dur=100)
                app.progress_api(self.r)
                self.assertFalse(json.loads(self.r.response[1])['completed'])
            self.r.data=dict(lesson=self.lesson['id'],media='helena',pos=90,seen='1'*90+'0'*10,dur=100)
            app.progress_api(self.r);self.assertTrue(json.loads(self.r.response[1])['completed'])
            self.choose('miguel')
            self.assertEqual(app.course_progress(self.con,self.uid,self.c['id'])['lessons_done'],1)
            self.assertEqual(self.con.execute('SELECT COUNT(*) FROM presenter_progress').fetchone()[0],2)
            row=self.con.execute('SELECT position,seen FROM lesson_progress').fetchone()
            self.assertEqual(row['position'],0);self.assertEqual(row['seen'],'')

    def test_progress_rejects_nonfinite_values_and_missing_variant(self):
        for pos,key in [('nan','original'),('inf','original'),(5,'helena'),(5,'bad')]:
            self.r.data=dict(lesson=self.lesson['id'],media=key,pos=pos,seen='1'*200,dur=100)
            with self.assertRaises(app.HttpError): app.progress_api(self.r)

    def test_original_progress_and_script_assets(self):
        n=math.ceil(self.lesson['duration'])
        self.r.data=dict(lesson=self.lesson['id'],media='original',pos=3,seen='1'*3,dur=n)
        app.progress_api(self.r);self.assertFalse(json.loads(self.r.response[1])['completed'])
        self.r.data.update(pos=n,seen='1'*n)
        app.progress_api(self.r);self.assertTrue(json.loads(self.r.response[1])['completed'])
        scripts=json.loads((app.STATIC/'presenters/scripts.json').read_text())
        for key in app.PRESENTERS:
            self.assertTrue((app.STATIC/f'presenters/{key}.png').is_file())
            self.assertEqual(len(scripts[key]['courses']),7)

if __name__=='__main__': unittest.main()
