import unittest

from resources.summary_document_labels import summary_document_text


class SummaryDocumentLabelsTest(unittest.TestCase):
    def test_saved_template_document_names_are_expanded(self):
        self.assertEqual(summary_document_text('A TIG-et a TIG-hez csatoljuk.'),
                         'A Teljesítés-összesítőt a Teljesítés-összesítőhöz csatoljuk.')

    def test_legacy_full_title_and_placeholders(self):
        self.assertEqual(summary_document_text('Teljesítési igazolás: {courier_name}'),
                         'Teljesítés-összesítő: {courier_name}')

    def test_internal_keys_are_unchanged_and_conversion_is_idempotent(self):
        text = 'tig_reference tig_done Teljesítés-összesítő'
        self.assertEqual(summary_document_text(summary_document_text(text)), text)

    def test_new_pdf_is_summary_without_acceptance_attestation(self):
        from datetime import date
        from io import BytesIO
        from pypdf import PdfReader
        from resources.settlement_pdf import build_tig_pdf
        for accepted in (False, True):
            pdf = build_tig_pdf(
                {'id': '1234', 'name': 'Minta Futár', 'document_month': date(2026, 10, 1),
                 'tig_type': 'AAM', 'tig_accepted': accepted, 'document_reference': '1234-TIG-202610'},
                {'payable': 250000, 'tip': 25000, 'cash': 15000})
            text = '\n'.join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages)
            self.assertIn('Teljesítés-összesítő', text)
            self.assertIn('250 000 Ft', text)
            for obsolete in ('TIG', 'elfogad', 'igazolás', 'hiteles', 'aláírás'):
                self.assertNotIn(obsolete, text)
