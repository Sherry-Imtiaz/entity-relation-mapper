# Entity Relation Mapper

Current Version: **v2.1.0 Phase 4 — Stabilisation, Cleanup, and Packaging**

Entity Relation Mapper is a Streamlit-based tool for importing database schema metadata, defining named relationship contexts, managing manual/inferred/conditional relationships, visualising ERD relationships, and exporting structured database context for SQL/query generation.

## Key Features

- CSV and Excel schema import
- Optional direct database introspection support
- Named relationship contexts
- Context-scoped relationship mapping
- Manual, inferred, imported, explicit FK, and conditional relationships
- Relationship validation dashboard
- Import preview and validation
- Streamlit Flow ERD visualisation
- Graphviz fallback
- Mermaid text export
- ChatGPT-friendly Markdown export
- JSON export
- Local state save/load

## Installation

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

Windows helpers are also available:

```bash
scripts\run_app.bat
```

or:

```powershell
.\scripts\run_app.ps1
```

## File Structure

```text
erd_mapper_v2_1_0/
├── app.py
├── config.py
├── models.py
├── state_manager.py
├── importers.py
├── validation.py
├── inference.py
├── exports.py
├── visualisation.py
├── ui_shared.py
├── ui_contexts.py
├── ui_tables.py
├── ui_relationships.py
├── ui_inference.py
├── ui_erd.py
├── ui_export.py
├── requirements.txt
├── README.md
├── CHANGELOG.md
├── VERSION.md
├── .gitignore
├── sample_data/
│   ├── simple_schema_template.csv
│   └── relationship_context_example.md
└── scripts/
    ├── run_app.bat
    ├── run_app.ps1
    └── compile_check.py
```

## Basic Workflow

1. Import schema metadata from CSV or Excel.
2. Create a named relationship context.
3. Add relevant tables to the context.
4. Add manual or conditional relationships.
5. Use inference to suggest likely relationships where helpful.
6. Validate relationships.
7. Review the ERD View.
8. Export Markdown, JSON, Mermaid, or Graphviz DOT as needed.

## Import Format

The simplest CSV format is one row per column:

```csv
schema_name,table_name,column_name,data_type,nullable,is_primary_key,ordinal_position,row_count,module,purpose,notes,comment
PropertyWise,Properties,Property_Id,int,no,yes,1,10000,Property,Property master,Main property table,Primary key
```

A sample is available at:

```text
sample_data/simple_schema_template.csv
```

## Named Relationship Contexts

A relationship context represents a focused business or technical relationship group, such as:

- Property Ownership Relations
- Payment Relations
- Customer Relations
- Animal Registration Relations
- Regulatory Application Relations

Each context can have its own tables, comments, business guidance, and scoped exports.

## Validation

Run the lightweight compile check:

```bash
python scripts/compile_check.py
```

## Local State

The app stores local working state in:

```text
erd_mapper_state.json
```

This file is ignored by `.gitignore` by default.

## Rollback

Phase 4 creates:

```text
app_pre_v2_1_0_phase4_backup.py
```

Use this backup if you need to revert the `app.py` shell after Phase 4 packaging.


## Logs & Errors

The app records local troubleshooting events in `erm_error_log.json`. Use the Logs & Errors tab to filter, search, download, or clear log entries.


## Relationship Guidance

The Relationships tab can suggest cardinality, join type, and confidence values based on the selected source and target fields. Suggestions are user-controlled and only apply when you select **Apply suggested options**.


## Export Quality Checks

The Export for ChatGPT tab includes an export readiness checklist and completeness score. It highlights broken relationships, disconnected tables, missing relationship descriptions, and conditional relationships missing condition SQL before export.


## Dynamic Relationship Suggestions

The Relationships tab can suggest join type and confidence based on the selected cardinality and selected source/target fields. Enable **Auto-apply suggested join and confidence** to update those controls automatically, or turn it off for manual override.


## Streamlit Session State Warning Fix

