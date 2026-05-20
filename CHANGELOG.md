# Entity Relation Mapper — Changelog

## v2.2.24 Patch — Replace Deprecated Components HTML Viewer

### Fixed
- Replaced deprecated `st.components.v1.html` usage.
- Removed the Streamlit warning about `st.components.v1.html` being removed after 2026-06-01.

### Changed
- Dependency-free ERD viewer HTML is now loaded through `st.iframe()` using a base64 `data:text/html` URL.

### Preserved
- Dependency-free ERD viewer.
- White background.
- Zoom and pan.
- Reset and fit controls.
- Relationship-flow layout.
- Orthogonal / curved edge options.
- Relationship labels and condition labels.
- DOT and Mermaid downloads.

---

## v2.2.23 Patch — ERD Viewer CSS Brace Runtime Fix

### Fixed
- Fixed runtime error in `erd_rendering.py` caused by unescaped CSS braces inside the HTML f-string.
- Rebuilt the dependency-free ERD viewer template with correctly escaped CSS and JavaScript braces.

### Preserved
- Clean white background.
- Dependency-free ERD viewer.
- Zoom and pan.
- Reset and fit controls.
- Relationship-flow layout.
- Orthogonal / curved edge options.
- Relationship labels and condition labels.
- DOT and Mermaid downloads.

---

## v2.2.22 Patch — Dependency-Free ERD White Background Fix

### Fixed
- Restored the white background in the dependency-free ERD viewer.
- Removed the grey/checker/grid background from the ERD viewport.
- Added a consistent white canvas behind the diagram.

### Preserved
- Dependency-free rendering.
- Relationship-flow layout.
- Orthogonal / curved edge styling.
- Conditional relationship highlighting.
- Zoom and pan.
- Reset and fit controls.
- DOT and Mermaid downloads.

---

## v2.2.21 Patch — Dependency-Free ERD Routing and Visibility Fix

### Improved
- Dependency-free ERD table layout.
- Relationship line visibility.
- Arrowhead visibility.
- Conditional relationship highlighting.
- Label readability.
- Canvas padding to avoid clipping.

### Added
- Show relationship labels toggle.
- Show condition labels toggle.
- Edge style selector: Orthogonal / Curved.
- Table spacing selector: Compact / Comfortable / Wide.

### Preserved
- Dependency-free rendering.
- Zoom and pan.
- DOT download.
- Mermaid download.
- Static Streamlit Graphviz display mode.

---

## v2.2.20 Patch — Dependency-Free ERD Viewer Fallback

### Added
- Dependency-free interactive ERD viewer.
- Zoom in / zoom out, mouse-wheel zoom, click-and-drag pan, reset view, and fit to screen.

### Changed
- ERD View no longer depends on the Graphviz `dot` executable for its default interactive view.
- SVG/PNG server-side image downloads are disabled by default and documented as optional Graphviz-system features.

### Preserved
- Static Streamlit Graphviz display mode.
- DOT download.
- Mermaid download.
- Multi-context ERD selection.
- Conditional labels in dependency-free viewer labels.

---

## v2.2.19 Patch — Interactive Graphviz ERD Viewer

### Added
- Interactive Graphviz SVG viewer.
- Zoom in and zoom out controls.
- Mouse-wheel zoom.
- Click-and-drag pan.
- Reset view.
- Fit to screen.
- Display mode selector for Interactive viewer or Static Streamlit Graphviz.

### Preserved
- Multi-context ERD selection.
- Whole database ERD mode.
- Conditional labels.
- DOT, SVG, PNG, and Mermaid downloads.
- Static Graphviz fallback.

---

## v2.2.18 Patch — Manage Relationship Preview String Fix

### Fixed
- Fixed `SyntaxError: unterminated f-string literal` in `ui_relationships.py`.
- Replaced fragile newline f-string preview concatenation with `chr(10).join(...)`.

