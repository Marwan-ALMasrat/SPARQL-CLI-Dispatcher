"""
SPARQL CLI Dispatcher — publications ontology.
Usage:  python query.py "<intent>"
Example: python query.py "list authors at NeurIPS"
"""

import argparse
import sys
import requests

ENDPOINT = "http://localhost:3030/publications/sparql"

PREFIX = """
PREFIX :      <http://aispire.example.org/publications/>
PREFIX rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs:  <http://www.w3.org/2000/01/rdf-schema#>
PREFIX skos:  <http://www.w3.org/2004/02/skos/core#>
PREFIX xsd:   <http://www.w3.org/2001/XMLSchema#>
"""

# ---------------------------------------------------------------------------
# SPARQL queries (reused from Integration 9A)
# ---------------------------------------------------------------------------

QUERIES = {
    "list authors at neurips": {
        "type": "SELECT",
        "sparql": PREFIX + """
SELECT DISTINCT ?author
WHERE {
    ?paper :publishedIn :NeurIPS ;
           :authoredBy  ?author .
}
ORDER BY ?author
""",
        "columns": ["author"],
    },

    "papers per topic": {
        "type": "SELECT",
        "sparql": PREFIX + """
SELECT ?topic (COUNT(?paper) AS ?n)
WHERE {
    ?paper :topic ?topic .
}
GROUP BY ?topic
ORDER BY DESC(?n)
""",
        "columns": ["topic", "n"],
    },

    "top 5 cited": {
        "type": "SELECT",
        "sparql": PREFIX + """
SELECT ?paper ?cc
WHERE {
    ?paper :citationCount ?cc .
}
ORDER BY DESC(?cc)
LIMIT 5
""",
        "columns": ["paper", "cc"],
    },

    "coauthor pairs": {
        "type": "SELECT",
        "sparql": PREFIX + """
SELECT DISTINCT ?a ?b
WHERE {
    ?paper :authoredBy ?a ;
           :authoredBy ?b .
    FILTER (?a != ?b)
    FILTER (str(?a) < str(?b))
}
ORDER BY ?a ?b
""",
        "columns": ["a", "b"],
    },

    "papers with doi": {
        "type": "SELECT",
        "sparql": PREFIX + """
SELECT ?paper ?doi
WHERE {
    ?paper a :Paper .
    OPTIONAL { ?paper :doi ?doi . }
}
ORDER BY ?paper
""",
        "columns": ["paper", "doi"],
    },

    "any prolific author": {
        "type": "ASK",
        "sparql": PREFIX + """
ASK {
    SELECT ?author (COUNT(?paper) AS ?cnt)
    WHERE {
        ?paper :authoredBy ?author .
    }
    GROUP BY ?author
    HAVING (COUNT(?paper) > 10)
}
""",
        "columns": [],
    },

    "graph 2023 papers": {
        "type": "CONSTRUCT",
        "sparql": PREFIX + """
CONSTRUCT {
    ?paper :authoredBy ?author .
}
WHERE {
    ?paper a :Paper ;
           :year        2023 ;
           :authoredBy  ?author .
}
""",
        "columns": [],
    },

    "authors named hinton": {
        "type": "SELECT",
        "sparql": PREFIX + """
SELECT DISTINCT ?author
WHERE {
    ?author ?label "Hinton" .
    FILTER (?label = skos:prefLabel || ?label = skos:altLabel)
}
""",
        "columns": ["author"],
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short(uri: str) -> str:
    """Shorten a full URI to its local name prefixed with ':'."""
    for sep in ("#", "/"):
        if sep in uri:
            return ":" + uri.rsplit(sep, 1)[-1]
    return uri


def _run_select(sparql: str, columns: list) -> int:
    r = requests.get(
        ENDPOINT,
        params={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
        timeout=10,
    )
    r.raise_for_status()
    bindings = r.json()["results"]["bindings"]
    if not bindings:
        print("(no results)")
        return 0
    for row in bindings:
        parts = []
        for col in columns:
            val = row.get(col, {})
            raw = val.get("value", "(unbound)")
            parts.append(_short(raw) if val.get("type") == "uri" else raw)
        print("  ".join(parts))
    return 0


def _run_ask(sparql: str) -> int:
    r = requests.get(
        ENDPOINT,
        params={"query": sparql},
        headers={"Accept": "application/sparql-results+json"},
        timeout=10,
    )
    r.raise_for_status()
    result = r.json()["boolean"]
    print(str(result).lower())
    return 0


def _run_construct(sparql: str) -> int:
    r = requests.get(
        ENDPOINT,
        params={"query": sparql},
        headers={"Accept": "text/turtle"},
        timeout=10,
    )
    r.raise_for_status()
    lines = [ln for ln in r.text.splitlines() if ln.strip() and not ln.startswith("@prefix") and not ln.startswith("PREFIX")]
    print(f"({len(lines)} triples returned)")
    for ln in lines[:10]:
        print(" ", ln)
    if len(lines) > 10:
        print(f"  ... ({len(lines) - 10} more)")
    return 0


def _usage_banner() -> str:
    intents = "\n".join(f'  python query.py "{k}"' for k in sorted(QUERIES))
    return (
        "Unknown intent. Supported intents:\n"
        + intents
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def dispatch(intent: str) -> int:
    key = intent.strip().lower()
    if key not in QUERIES:
        print(_usage_banner(), file=sys.stderr)
        return 1

    entry = QUERIES[key]
    qtype = entry["type"]
    sparql = entry["sparql"]

    if qtype == "SELECT":
        return _run_select(sparql, entry["columns"])
    elif qtype == "ASK":
        return _run_ask(sparql)
    elif qtype == "CONSTRUCT":
        return _run_construct(sparql)
    else:
        print(f"Unsupported query type: {qtype}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Dispatch natural-language intents to SPARQL queries against the publications dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Supported intents:\n" + "\n".join(f'  "{k}"' for k in sorted(QUERIES)),
    )
    parser.add_argument("intent", help='Natural-language intent string, e.g. "top 5 cited"')
    args = parser.parse_args()
    sys.exit(dispatch(args.intent))


if __name__ == "__main__":
    main()
