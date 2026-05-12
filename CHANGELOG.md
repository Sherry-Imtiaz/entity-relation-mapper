# Entity Relation Mapper — Changelog

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
