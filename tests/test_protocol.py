from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apache_incubator_reports_mcp import protocol


class ProtocolTests(unittest.TestCase):
    def test_initialize(self) -> None:
        response = protocol.handle_payload({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        if not isinstance(response, dict):
            self.fail("Expected initialize response to be a JSON-RPC object")

        self.assertEqual(response["result"]["serverInfo"]["name"], "apache-incubator-reports-mcp")

    def test_tools_list_includes_cache_tool(self) -> None:
        response = protocol.handle_payload({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        if not isinstance(response, dict):
            self.fail("Expected tools/list response to be a JSON-RPC object")
        names = {tool["name"] for tool in response["result"]["tools"]}

        self.assertIn("cache_all_reports", names)
        self.assertIn("get_report_due_dates", names)
        self.assertIn("get_report_due_dates_ical", names)


if __name__ == "__main__":
    unittest.main()
