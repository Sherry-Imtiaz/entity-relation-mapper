from pathlib import Path

STATE_FILE = Path("erd_mapper_state.json")

APP_VERSION = "v2.1.2"
APP_VERSION_NAME = "Graphviz Escape Sequence Fix"
APP_CHANGELOG = [
    {
        "version": "v2.1.2 Patch",
        "title": "Graphviz Escape Sequence Fix",
        "changes": [
            "Fixed invalid Python escape sequence in Graphviz DOT label generation.",
            "Replaced Graphviz left-aligned line breaks with escaped \\l sequences.",
            "Removed SyntaxWarning during compile checks for exports.py.",
            "Preserved existing Graphviz DOT export behaviour."
        ],
    },
    {
        "version": "v2.1.1 Patch",
        "title": "Phase 4 Config Newline Fix",
        "changes": [
            "Fixed config.py where Phase 4 packaging wrote a literal backslash-n into APP_CHANGELOG.",
            "Restored valid Python syntax for the in-code changelog.",
            "Re-ran compile validation across the modular project files."
        ],
    },
    {
        "version": "v2.1.0 Phase 4",
        "title": "Stabilisation, Cleanup, and Packaging",
        "changes": [
            "Added README.md with installation, run, structure, and workflow guidance.",
            "Added CHANGELOG.md with full project changelog summary.",
            "Added VERSION.md with current version metadata.",
            "Added .gitignore for Python, Streamlit state, virtual environments, and local exports.",
            "Added sample_data/simple_schema_template.csv.",
            "Added sample_data/relationship_context_example.md.",
            "Added Windows run scripts in scripts/run_app.bat and scripts/run_app.ps1.",
            "Added scripts/compile_check.py for lightweight compile validation.",
            "Preserved existing application functionality after modularisation."
        ],
    },
    {
        "version": "v2.1.0 Phase 3",
        "title": "UI Tab Extraction",
        "changes": [
            "Extracted the Relationship Contexts tab into ui_contexts.py.",
            "Extracted the Tables tab into ui_tables.py.",
            "Extracted the Relationships tab into ui_relationships.py.",
            "Extracted the Infer Links tab into ui_inference.py.",
            "Extracted the ERD View tab into ui_erd.py.",
            "Extracted the Export for ChatGPT tab into ui_export.py.",
            "Added ui_shared.py for shared UI helper functions.",
            "Reduced app.py to a cleaner Streamlit shell/orchestrator."
        ],
    },
    {
        "version": "v2.1.0 Phase 2",
        "title": "Logic Module Extraction",
        "changes": [
            "Extracted CSV and Excel import logic into importers.py.",
            "Extracted relationship validation and quality logic into validation.py.",
            "Extracted relationship inference logic into inference.py.",
            "Extracted Markdown, JSON, Mermaid, and Graphviz export logic into exports.py.",
            "Extracted Streamlit Flow ERD visualisation helpers into visualisation.py.",
            "Preserved existing UI behaviour while reducing app.py complexity."
        ],
    },
    {
        "version": "v2.1.0 Phase 1",
        "title": "Core Structure Extraction",
        "changes": [
            "Extracted app configuration, version constants, and changelog into config.py.",
            "Extracted ERD dataclass models into models.py.",
            "Extracted state serialization, save/load, and metadata merge helpers into state_manager.py.",
            "Created app.py as the new Streamlit entry point.",
            "Added requirements.txt for dependency tracking.",
            "Preserved existing UI behaviour from the pre-modularisation checkpoint."
        ],
    },
    {
        "version": "v2.0.5 Patch",
        "title": "Table-Style ERD Components",
        "changes": [
            "Changed Streamlit Flow ERD nodes from generic cards to database table-style components.",
            "Added compact column-row display using PK, key-like, and normal field markers.",
            "Improved table headers by separating schema and table names.",
            "Reduced visual clutter by using a compact ERD table format inside each node.",
            "Kept relationship edges and conditional edge labelling unchanged."
        ],
    },
    {
        "version": "v2.0.4 Patch",
        "title": "Streamlit Flow ERD Visual Styling",
        "changes": [
            "Improved Streamlit Flow table node readability and layout.",
            "Separated key/ID-like fields from other fields inside ERD nodes.",
            "Reduced oversized headings and improved metadata formatting.",
            "Increased node spacing to reduce overlap in the ERD view.",
            "Limited visible columns per node and added remaining-column counts.",
            "Improved node card styling for a cleaner ERD visualisation."
        ],
    },
    {
        "version": "v2.0.3 Patch",
        "title": "Streamlit Flow ERD View",
        "changes": [
            "Removed the React Flow visual relationship creation section from the Relationships tab.",
            "Kept relationship creation and editing form-based inside the Relationships tab.",
            "Added Streamlit Flow as an interactive ERD visualisation inside the ERD View tab.",
            "Used active named relationship context scoping for the Streamlit Flow ERD visualisation.",
            "Kept Graphviz and Mermaid text export available as supporting ERD outputs."
        ],
    },
    {
        "version": "v2.0.2 Patch",
        "title": "React Flow Node Content Syntax Fix",
        "changes": [
            "Fixed an unterminated string literal in the React Flow table node content builder.",
            "Replaced vulnerable newline string joins with chr(10).join(...) in the visual editor helper.",
            "Preserved the React Flow visual relationship editor inside the Relationships tab."
        ],
    },
    {
        "version": "v2.0.1 Patch",
        "title": "React Flow Visibility Fix",
        "changes": [
            "Made the Visual Relationship Builder section explicitly React Flow based inside the Relationships tab.",
            "Removed any Graphviz preview from the Relationships tab visual builder workflow.",
            "Kept Graphviz only in the separate ERD View tab.",
            "Added clearer guidance when streamlit-flow-component is not installed."
        ],
    },
    {
        "version": "v2.0.0 Phase 1",
        "title": "React Flow Visual Relationship Editor",
        "changes": [
            "Replaced the temporary Graphviz visual builder with a React Flow based visual relationship editor inside the Relationships tab.",
            "Added streamlit-flow-component as an optional dependency for interactive table nodes and relationship edges.",
            "Added context-scoped React Flow table nodes using assigned tables from the active named relationship context.",
            "Added existing context relationships as interactive visual edges.",
            "Kept form-assisted field selection for saving manual or conditional relationships into the active context.",
            "Preserved the standard Relationships form, validation dashboard, editing workflow, ERD view, and exports."
        ],
    },
    {
        "version": "v2.0.0 Phase 1",
        "title": "Visual Manual Relationship Editor",
        "changes": [
            "Added a visual relationship builder section inside the existing Relationships tab.",
            "Added context-scoped visual graph preview for assigned tables and existing relationships.",
            "Added visual/manual relationship creation using source and target table/field selection from the active context.",
            "Added optional Condition SQL and Extra Join SQL fields to the visual relationship creation workflow.",
            "Saved visually created relationships into the same relationship registry and active named relationship context.",
            "Kept the existing form-based relationship creation, validation dashboard, and editing workflow."
        ],
    },
    {
        "version": "v1.1.5 Patch",
        "title": "Unified Relationship Management",
        "changes": [
            "Moved conditional relationship creation into the main Relationships workflow.",
            "Added relationship mode selection for standard or conditional relationships.",
            "Added Condition SQL and Extra Join SQL fields to the main relationship creation form.",
            "Added relationship editing for active status, relationship type, join type, cardinality, condition SQL, extra join SQL, and description.",
            "Removed the separate Conditional Links tab from the main workflow.",
            "Kept existing conditional relationships backward compatible through relationship_type='conditional' and condition_sql."
        ],
    },
    {
        "version": "v1.1.5 Patch",
        "title": "Unified Relationship Management",
        "changes": [
            "Moved conditional relationship creation into the main Relationships workflow.",
            "Added relationship mode selection for standard or conditional relationships.",
            "Added Condition SQL and Extra Join SQL fields to the main relationship creation form.",
            "Added relationship editing for active status, relationship type, join type, cardinality, condition SQL, extra join SQL, and description.",
            "Removed the separate Conditional Links tab from the main workflow.",
            "Kept existing conditional relationships backward compatible through relationship_type='conditional' and condition_sql."
        ],
    },
    {
        "version": "v1.1.4 Patch",
        "title": "Changelog String Escape Fix",
        "changes": [
            "Fixed invalid Python syntax caused by unescaped quote characters inside changelog text.",
            "Corrected changelog wording for Streamlit width parameter replacements.",
            "Preserved v1.1.2 and v1.1.3 patch fixes."
        ],
    },
    {
        "version": "v1.1.3 Patch",
        "title": "Export Helper String Literal Fix",
        "changes": [
            "Fixed an unterminated string literal caused by newline join syntax in the context export helper.",
            "Replaced vulnerable newline string concatenation with chr(10)-based joins.",
            "Preserved the v1.1.2 Streamlit and UTC deprecation fixes."
        ],
    },
    {
        "version": "v1.1.2 Patch",
        "title": "Streamlit and UTC Deprecation Fixes",
        "changes": [
            "Replaced deprecated Streamlit use_container_width=True parameters with width='stretch'.",
            "Replaced deprecated Streamlit use_container_width=False pattern support with width='content' where applicable.",
            "Replaced deprecated datetime.utcnow() calls with timezone-aware datetime.now(UTC).",
            "Reduced command-line deprecation warnings when running the app on current Streamlit and Python versions.",
        ],
    },
    {
        "version": "v1.1.1 Patch",
        "title": "Phase 3 Syntax Fix",
        "changes": [
            "Fixed a syntax issue where a return statement could be interpreted outside a helper function after Phase 3 edits.",
            "Re-stabilised the context export and validation helper section.",
            "Maintained all previous v1.1.0 Phase 1, Phase 2, and Phase 3 changelog entries in code.",
        ],
    },
    {
        "version": "v1.1.0 Phase 3",
        "title": "Context Export, Validation, and Relationship Quality",
        "changes": [
            "Added context-scoped Markdown, JSON, and Mermaid exports.",
            "Added relationship validation and broken relationship detection.",
            "Added relationship quality dashboard metrics.",
            "Added import validation preview foundation for schema files.",
            "Added improved conditional relationship review/edit workflow.",
            "Added clearer custom naming and rename support for relationship contexts.",
        ],
    },
    {
        "version": "v1.1.0 Phase 2",
        "title": "Context-Scoped Relationships and ERD",
        "changes": [
            "Scoped manual relationships to the active named relationship context.",
            "Scoped inferred relationship suggestions to tables assigned to the active named relationship context.",
            "Scoped conditional relationships to the active named relationship context.",
            "Updated relationship registry display to show context names.",
            "Updated ERD view to optionally display only the active named relationship context.",
            "Maintained changelog history directly in the application code.",
        ],
    },
    {
        "version": "v1.1.0 Phase 1",
        "title": "Named Relationship Context Foundation",
        "changes": [
            "Added visible app versioning.",
            "Added named relationship context data model.",
            "Added relationship context management screen.",
            "Added schema-filtered and searchable table assignment for contexts.",
        ],
    },
    {
        "version": "v1.0.0",
        "title": "Baseline CSV/Excel ERD Mapper",
        "changes": [
            "Added CSV and Excel schema import.",
            "Added table and column viewer.",
            "Added manual, inferred, and conditional relationships.",
            "Added ERD view and ChatGPT-friendly Markdown/JSON export.",
        ],
    },
]
