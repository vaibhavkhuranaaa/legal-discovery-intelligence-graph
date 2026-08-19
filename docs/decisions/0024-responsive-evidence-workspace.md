# Decision 0024: Responsive evidence workspace

## Decision

Keep the existing Flask and Jinja interface, correct responsive behavior in the shared shell and design tokens, and adapt only the graph and timeline interactions that need view-specific controls. Mobile uses a native disclosure menu, single-column controls, 44 pixel touch targets, locally scrollable tables, wrapped evidence metadata, and a bounded graph canvas with a fit control. The search button exposes an in-progress label while the synchronous request runs.

## Why

The reported 1,107 pixel content width in a 375 pixel viewport came from shared non-wrapping navigation and desktop minimum widths, not from the retrieval or graph data contracts. Fixing those constraints once preserves the evidence pipeline and removes page-level overflow from every public route. The shared token correction also removes seven automated contrast violations without changing the established legal-technology visual direction.

## Alternatives rejected

- A new frontend framework was rejected because the existing server-rendered application already owns routing, states, and interaction contracts.
- A separate mobile application was rejected because it would duplicate information architecture and drift from the cited evidence workflow.
- Hiding graph, timeline, audit, or evaluation features on mobile was rejected because those are core verification paths.
- Page-level overflow clipping alone was rejected because it would conceal unreachable controls rather than fix layout constraints.

## Not done

No retrieval logic, threshold, citation, flag rule, corpus, evaluation artifact, backend, deployment, release pin, paid resource, or public visibility changed. Browser emulation does not replace physical iPhone, Android, Safari, or landscape testing. Plotly SVG contrast remains a manual review item because the automated audit cannot determine its composed background.

## Changed

The shared shell now provides responsive navigation, safe-area-aware spacing, focus treatment, touch sizing, and a search loading label. Evidence metadata wraps, tables scroll within their own container, the graph can fit to its viewport, and the timeline offers a direct citation-table path. Browser checks measured zero page-level overflow on all six routes at 390 pixels and on paired stakeholder and technical views at 1440 pixels.
