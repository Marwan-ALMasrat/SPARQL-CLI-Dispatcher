# SPARQL CLI Dispatcher

A command-line tool that maps fixed natural-language intents to SPARQL queries against the `publications` ontology loaded in Apache Jena Fuseki.

This is a minimum-viable NL→formal-query dispatcher — a preview of the Week B integrated pipeline.

---

## Prerequisites

- Python 3.10+
- Docker (for Fuseki)
- The `publications` dataset loaded (from Integration 9A)

---

## Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/<your-username>/sparql-cli-dispatcher.git
cd sparql-cli-dispatcher

# 2. Install dependencies
pip install -r requirements.txt

# 3. Bring up Fuseki (reuse docker-compose.yml from Integration 9A)
docker compose up -d

# 4. Load the dataset (if not already loaded)
python load_dataset.py
```

---

## Usage

```bash
python query.py "<intent>"
```

### Example session

```
$ python query.py "list authors at NeurIPS"
:author000
:author001
:author100
...
(17 total)

$ python query.py "papers per topic"
:topic_self-supervised  5
:topic_summarization    3
:topic_interpretability 2
...

$ python query.py "top 5 cited"
:paper063  485
:paper043  475
:paper004  473
:paper007  470
:paper048  470

$ python query.py "any prolific author"
true

$ python query.py "graph 2023 papers"
(25 triples returned)
  <paper042> :authoredBy <author003> .
  ...

$ python query.py "unknown thing"
Unknown intent. Supported intents:
  python query.py "any prolific author"
  python query.py "authors named hinton"
  ...
```

---

## Intent → SPARQL Mapping

| Intent string | Query type | What it answers | Key SPARQL clauses |
|---|---|---|---|
| `list authors at neurips` | SELECT | All distinct authors with a paper at NeurIPS | `WHERE { ?paper :publishedIn :NeurIPS ; :authoredBy ?author }` |
| `papers per topic` | SELECT | Count of papers per research topic | `GROUP BY ?topic`, `COUNT(?paper) AS ?n` |
| `top 5 cited` | SELECT | Five papers with highest `:citationCount` literal | `ORDER BY DESC(?cc) LIMIT 5` |
| `coauthor pairs` | SELECT | All canonical unordered author–coauthor pairs | `SELECT DISTINCT`, `FILTER (str(?a) < str(?b))` |
| `papers with doi` | SELECT | Every paper + its DOI (unbound if missing) | `OPTIONAL { ?paper :doi ?doi }` |
| `any prolific author` | ASK | True if any author has > 10 papers | `ASK { ... HAVING (COUNT(?paper) > 10) }` |
| `graph 2023 papers` | CONSTRUCT | RDF graph of 2023 paper–author triples | `CONSTRUCT { ?paper :authoredBy ?author }` |
| `authors named hinton` | SELECT | Authors with "Hinton" as prefLabel or altLabel | `FILTER (?label = skos:prefLabel \|\| ?label = skos:altLabel)` |

---

## Running the tests

```bash
# Unit tests only (no Fuseki needed)
pytest tests/ -v

# Unit + integration tests (Fuseki must be running)
pytest tests/ -v -m integration
```

The test suite verifies:
- The registry contains ≥ 5 intents covering SELECT, ASK, and CONSTRUCT.
- Each SPARQL string contains the expected clauses (OPTIONAL, HAVING, LIMIT, etc.).
- An unknown intent exits non-zero and prints the usage banner to stderr.
- (Integration) Each intent returns exit code 0 against a live Fuseki instance.

---

## Design notes

### Intent matching
Intents are matched by exact lowercase string against a Python dict (`QUERIES` in `query.py`). This is intentionally simple — the goal is a clean NL→SPARQL reduction with no ambiguity, not fuzzy NLP matching. Week B replaces this dict lookup with an LLM-based dispatcher.

### Query reuse
The eight SPARQL strings are reused directly from Integration 9A. The dispatcher adds no new query logic — it adds the CLI layer, the intent registry, and the output formatting.

### Output formatting
- **SELECT** — one row per line, URI local names shortened to `:name`.
- **ASK** — prints `true` or `false`.
- **CONSTRUCT** — prints triple count + first 10 triples (prefix declarations stripped).

### Extending the dispatcher
To add a new intent, add one entry to the `QUERIES` dict in `query.py`:

```python
QUERIES["my new intent"] = {
    "type": "SELECT",          # SELECT | ASK | CONSTRUCT
    "sparql": PREFIX + """
SELECT ?x WHERE { ... }
""",
    "columns": ["x"],          # variable names in order for display
}
```

No other changes are needed — the dispatcher, help text, and test structure pick it up automatically.

---

## Requirements

```
requests>=2.31
pytest>=8.0
```

(See `requirements.txt`)
