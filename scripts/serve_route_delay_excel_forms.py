"""Read the saved Excel row on every click and open its Google Form draft.

Local-only server. It never submits Google Forms or changes the workbook.
"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
from pathlib import Path
import socket
from urllib.parse import parse_qs, urlparse

spec = importlib.util.spec_from_file_location('route_drafts', Path(__file__).with_name('prepare_route_delay_forms.py'))
drafts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drafts)


def load_draft(workbook, key):
    import openpyxl
    book = openpyxl.load_workbook(workbook, read_only=True, data_only=True)
    try:
        rows = book['Űrlapok'].iter_rows(values_only=True)
        for values in rows:
            headers = [drafts.text(v) for v in values]
            if {'Forrássor', 'Futár ID', 'Dátum'}.issubset(headers):
                break
        else:
            raise ValueError('Az űrlaplista fejléce hiányzik vagy megváltozott.')
        found = []
        for values in rows:
            row = dict(zip(headers, values))
            if drafts.text(row.get('Forrássor')) == key:
                found.append(row)
        if len(found) != 1:
            raise ValueError('A forrássor nem található egyértelműen. A Forrássor oszlopot ne módosítsd.')
        row = found[0]
        if not row.get('Dátum'):
            raise ValueError('Hiányzik a dátum ennél a sornál. Add meg az Excel Dátum oszlopában, majd mentsd el (Ctrl+S).')
        row['Javasolt kategória száma'] = row.get('Kategória száma')
        row['Reklamáció indoklása'] = row.get('Végleges indoklás')
        # Re-read the template on each opening; a running local helper must not
        # keep serving a previous letter after its files have been updated.
        current = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(current)
        return current.prepare_row(row, int(key))
    finally:
        book.close()


def handler_for(workbook, token):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            target = urlparse(self.path)
            params = parse_qs(target.query)
            if not hmac.compare_digest(params.get('token', [''])[0], token):
                self.send_error(403, 'Use the link in your Excel workbook.')
                return
            try:
                if target.path != '/form':
                    raise ValueError('Az Excel Űrlap kitöltése hivatkozását használd.')
                draft = load_draft(workbook, params.get('key', [''])[0])
                self.send_response(302)
                self.send_header('Location', draft['prefill_url'])
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.end_headers()
            except Exception as exc:
                message = str(exc) if isinstance(exc, ValueError) else 'Az Excel nem olvasható. Mentsd el, és próbáld újra.'
                body = ('<!doctype html><meta charset="utf-8"><h1>Űrlap nem nyílt meg</h1><p>'
                        + drafts.html.escape(message) + '</p><p>Nem történt beküldés.</p>').encode('utf-8')
                self.send_response(400)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *args):
            # Do not log the local access token or complaint data.
            pass
    return Handler


class LocalFormServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workbook', type=Path, required=True)
    parser.add_argument('--settings', type=Path, required=True)
    parser.add_argument('--check', action='store_true', help='Check files and workbook without starting the server.')
    args = parser.parse_args()
    config = json.loads(args.settings.read_text(encoding='utf-8'))
    if args.check:
        import openpyxl
        book = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
        try:
            if 'Űrlapok' not in book.sheetnames:
                raise ValueError('Az Excelben nincs Űrlapok munkalap.')
            print('Ellenorzes OK. Excel: ' + str(args.workbook), flush=True)
        finally:
            book.close()
        return
    server = LocalFormServer(('127.0.0.1', int(config['port'])), handler_for(args.workbook, config['token']))
    print('Az Excel-urlapkitolto fut. Hagyd nyitva ezt az ablakot.', flush=True)
    print('Excel modositasa > Ctrl+S > Urlap kitoltese. Leallitas: Ctrl+C.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
