# Demo Script (2 minutes)

> **Status: VERIFIED — live deployment.** Run against
> `https://legal-discovery-intelligence-graph.onrender.com`.

## Demo Outline

1. **(0–20s) Start on the case page (`/`)** — "eDiscovery is a story decoded from documents.
   Here's the matter, the corpus, and a guided tour." Point at the synthetic-data disclosure
   and the six tour steps.
2. **(20–50s) Run tour steps 1–2** — the award question (cited vector evidence, cosine
   scores) and the Reyes–Crestline relationship question (graph badges, open a graph
   evidence trail).
3. **(50–70s) Verify a citation** — click "view source document →" under an evidence card;
   the full stored document renders with its passages and privilege/PII flags.
4. **(70–90s) Run tour steps 4–6** — privilege badge on the audit/counsel material, PII badge
   on the HR record, then the trick question: calibrated refusal instead of weak matches.
5. **(90–110s) Timeline + entity graph** — the decoded chronology, every event cited and
   linked to its source.
6. **(110–120s) Credibility close** — Evaluation page (total model score with the honest
   hybrid-@10 regression) and `/audit` showing the searches just run.

## Recording Notes

- On a cold instance, wait for the first retrieval while the embedding model warms;
  subsequent searches are faster (a keep-alive workflow reduces cold starts).
- Do not present a generated conclusion: the product shows cited evidence only.
