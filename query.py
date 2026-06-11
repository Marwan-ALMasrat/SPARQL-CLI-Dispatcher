"""
query.py — SPARQL CLI Dispatcher
---------------------------------
Takes a fixed-vocabulary natural-language intent and dispatches
the matching SPARQL query against the publications Fuseki endpoint.

Usage:
    python query.py "list authors at NeurIPS"
    python query.py "papers per topic"
    python query.py "top 5 cited"
    python query.py --endpoint http://localhost:3030/publications "top 5 cited"
"""

import argparse
import sys
import textwrap
from typing import Optional

import requests

# ─── Fuseki endpoint (override via --endpoint) ───────────────────────────────
DEFAULT_ENDPOINT = "http://localhost:3030/publications/sparql"
DEFAULT_UPDATE   = "http://localhost:3030/publications/update"

# ─── Prefix block shared by all queries ──────────────────────────────────────
PREFIXES = """
PREFIX :    <http://example.org/pub#>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:<http://www.w3.org/2000/01/rdf-schema#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""

# ─── Intent → SPARQL registry ────────────────────────────────────────────────
# Each entry is a dict with:
#   "type"        : "SELECT" | "CONSTRUCT" | "ASK"
#   "description" : human-readable label
#   "query"       : the SPARQL string (without prefixes)
#   "keywords"    : list of substrings used for fuzzy matching

INTENTS: list[dict] = [
    # ── 1. SELECT — list authors affiliated with NeurIPS ─────────────────────
    {
        "name": "list authors at NeurIPS",
        "type": "SELECT",
        "description": "List all authors affiliated with the NeurIPS venue.",
        "keywords": ["author", "neurips"],
        "query": PREFIXES + """
SELECT DISTINCT ?author ?name
WHERE {
    ?author a :Author ;
            :affiliatedWith :venue_neurips ;
            :name ?name .
}
ORDER BY ?author
""",
    },

    # ── 2. SELECT — count papers per topic ───────────────────────────────────
    {
        "name": "papers per topic",
        "type": "SELECT",
        "description": "Count the number of papers for each topic.",
        "keywords": ["papers", "topic"],
        "query": PREFIXES + """
SELECT ?topic ?label (COUNT(?paper) AS ?paperCount)
WHERE {
    ?paper a :Paper ;
           :hasTopic ?topic .
    ?topic :topicLabel ?label .
}
GROUP BY ?topic ?label
ORDER BY DESC(?paperCount)
""",
    },

    # ── 3. SELECT — top N most-cited papers ──────────────────────────────────
    {
        "name": "top 5 cited",
        "type": "SELECT",
        "description": "List the top 5 papers by citation count.",
        "keywords": ["top", "cited"],
        "query": PREFIXES + """
SELECT ?paper ?title ?citationCount
WHERE {
    ?paper a :Paper ;
           :title ?title ;
           :citationCount ?citationCount .
}
ORDER BY DESC(?citationCount)
LIMIT 5
""",
    },

    # ── 4. SELECT — papers published at a given venue ────────────────────────
    {
        "name": "papers at ICML",
        "type": "SELECT",
        "description": "List all papers published at ICML.",
        "keywords": ["papers at icml", "icml papers", "icml"],
        "query": PREFIXES + """
SELECT ?paper ?title ?year
WHERE {
    ?paper a :Paper ;
           :title ?title ;
           :year ?year ;
           :publishedAt :venue_icml .
}
ORDER BY ?year ?title
""",
    },

    # ── 5. SELECT — authors with more than one paper ─────────────────────────
    {
        "name": "prolific authors",
        "type": "SELECT",
        "description": "List authors who have written more than one paper.",
        "keywords": ["prolific", "multiple papers", "more than one", "active authors"],
        "query": PREFIXES + """
SELECT ?author ?name (COUNT(?paper) AS ?paperCount)
WHERE {
    ?paper a :Paper ;
           :writtenBy ?author .
    ?author :name ?name .
}
GROUP BY ?author ?name
HAVING (COUNT(?paper) > 1)
ORDER BY DESC(?paperCount)
""",
    },

    # ── 6. CONSTRUCT — build a co-authorship subgraph ────────────────────────
    {
        "name": "coauthor graph",
        "type": "CONSTRUCT",
        "description": "Construct an RDF graph of co-authorship relationships.",
        "keywords": ["coauthor", "co-author", "graph", "construct"],
        "query": PREFIXES + """
CONSTRUCT {
    ?a1 :coAuthorWith ?a2 .
}
WHERE {
    ?paper a :Paper ;
           :writtenBy ?a1 ;
           :writtenBy ?a2 .
    FILTER (?a1 != ?a2)
    FILTER (STR(?a1) < STR(?a2))
}
""",
    },

    # ── 7. ASK — does any paper have more than 400 citations? ────────────────
    {
        "name": "any highly cited",
        "type": "ASK",
        "description": "Ask whether any paper has more than 400 citations.",
        "keywords": ["highly cited", "over 400", "400 citation", "any cited"],
        "query": PREFIXES + """
