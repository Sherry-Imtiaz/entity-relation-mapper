# Entity Relation Mapper — Changelog

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
