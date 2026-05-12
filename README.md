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
