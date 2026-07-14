# Demo Script (90 seconds)

> **Status: VERIFIED — live deployment.** Run against
> `https://legal-discovery-intelligence-graph-ma2dfvnresf84ytk4nzelm.streamlit.app/`.

## Demo Outline

1. **(0–15s) Frame the problem** — "Discovery productions hide who did what, with whom, when.
   This app answers that with cited evidence."
2. **(15–40s) Ask an investigative question** — run “What connects Daniel Reyes to Northgate
   Supply Solutions?”; show ranked, cited hybrid evidence.
3. **(40–65s) Pivot into the graph** — expand an entity from the evidence; show the Neo4j
   subgraph connecting people, organizations, money, and documents.
4. **(65–80s) Timeline** — filter events by the key entity; show the case chronology.
5. **(80–90s) Credibility close** — evaluation page: precision/recall/F1, reproducible from the
   repo; synthetic-data disclosure.

## Recording Notes

- On a cold instance, wait for the first retrieval while the embedding model warms; subsequent
  searches are faster.
- Show the entity graph immediately after the chosen question, then the timeline and evaluation
  tabs. Do not present a generated conclusion: the product shows cited evidence only.
