"""End-to-end demo: ask three example questions against the running API.

Run via ``make demo`` (which brings the stack up and ingests the corpus first).
Posts each question to ``POST /ask`` and prints the answer with its citations,
then prints the ``/metrics`` summary. Targets the ``API_URL`` env var
(default ``http://api:8000`` for use inside the compose network).
"""

from __future__ import annotations

import os

import httpx

QUESTIONS = [
    "How does vector search work in Elasticsearch?",
    "What is reciprocal rank fusion and how does hybrid search combine results?",
    "How should I chunk documents before indexing them for retrieval?",
]


def main() -> None:
    base_url = os.environ.get("API_URL", "http://api:8000").rstrip("/")
    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        for i, question in enumerate(QUESTIONS, start=1):
            print(f"\n{'=' * 78}\n[{i}] {question}\n{'=' * 78}")
            resp = client.post("/ask", json={"query": question, "k": 6})
            if resp.status_code != 200:
                print(f"  ERROR {resp.status_code}: {resp.text[:200]}")
                continue
            body = resp.json()
            status = "ANSWERED" if body["answered"] else "INSUFFICIENT EVIDENCE"
            print(f"  [{status}] {body['answer']}")
            for claim in body.get("claims", []):
                cites = ", ".join(claim["citations"]) or "(none)"
                print(f"    - {claim['text']}  [{cites}]")

        print(f"\n{'=' * 78}\nMETRICS\n{'=' * 78}")
        metrics = client.get("/metrics")
        if metrics.status_code == 200:
            for key, value in metrics.json().items():
                print(f"  {key}: {value}")
        else:
            print(f"  ERROR {metrics.status_code}: {metrics.text[:200]}")


if __name__ == "__main__":
    main()