### Preserved
- Manage relationship conditional editing.
- Condition SQL editing.
- Extra Join SQL editing.
- Cardinality editing.
- Context-safe relationship ID regeneration.
- Duplicate detection on update.

---

## v2.2.17 Patch — Manage Relationship Conditional Editing

### Added
- Edit relationship mode from Manage relationship.
- Edit cardinality.
- Edit Condition SQL.
- Edit Extra Join SQL.
- Duplicate detection when edited relationship settings match another connection.
- Context-safe relationship ID regeneration when relationship type or condition changes.

### Fixed
- Existing relationships no longer need to be deleted/recreated just to change conditional logic.

### Preserved
- Active status editing.
- Join type editing.
- Confidence editing.
- Description editing.
- Delete relationship action.

---

## v2.2.16 Patch — Multi-Context ERD and Export Selection

### Added
- Whole database vs selected-context mode for ERD View.
- Whole database vs selected-context mode for Export for ChatGPT.
- Multi-select relationship context picker for ERD View.
- Multi-select relationship context picker for Export for ChatGPT.
- Multi-context quality checks.
- Context name attached to each relationship in Markdown and JSON exports.

### Preserved
- Conditional labels in Graphviz and Mermaid.
- Graphviz DOT/SVG/PNG downloads.
- Mermaid download.
- Active relationship filtering.
- Connected-table filtering.

---

## v2.2.15 Patch — Conditional Labels and Graphviz Image Downloads

### Added
- Conditional relationship text on Graphviz ERD labels.
- Conditional relationship text on Mermaid ERD labels.
- Graphviz DOT download.
- Graphviz SVG download.
- Graphviz PNG download.
- Mermaid ERD download.
- `erd_rendering.py` helper module.

### Preserved
- Relationship Context dropdown workflow.
- Context-specific ERD display.
- Whole database ERD display.
- Existing export behaviour.

---

## v2.2.14 Patch — Context-Safe IDs and Duplicate Relationship Handling

### Added
- Context-safe relationship IDs.
- Duplicate connection warning when adding a relationship.
- Duplicate handling options.
- Shared Relationships context support.
- Whole database relationship deduplication helpers.

### Fixed
- Identical source/target connections in different contexts no longer overwrite each other.

### Preserved
- Context-specific ERD and export behaviour.
- Relationship Context dropdown workflow.
- Existing saved relationships.

---

## v2.2.13 Patch — Validation Fix, Clean Context Export, and Log Sorting

### Fixed
- Fixed relationship validation error: `'DataFrame' object has no attribute 'relationships'`.
- Rebuilt `ui_export.py` so old export warning paths are removed.
- Rebuilt `ui_erd.py` so old ERD paths are removed.
- Strengthened table inference for context export quality checks.

### Added
- Sort Logs & Errors by timestamp, severity/log type, module, action, or message.
- Sort direction control.

### Preserved
- Relationship Context dropdowns for Export and ERD.
- Whole database option.
- Active relationship filtering.
- Graphviz ERD.
- Markdown, JSON, and Mermaid export options.

---

## v2.2.12 Patch — Context-Based ERD and Export Selection

### Changed
- Replaced relationship multiselect controls with Relationship Context dropdowns.
- Export for ChatGPT now exports the selected context instead of manually selected relationships.
- ERD View now displays the selected context instead of manually selected relationships.

### Preserved
- Table inference from context relationships.
- Whole database export option.
- Active relationship filtering.
- Graphviz ERD.
- Markdown, JSON, and Mermaid export options.
- Export log deduplication during Streamlit reruns.

---

## v2.2.11 Patch — Relationship Selection, Export Scope Fix, and Log Deduplication

### Added
- Relationship multiselect for Export for ChatGPT.
- Relationship multiselect for ERD View.
- Option to show only tables connected to selected relationships.
- Manual-only and conditional-only relationship presets.

### Fixed
- Export quality checks can infer tables from selected relationships.
- Contexts with relationships but empty/mismatched table assignment no longer automatically report zero included tables.
- Reduced repeated export warning logs during Streamlit reruns.

