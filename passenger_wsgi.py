"""Adaptador WSGI do ATC LMS, para alojamento partilhado (cPanel "Setup Python App" / Passenger).

O atc_lms.py é um servidor HTTP próprio (BaseHTTPRequestHandler). Aqui cada pedido WSGI é entregue
ao mesmo Handler, sem socket: o Handler escreve a resposta num buffer, que é devolvido ao Passenger.
Os ficheiros (vídeos, imagens) são enviados aos bocados, sem os carregar inteiros em memória.

No cPanel: ficheiro de arranque = passenger_wsgi.py, ponto de entrada = application.
Variáveis de ambiente: ATC_DADOS (pasta gravável), ATC_ELEVEN_KEY (guia por voz).
"""
import io
import os
import sys
import urllib.parse
from http.client import HTTPMessage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import atc_lms  # noqa: E402

atc_lms.init_db()
atc_lms.seed_demo()

HOP_BY_HOP = {"connection", "keep-alive", "transfer-encoding", "server", "date"}


class WsgiHandler(atc_lms.Handler):
    """O Handler do LMS, alimentado por um ambiente WSGI em vez de um socket."""

    def __init__(self, environ):  # noqa: D107 (não chama o construtor do socketserver)
        self.environ = environ
        self.command = environ["REQUEST_METHOD"].upper()
        self.request_version = "HTTP/1.1"
        self.requestline = ""
        self.client_address = (environ.get("REMOTE_ADDR", ""), 0)
        uri = environ.get("REQUEST_URI")
        if not uri:
            uri = urllib.parse.quote((environ.get("SCRIPT_NAME", "") + environ.get("PATH_INFO", "/")).encode("latin-1"))
            if environ.get("QUERY_STRING"):
                uri += "?" + environ["QUERY_STRING"]
        self.path = uri
        self.headers = HTTPMessage()
        for k, v in environ.items():
            if k.startswith("HTTP_"):
                self.headers[k[5:].replace("_", "-").title()] = v
        for k in ("CONTENT_TYPE", "CONTENT_LENGTH"):
            if environ.get(k):
                self.headers[k.replace("_", "-").title()] = environ[k]
        self.rfile = environ["wsgi.input"]
        self.wfile = io.BytesIO()
        self.stream = None  # (caminho, início, fim) quando a resposta é um ficheiro

    def serve_file(self, path, download_name=None, ctype=None):
        # Envia só os cabeçalhos (como num HEAD); o corpo é lido do disco pelo servidor WSGI.
        command = self.command
        self.command = "HEAD"
        try:
            super().serve_file(path, download_name, ctype)
        finally:
            self.command = command
        if command != "HEAD":
            self.stream = path

    def run(self):
        method = "GET" if self.command == "HEAD" else self.command
        if method not in ("GET", "POST"):
            self.send(405, "", headers={"Allow": "GET, HEAD, POST"})
        else:
            self.dispatch(method)
        raw = self.wfile.getvalue()
        head, _, body = raw.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").split("\r\n")
        status = lines[0].split(" ", 1)[1]
        headers = []
        for line in lines[1:]:
            k, _, v = line.partition(":")
            if k.lower() not in HOP_BY_HOP:
                headers.append((k, v.strip()))
        return status, headers, body


def ficheiro(path, start, end, bloco=256 * 1024):
    with open(path, "rb") as f:
        f.seek(start)
        left = end - start + 1
        while left > 0:
            chunk = f.read(min(bloco, left))
            if not chunk:
                break
            left -= len(chunk)
            yield chunk


def application(environ, start_response):
    r = WsgiHandler(environ)
    status, headers, body = r.run()
    if environ.get("wsgi.url_scheme") == "https" or environ.get("HTTP_X_FORWARDED_PROTO") == "https":
        headers = [(k, v + "; Secure" if k.lower() == "set-cookie" else v) for k, v in headers]
    start_response(status, headers)
    if r.stream is None or r.command == "HEAD" or not status.startswith(("200", "206")):
        return [body]
    size = r.stream.stat().st_size
    start, end = 0, size - 1
    for k, v in headers:
        if k.lower() == "content-range":  # "bytes 100-199/1000"
            start, end = (int(x) for x in v.split(" ")[1].split("/")[0].split("-"))
    return ficheiro(r.stream, start, end)
