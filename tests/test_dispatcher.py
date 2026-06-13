"""
tests/test_dispatcher.py
Verifies:
  - Each intent resolves to the correct SPARQL type and key columns.
  - An unknown intent exits non-zero and prints the usage banner.
  - The dispatch() function returns 0 for all known intents
    (integration tests — require a live Fuseki at localhost:3030).
"""

import pytest
import sys
import subprocess
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
sys.path.insert(0, ".")
from query import QUERIES, dispatch, _usage_banner


# ---------------------------------------------------------------------------
# Unit tests — no live Fuseki needed
# ---------------------------------------------------------------------------

class TestQueryRegistry:
    """Verify the intent registry structure."""

    def test_minimum_five_intents(self):
        assert len(QUERIES) >= 5, "Need at least 5 registered intents"

    def test_has_select(self):
        types = {v["type"] for v in QUERIES.values()}
        assert "SELECT" in types

    def test_has_ask(self):
        types = {v["type"] for v in QUERIES.values()}
        assert "ASK" in types

    def test_has_construct(self):
        types = {v["type"] for v in QUERIES.values()}
        assert "CONSTRUCT" in types

    def test_every_entry_has_sparql(self):
        for intent, entry in QUERIES.items():
            assert "sparql" in entry, f"Missing 'sparql' key for intent: {intent}"
            assert len(entry["sparql"]) > 20, f"SPARQL too short for intent: {intent}"

    def test_every_entry_has_type(self):
        for intent, entry in QUERIES.items():
            assert entry["type"] in ("SELECT", "ASK", "CONSTRUCT"), \
                f"Unknown type for intent: {intent}"

    def test_select_entries_have_columns(self):
        for intent, entry in QUERIES.items():
            if entry["type"] == "SELECT":
                assert "columns" in entry and len(entry["columns"]) >= 1, \
                    f"SELECT intent missing columns: {intent}"


class TestSparqlContent:
    """Verify SPARQL strings contain expected clauses."""

    def test_neurips_query_contains_publishedIn(self):
        q = QUERIES["list authors at neurips"]["sparql"]
        assert ":publishedIn" in q
        assert ":NeurIPS" in q

    def test_top5_query_contains_limit(self):
        q = QUERIES["top 5 cited"]["sparql"]
        assert "LIMIT 5" in q
        assert "ORDER BY DESC" in q

    def test_coauthor_pairs_has_canonical_filter(self):
        q = QUERIES["coauthor pairs"]["sparql"]
        assert "str(?a) < str(?b)" in q
        assert "DISTINCT" in q

    def test_papers_with_doi_has_optional(self):
        q = QUERIES["papers with doi"]["sparql"]
        assert "OPTIONAL" in q

    def test_ask_has_having(self):
        q = QUERIES["any prolific author"]["sparql"]
        assert "ASK" in q
        assert "HAVING" in q

    def test_construct_has_year_2023(self):
        q = QUERIES["graph 2023 papers"]["sparql"]
        assert "CONSTRUCT" in q
        assert "2023" in q

    def test_hinton_query_has_both_labels(self):
        q = QUERIES["authors named hinton"]["sparql"]
        assert "prefLabel" in q
        assert "altLabel" in q


class TestUsageBanner:
    """Verify the usage banner lists all intents."""

    def test_banner_contains_all_intents(self):
        banner = _usage_banner()
        for intent in QUERIES:
            assert intent in banner, f"Intent missing from banner: {intent}"

    def test_banner_starts_with_unknown_message(self):
        banner = _usage_banner()
        assert banner.startswith("Unknown intent")


class TestDispatchUnknownIntent:
    """Unknown intents must exit non-zero."""

    def test_dispatch_returns_1_for_unknown(self):
        result = dispatch("this is not a valid intent")
        assert result == 1

    def test_cli_exits_nonzero_for_unknown(self):
        result = subprocess.run(
            [sys.executable, "query.py", "totally unknown intent"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_cli_prints_usage_on_unknown(self):
        result = subprocess.run(
            [sys.executable, "query.py", "totally unknown intent"],
            capture_output=True,
            text=True,
        )
        assert "Unknown intent" in result.stderr
        assert "Supported intents" in result.stderr


# ---------------------------------------------------------------------------
# Integration tests — require live Fuseki at localhost:3030
# Mark with pytest.mark.integration; skip if Fuseki is down.
# Run with: pytest tests/ -v -m integration
# ---------------------------------------------------------------------------

import requests as _requests

def _fuseki_available():
    try:
        r = _requests.get("http://localhost:3030/$/ping", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


FUSEKI_UP = _fuseki_available()
skip_if_no_fuseki = pytest.mark.skipif(
    not FUSEKI_UP, reason="Fuseki not running at localhost:3030"
)


class TestDispatchLive:
    """Integration tests — fire real queries against Fuseki."""

    @skip_if_no_fuseki
    def test_neurips_authors_returns_rows(self):
        assert dispatch("list authors at neurips") == 0

    @skip_if_no_fuseki
    def test_papers_per_topic_returns_rows(self):
        assert dispatch("papers per topic") == 0

    @skip_if_no_fuseki
    def test_top5_cited_returns_rows(self):
        assert dispatch("top 5 cited") == 0

    @skip_if_no_fuseki
    def test_ask_returns_zero(self):
        assert dispatch("any prolific author") == 0

    @skip_if_no_fuseki
    def test_construct_returns_zero(self):
        assert dispatch("graph 2023 papers") == 0

    @skip_if_no_fuseki
    def test_coauthor_pairs_returns_rows(self):
        assert dispatch("coauthor pairs") == 0

    @skip_if_no_fuseki
    def test_papers_with_doi_returns_rows(self):
        assert dispatch("papers with doi") == 0

    @skip_if_no_fuseki
    def test_hinton_returns_rows(self):
        assert dispatch("authors named hinton") == 0