### Preserved
- Existing whole database export.
- Existing active context export.
- Existing Graphviz ERD.
- Existing Markdown, JSON, and Mermaid export options.

---

## v2.2.10 Patch — Streamlit Session State Warning Fix

### Fixed
- Removed duplicate default/session-state handling for `manual_picklist_confidence`.
- Prevented the Streamlit warning about a widget being created with a default value while also being set through Session State.

### Preserved
- Dynamic relationship suggestions.
- Auto-apply suggested join and confidence.
- Manual override workflow.
- Relationship registry and export workflows.

---

## v2.2.9 Patch — Dynamic Relationship Suggestion Controls

### Added
- Dynamic relationship suggestions based on selected cardinality.
- Auto-apply suggested join and confidence option.
- Manual override when auto-apply is disabled.

### Changed
- Suggested join now reacts to cardinality.
- Suggestion reason now explains both cardinality and field analysis.

### Preserved
- Context-scoped relationship picklists.
- Relationship registry.
- Existing ERD/export behaviour.

---

## v2.2.8 Patch — Export Quality Helper Import Fix

### Fixed
- Fixed `NameError: name 'report_to_issue_rows' is not defined` in `ui_export.py`.
- Made `report_to_issue_rows` available to `_render_export_quality_panel()`.

### Preserved
- Export readiness checklist.
- Relationship completeness score.
- Context quality summary.
- Existing export workflows.

---

## v2.2.7 Patch — Export Future Import Order Fix

### Fixed
- Fixed `ui_export.py` import order.
- Ensured `from __future__ import annotations` is the first executable line.
- Removed duplicate future imports if present.

### Preserved
- Export readiness checklist.
- Relationship completeness score.
- Context quality summary.
- Existing export workflows.

---

## v2.2.6 Patch — Export Quality Checks and Context Completeness

### Added
- `quality_checks.py`.
- Export readiness checklist.
- Relationship completeness score.
- Context quality summary.
- Warning panel for incomplete exports.
- Missing-description detection.
- Tables-without-relationships detection.
- Conditional relationship quality checks.

### Changed
- Export tab now provides quality guidance before exporting.
- Export remains user-controlled and does not block output.

### Preserved
- Existing Markdown, JSON, and Mermaid export workflows.
- Existing context-scoped export.
- Existing saved-state compatibility.

---

## v2.2.5 Patch — Relationships Module Rebuild

### Fixed
- Fully rebuilt `ui_relationships.py` to remove persistent indentation corruption.
- Backed up the previous file as `ui_relationships_pre_v2_2_5_backup.py`.

### Preserved
- Context-scoped relationship picklists.
- Relationship guidance and Apply Suggested Options.
- Relationship registry.
- Validation display.
- Update/delete relationship actions.

---

## v2.2.4 Patch — Relationship Guidance Indentation Fix

### Fixed
- Fixed `IndentationError` in `ui_relationships.py`.
- Replaced the affected manual relationship picklist form with a clean implementation.
- Preserved suggestion guidance and Apply Suggested Options behaviour.

---

## v2.2.3 Patch — Relationship Guidance and Auto-Suggestions

### Added
- `relationship_guidance.py`.
- Suggested cardinality, join type, and confidence recommendations.
- Relationship explanation panel.
- Apply Suggested Options button.
- Same-table/self-join warning.
- Logging when suggested options are applied.

### Preserved
- Existing manual relationship workflow.
- Existing conditional relationship workflow.
- Existing saved-state compatibility.
- Existing ERD/export behaviour.

---

## v2.2.2 Patch — Logs & Errors Page

### Added
- logger.py for local JSON application logging.
- ui_logs.py for the Logs & Errors page.
- Logs & Errors tab.
- Severity, module, and search filters.
- Download logs JSON button.
- Clear logs action.
- erm_error_log.json gitignore entry.

### Preserved
- Existing saved-state compatibility.
- Existing schema, relationship, ERD, and export workflows.

---

