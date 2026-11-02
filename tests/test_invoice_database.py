import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("invoice_database", ROOT / "resources/pwa_invoice_database.py")
database = importlib.util.module_from_spec(spec)
spec.loader.exec_module(database)


class InvoiceDatabaseTests(unittest.TestCase):
    def test_many_schema_queries_reuse_one_client_and_close_it_once(self):
        rest = Mock()
        rest.__enter__ = Mock(return_value=rest)
        rest.__exit__ = Mock(return_value=False)
        module = ModuleType('postgrest'); module.SyncPostgrestClient = Mock(return_value=rest)
        with patch.dict(sys.modules, {'postgrest': module}):
            with database.invoice_database('https://project.supabase.co', 'private-key') as client:
                for _ in range(40):
                    self.assertIs(client.schema('public'), rest)
                    client.schema('public').table('PWA_INVOICE_RAW')
                with self.assertRaises(ValueError): client.schema('settlement')
        module.SyncPostgrestClient.assert_called_once()
        rest.schema.assert_not_called()
        rest.__exit__.assert_called_once_with(None, None, None)

    def test_client_closed_when_query_raises(self):
        rest = Mock(); rest.__enter__ = Mock(return_value=rest); rest.__exit__ = Mock(return_value=False)
        module = ModuleType('postgrest'); module.SyncPostgrestClient = Mock(return_value=rest)
        with patch.dict(sys.modules, {'postgrest': module}):
            with self.assertRaises(TimeoutError):
                with database.invoice_database('https://project.supabase.co', 'private-key'):
                    raise TimeoutError('test query failed')
        self.assertIs(rest.__exit__.call_args.args[0], TimeoutError)


if __name__ == '__main__': unittest.main()
