"""Guia por voz: perguntas frequentes, cache de respostas e áudio pré-gerado (sem custos repetidos)."""
import unittest
from unittest import mock
from test_personalisation import app


class VoiceGuideTests(unittest.TestCase):
    def setUp(self):
        self.dados = app.voz_dados('informatica', 'aula-1-1')
        self.con = app.sqlite3.connect(':memory:')
        self.con.row_factory = app.sqlite3.Row
        self.con.executescript(app.SCHEMA)
        self.lesson = {'id': 1}

    def responder(self, q):
        with mock.patch.object(app, 'ollama_available', return_value=False):
            return app.voz_responder(self.con, self.lesson, None, 'informatica', self.dados, q)

    def test_spoken_variations_find_the_right_answer(self):
        casos = {'qual a diferença entre hardware e software': 'hardware-software',
                 'como é que eu desligo o computador': 'encerrar',
                 'como faço para entrar no windows': 'iniciar-sessao',
                 'o rato é hardware?': 'hardware',
                 'como abro o word': 'procurar-programa'}
        for q, esperado in casos.items():
            self.assertEqual(app.voz_procurar(q, self.dados)['id'], esperado, q)

    def test_off_topic_questions_go_to_the_trainer(self):
        for q in ('quanto custa o curso', 'qual é a capital de angola'):
            self.assertIsNone(app.voz_procurar(q, self.dados))
            self.assertEqual(self.responder(q), (self.dados['linhas']['nao_sei'], 'sem_resposta'))
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM voice_answers').fetchone()[0], 0)

    def test_answers_are_cached_and_reused(self):
        texto, fonte = self.responder('Como desligo o computador?')
        self.assertEqual(fonte, 'faq')
        self.assertEqual(self.responder('como desligo o computador'), (texto, 'cache'))
        self.assertEqual(self.con.execute('SELECT hits FROM voice_answers').fetchone()[0], 1)

    def test_silence_asks_to_repeat(self):
        self.assertEqual(self.responder(''), (self.dados['linhas']['nao_ouvi'], 'linha'))

    def test_lesson_1_2_answers_and_redirects_what_it_does_not_cover(self):
        dados = app.voz_dados('informatica', 'aula-1-2')
        self.assertEqual(app.voz_procurar('como é que eu crio uma pasta nova', dados)['id'], 'criar-pasta')
        self.assertEqual(app.voz_procurar('como abro o explorador', dados)['id'], 'explorador')
        for q in ('como copio um ficheiro', 'como mudo o nome de um ficheiro', 'como apago uma pasta'):
            self.assertIsNone(app.voz_procurar(q, dados), q)

    def test_every_answer_ships_with_audio_for_both_guides(self):
        textos = []
        for aula in ('aula-1-1', 'aula-1-2'):
            d = app.voz_dados('informatica', aula)
            textos += list(d['linhas'].values()) + [p['resposta'] for p in d['perguntas']]
        for guia in app.PRESENTERS:
            for t in textos:
                chave = app.voz_chave_audio(guia, t)
                self.assertIsNotNone(app.voz_ficheiro('informatica', guia, chave), (guia, t[:40]))
                self.assertEqual(app.voz_falar('informatica', guia, t), (chave, 0))   # nada a pagar

    def test_voice_key_is_not_in_the_code(self):
        self.assertEqual(app.ELEVEN_KEY, app.os.environ.get('ATC_ELEVEN_KEY', ''))


if __name__ == '__main__':
    unittest.main()
