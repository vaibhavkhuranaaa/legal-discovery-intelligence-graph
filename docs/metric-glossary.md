# Metric glossary

## Extraction micro F1

The harmonic mean of precision and recall over entity mentions, aggregated across entity types. Strict matching requires the predicted mention span to match the gold span. The current 0.887 result is measured on the deterministic synthetic corpus and is not a field benchmark.

## Retrieval recall at 10

The fraction of relevant gold passages found within the first ten retrieved results, macro-averaged across the labeled query set. Hybrid retrieval currently records 0.857 on the dense synthetic corpus.

## Relationship hit rate at 5

The fraction of relationship questions with at least one relevant passage in the first five results. Graph expansion improves this measure from the 0.500 vector-only baseline to 0.833.

## Refusal accuracy

The fraction of answerable and negative gold queries correctly separated by the calibrated top cosine threshold. The current 0.868 result includes both false refusals and unsupported questions that were not refused.

## Mobile page overflow

The maximum document width beyond the browser viewport. The responsive release target is zero pixels across every public route at 390 pixels. This layout measure does not prove physical-device or browser compatibility.
