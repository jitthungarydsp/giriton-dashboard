import subprocess
import unittest
from pathlib import Path


class DashboardInvoiceIssueTest(unittest.TestCase):
    def test_saved_reason_is_escaped_formatted_and_not_shown_for_paid_courier(self):
        source = (Path(__file__).resolve().parents[1] / "pwa/app.js").read_text(encoding="utf-8")
        start = source.index("function renderDashboardInvoiceIssue(")
        end = source.index("function renderSettlementDashboardExpanded(", start)
        script = "const assert=require('assert');const escapeHtml=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');\n"
        script += source[start:end]
        script += """
const row={status:{label:'Számla ellenőrzésre vár'},invoiceCheck:{note:'TIG: eltérés | Számla: 498602 Ft; TIG: 498489 Ft.\n<script>bad</script>',messages:['Hibás dátum']}};
const html=renderDashboardInvoiceIssue(row);
assert(html.includes('498602'));
assert(html.includes('<br><br>'));
assert(html.includes('Hibás dátum'));
assert(!html.includes('<script>'));
assert(html.includes('&lt;script&gt;'));
row.status.label='Kifizetve';
assert.equal(renderDashboardInvoiceIssue(row),'');
const missing=renderDashboardInvoiceIssue({status:{label:'Számla ellenőrzésre vár'}});
assert(missing.includes('Még nincs rögzített hibaindok'));
assert(missing.includes('önmagában nem jelenti'));
""".replace("Ft.\n<script>", "Ft.\\n<script>")
        result = subprocess.run(["node", "-e", script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