The relationship confidence slider now uses Streamlit Session State without also passing a duplicate widget default value. This prevents repeated Streamlit warnings while preserving auto-apply suggested confidence behaviour.


## Relationship Selection for Export and ERD

The Export for ChatGPT and ERD View tabs include relationship multiselect controls. You can export or visualise all relationships, manual-only relationships, conditional-only relationships, or a custom selection. The app can also show only tables connected to selected relationships.


## Context-Based ERD and Export Selection

The Export for ChatGPT and ERD View tabs use Relationship Context dropdowns. Selecting a context includes all active relationships in that context and can infer the connected tables from relationship endpoints.


## v2.2.13 Validation Fix, Clean Export, and Log Sorting

This release rebuilds the Export, ERD, and Logs modules cleanly, fixes the relationship validation summary call, strengthens table inference for context exports, and adds log sorting by timestamp, severity/log type, module, action, and message.


## Context-Safe IDs and Duplicate Relationship Handling

Relationships now include context identity in their generated IDs, preventing identical table/column connections in different relationship contexts from overwriting each other. The app warns when a duplicate connection already exists in another context and offers duplicate handling options, including use of a Shared Relationships context.


## Conditional Labels and Graphviz Image Downloads

Graphviz and Mermaid ERD outputs now include conditional relationship text on relationship labels. ERD View provides downloads for DOT, SVG, PNG, and Mermaid. SVG/PNG rendering requires the Graphviz renderer to be installed on the machine running Streamlit.


## Multi-Context ERD and Export Selection

ERD View and Export for ChatGPT now support two modes: Whole database or Selected relationship contexts. In selected-context mode, choose multiple relationship contexts to visualise or export only those relationships and their connected tables.


## Manage Relationship Conditional Editing

Manage relationship now supports editing relationship mode, cardinality, Condition SQL, Extra Join SQL, active status, join type, confidence, and description. When conditional settings change, the relationship ID is regenerated using the context-safe ID format.


## Manage Relationship Preview String Fix

Fixed an unterminated f-string error in `ui_relationships.py` by rebuilding the Manage relationship preview using safe preview lines and `chr(10).join(...)`.


## Interactive Graphviz ERD Viewer

ERD View now includes an interactive SVG viewer for Graphviz diagrams. The viewer supports zoom in, zoom out, mouse-wheel zoom, click-and-drag pan, reset, and fit-to-screen. Static Streamlit Graphviz remains available as a display mode and fallback.


## Dependency-Free ERD Viewer Fallback

ERD View includes a dependency-free interactive HTML/SVG viewer that supports zoom and pan without requiring the Graphviz system executable. Static Streamlit Graphviz remains available, and DOT/Mermaid downloads remain available. SVG/PNG server-side image export requires optional Graphviz system installation.


## Dependency-Free ERD Routing and Visibility Fix

The dependency-free ERD viewer now uses relationship-flow layout, clearer orthogonal edges, stronger line styling, improved labels, conditional relationship highlighting, and display controls for labels, condition labels, edge style, and table spacing.


## Dependency-Free ERD White Background Fix

The dependency-free ERD viewer now uses a clean white viewport and canvas background. This removes the grey/checker/grid background while preserving zoom, pan, relationship-flow layout, clearer routing, labels, and DOT/Mermaid downloads.


## ERD Viewer CSS Brace Runtime Fix

Fixed a runtime error in the dependency-free ERD viewer caused by CSS braces being interpreted as Python f-string expressions. The viewer template has been rebuilt with safely escaped CSS and JavaScript braces while preserving the clean white background, routing, labels, zoom and pan controls, and DOT/Mermaid downloads.


## Replace Deprecated Components HTML Viewer

The dependency-free ERD viewer now renders through `st.iframe()` using a base64 HTML data URL instead of deprecated `st.components.v1.html`. This removes the Streamlit deprecation warning while preserving zoom, pan, routing, labels, white background, and DOT/Mermaid downloads.