## v2.2.1 Patch — Remove Residual Development UI Text

### Fixed
- Removed remaining frontend text that referenced removed visual relationship creation.
- Removed residual Streamlit Flow implementation wording where detected.
- Replaced internal implementation-history messages with clean user-facing guidance.

---

## v2.2.0 Phase 1 — UI Cleanup and Tooltips

### Added
- Getting Started workflow guide in the sidebar.
- Relationship field guide in the Relationships tab.
- Tooltips/help text for manual relationship fields.

### Changed
- Removed development-history wording from the frontend where detected.
- Improved ERD View wording.
- Preserved existing relationship data model and saved-state compatibility.

---

## v2.1.7 Patch — ERD Visual Simplification

### Added
- Key/ID field prioritisation for Mermaid and Graphviz ERD output.
- Maximum 10 displayed fields per table in ERD schemas.

### Changed
- ERD View now uses Graphviz as the main visualisation.
- Mermaid and Graphviz ERDs are simplified to show relevant schema fields only.

### Removed
- Streamlit Flow visual component from the ERD View workflow.
- streamlit-flow-component dependency from requirements.txt.

---

## v2.1.0 Phase 4 — Stabilisation, Cleanup, and Packaging

### Added
- README.md with installation, run, structure, and workflow guidance.
- CHANGELOG.md.
- VERSION.md.
- .gitignore.
- sample_data/simple_schema_template.csv.
- sample_data/relationship_context_example.md.
- scripts/run_app.bat.
- scripts/run_app.ps1.
- scripts/compile_check.py.

### Changed
- Project structure finalised for the v2.1.0 modular release.
- App package is easier to run, check, share, and maintain.

### Preserved
- Existing app functionality.
- Existing saved-state compatibility.
- Existing Streamlit Flow ERD view.
- Existing import/export behaviour.

---

## v2.1.0 Phase 3 — UI Tab Extraction

### Added
- ui_contexts.py.
- ui_tables.py.
- ui_relationships.py.
- ui_inference.py.
- ui_erd.py.
- ui_export.py.
- ui_shared.py.

### Changed
- Streamlit tabs moved out of app.py.
- app.py reduced to a shell/orchestrator.

---

## v2.1.0 Phase 2 — Logic Module Extraction

### Added
- importers.py.
- validation.py.
- inference.py.
- exports.py.
- visualisation.py.

### Changed
- Import, validation, inference, export, and visualisation logic moved out of app.py.

---

## v2.1.0 Phase 1 — Core Structure Extraction

### Added
- config.py.
- models.py.
- state_manager.py.
- requirements.txt.

### Changed
- Version/changelog, data models, and state management extracted from the original single-file app.

---

## v2.0.5 Patch — Table-Style ERD Components

### Added
- Table-style Streamlit Flow ERD components.
- PK/KEY/normal field row markers.
- Improved table node spacing and compact layout.

---

## v2.0.4 Patch — Streamlit Flow ERD Visual Styling

### Added
- Improved ERD node readability.
- Key/ID field grouping.
- Cleaner table node styling.

---

## v2.0.3 Patch — Streamlit Flow ERD View

### Added
- Streamlit Flow interactive ERD visualisation in ERD View.

### Changed
- React Flow relationship creation removed from Relationships tab.
- Relationship creation remains form-based.

---

## v1.1.5 Patch — Unified Relationship Management

### Added
- Conditional relationship creation inside the Relationships workflow.
- Unified relationship editing.

### Removed
- Separate Conditional Links tab.

---

## v1.1.0 Phases 1–3 — Named Relationship Contexts

### Added
- Named relationship contexts.
- Context-scoped relationships.
- Context-scoped ERD/export.
- Validation dashboard.
- Import preview foundation.

---

## v1.0.0 — Baseline Release

### Added
- CSV/Excel import.
- Table and column viewer.
- Manual relationships.
- Inferred relationships.
- Conditional relationships.
- ERD view.
- Markdown/JSON/Mermaid exports.
- Local JSON state management.