ASK
WHERE {
    ?paper a :Paper ;
           :citationCount ?c .
    FILTER (?c > 400)
}
""",
    },

    # ── 8. SELECT — papers in a given year ───────────────────────────────────
    {
        "name": "papers in 2023",
        "type": "SELECT",
        "description": "List all papers published in 2023.",
        "keywords": ["papers in 2023", "2023 papers", "year 2023"],
        "query": PREFIXES + """
SELECT ?paper ?title ?venue
WHERE {
    ?paper a :Paper ;
           :title ?title ;
           :year 2023 ;
           :publishedAt ?venue .
}
ORDER BY ?title
""",
    },
]

# ─── Intent matching ─────────────────────────────────────────────────────────

def match_intent(user_input: str) -> Optional[dict]:
    """
    Try to match the user's free-text input to a known intent.
    Strategy:
      1. Exact name match (case-insensitive)
      2. All keywords present in the input (substring, case-insensitive)
    Returns the intent dict, or None if no match.
    """
    lowered = user_input.lower().strip()

    # Pass 1 — exact name match
    for intent in INTENTS:
        if intent["name"].lower() == lowered:
            return intent

    # Pass 2 — all keywords match
    for intent in INTENTS:
        if all(kw in lowered for kw in intent["keywords"]):
            return intent

    return None


def supported_intents_table() -> str:
    """Return a formatted table of supported intents for the error banner."""
    lines = [
        "",
        "Supported intents:",
        f"  {'Intent name':<30}  {'Type':<10}  Description",
        "  " + "-" * 75,
    ]
    for intent in INTENTS:
        lines.append(
            f"  {intent['name']:<30}  {intent['type']:<10}  {intent['description']}"
        )
    return "\n".join(lines)

# ─── SPARQL execution ────────────────────────────────────────────────────────

def run_select(endpoint: str, query: str) -> list[dict]:
    """Execute a SELECT query and return list of binding dicts."""
    response = requests.get(
        endpoint,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    return data["results"]["bindings"]


def run_construct(endpoint: str, query: str) -> str:
    """Execute a CONSTRUCT query and return Turtle text."""
    response = requests.get(
        endpoint,
        params={"query": query},
        headers={"Accept": "text/turtle"},
        timeout=15,
    )
    response.raise_for_status()
    return response.text


def run_ask(endpoint: str, query: str) -> bool:
    """Execute an ASK query and return the boolean result."""
    response = requests.get(
        endpoint,
        params={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["boolean"]

# ─── Result formatting ───────────────────────────────────────────────────────

def format_bindings(bindings: list[dict]) -> str:
    """Pretty-print SELECT result bindings."""
    if not bindings:
        return "(no results)"
    lines = []
    for row in bindings:
        parts = []
        for var, cell in row.items():
            # Strip full URI to local name for readability
            value = cell["value"]
            if value.startswith("http://example.org/pub#"):
                value = ":" + value.split("#")[-1]
            parts.append(f"{value}")
        lines.append("  ".join(parts))
    return "\n".join(lines)

# ─── Main dispatcher ─────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="query.py",
        description="SPARQL CLI Dispatcher — natural-language → SPARQL → Fuseki",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(supported_intents_table()),
    )
    parser.add_argument(
        "intent",
        metavar="INTENT",
        help='Natural-language query intent (e.g. "top 5 cited")',
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        metavar="URL",
        help=f"SPARQL query endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the matched SPARQL query without executing it.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # ── Match intent ─────────────────────────────────────────────────────────
    intent = match_intent(args.intent)
    if intent is None:
        print(
            f"ERROR: Unknown intent → '{args.intent}'\n"
            + supported_intents_table(),
            file=sys.stderr,
        )
        return 1

    print(f"[{intent['type']}] {intent['name']} — {intent['description']}")

    # ── Dry-run: just show the query ─────────────────────────────────────────
    if args.dry_run:
        print("\n── SPARQL Query ──────────────────────────────────────────")
        print(intent["query"].strip())
        return 0

    # ── Execute ───────────────────────────────────────────────────────────────
    try:
        query_type = intent["type"]

        if query_type == "SELECT":
            bindings = run_select(args.endpoint, intent["query"])
            print(format_bindings(bindings))

        elif query_type == "CONSTRUCT":
            turtle = run_construct(args.endpoint, intent["query"])
            print(turtle)

        elif query_type == "ASK":
            result = run_ask(args.endpoint, intent["query"])
            print("YES" if result else "NO")

    except requests.exceptions.ConnectionError:
        print(
            f"ERROR: Cannot connect to Fuseki at '{args.endpoint}'.\n"
            "       Make sure Docker is running:  docker-compose up -d",
            file=sys.stderr,
        )
        return 2

    except requests.exceptions.HTTPError as exc:
        print(f"ERROR: Fuseki returned HTTP {exc.response.status_code}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
