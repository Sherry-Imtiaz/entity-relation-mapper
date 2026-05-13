from pathlib import Path

STATE_FILE = Path("erd_mapper_state.json")

APP_VERSION = "v2.2.14"
APP_VERSION_NAME = "Context-Safe IDs and Duplicate Relationship Handling"
APP_CHANGELOG = [
    {
        "version": "v2.2.14 Patch",
        "title": "Context-Safe IDs and Duplicate Relationship Handling",
        "changes": [
            "Added context-safe relationship IDs so identical connections can exist in different relationship contexts without overwriting each other.",
            "Added duplicate connection detection when adding relationships.",
            "Added duplicate handling options: do not add duplicate, add to this context anyway, or extract/use Shared Relationships context.",
            "Added relationship_duplicates.py for duplicate detection and whole database deduplication helpers.",
            "Preserved context-specific relationship views and exports."
        ],
    },
    {
        "version": "v2.2.13 Patch",
        "title": "Validation Fix, Clean Context Export, and Log Sorting",
        "changes": [
            "Fixed relationship validation summary call so it receives the application state instead of validation results.",
            "Fully rebuilt ui_export.py to remove older appended export code paths.",
            "Fully rebuilt ui_erd.py to remove older appended ERD code paths.",
            "Fully rebuilt ui_logs.py with sorting by timestamp, severity/log type, module, action, and message.",
            "Strengthened quality_checks.py table inference using normalised table matching.",
            "Preserved context-based export and ERD selection."
        ],
    },
    {
        "version": "v2.2.12 Patch",
        "title": "Context-Based ERD and Export Selection",
        "changes": [
            "Removed relationship multiselect controls from Export for ChatGPT.",
            "Removed relationship multiselect controls from ERD View.",
            "Added Relationship Context dropdown selection for Export for ChatGPT.",
            "Added Relationship Context dropdown selection for ERD View.",
            "Export and ERD now include all active relationships from the selected context.",
            "Kept table inference from context relationships to avoid zero-table context exports.",
            "Kept export log deduplication during Streamlit reruns."
        ],
    },
    {
        "version": "v2.2.11 Patch",
        "title": "Relationship Selection, Export Scope Fix, and Log Deduplication",
        "changes": [
            "Added relationship multiselect controls to Export for ChatGPT.",
            "Added relationship multiselect controls to ERD View.",
            "Added option to show only tables connected to selected relationships.",
            "Updated export quality checks to infer tables from selected relationships.",
            "Fixed cases where contexts with relationships but no assigned tables were reported as zero-table exports.",
            "Reduced repeated export warning logs during Streamlit reruns."
        ],
    },
    {
        "version": "v2.2.10 Patch",
        "title": "Streamlit Session State Warning Fix",
        "changes": [
            "Fixed Streamlit warning for manual_picklist_confidence being set through Session State and also given a widget default value.",
            "Initialised manual_picklist_confidence only when the Session State key is missing.",
            "Removed the explicit value argument from the confidence slider.",
            "Preserved dynamic relationship suggestion and auto-apply behaviour.",
            "Re-ran compile validation across the modular project files."
        ],
    },
    {
        "version": "v2.2.9 Patch",
        "title": "Dynamic Relationship Suggestion Controls",
        "changes": [
            "Updated relationship suggestions to react to the selected cardinality.",
            "Added auto-apply suggested join and confidence behaviour.",
            "Kept manual override available when auto-apply is disabled.",
            "Updated suggestion reasons to explain the selected cardinality and field analysis.",
            "Rebuilt ui_relationships.py to keep indentation stable."
        ],
    },
    {
        "version": "v2.2.8 Patch",
        "title": "Export Quality Helper Import Fix",
        "changes": [
            "Fixed NameError in ui_export.py where report_to_issue_rows was not available to the export quality panel helper.",
            "Moved the quality_checks imports to module scope where helper functions can access them.",
            "Preserved export readiness checklist and context completeness scoring.",
            "Re-ran compile validation across the modular project files."
        ],
    },
    {
        "version": "v2.2.7 Patch",
        "title": "Export Future Import Order Fix",
        "changes": [
            "Fixed ui_export.py import order so from __future__ import annotations appears at the top of the file.",
            "Removed duplicate future imports from ui_export.py if present.",
            "Preserved export quality checks and context completeness functionality.",
            "Re-ran compile validation across the modular project files."
        ],
    },
    {
        "version": "v2.2.6 Patch",
        "title": "Export Quality Checks and Context Completeness",
        "changes": [
            "Added quality_checks.py for export readiness analysis.",
            "Added export readiness checklist to the Export for ChatGPT tab.",
            "Added relationship completeness score and quality status label.",
            "Added detection for broken relationships, missing descriptions, disconnected tables, and missing conditional SQL.",
            "Added warning panel for incomplete exports without blocking export generation.",
            "Added optional logging for export quality reports and export generation."
        ],
    },
    {
        "version": "v2.2.5 Patch",
        "title": "Relationships Module Rebuild",
        "changes": [
            "Fully rebuilt ui_relationships.py to remove persistent indentation corruption.",
            "Backed up the previous ui_relationships.py before replacement.",
            "Preserved context-scoped relationship picklists.",
            "Preserved relationship guidance, suggested options, and Apply Suggested Options behaviour.",
            "Preserved relationship registry, validation display, update, and delete actions."
        ],
    },
    {
        "version": "v2.2.4 Patch",
        "title": "Relationship Guidance Indentation Fix",
        "changes": [
            "Fixed IndentationError in ui_relationships.py introduced by the relationship guidance patch.",
            "Replaced the manual relationship picklist form with a clean, consistently indented implementation.",
            "Preserved relationship suggestion guidance, Apply Suggested Options, and logging behaviour.",
            "Re-ran compile validation across the modular project files."
        ],
    },
    {
        "version": "v2.2.3 Patch",
        "title": "Relationship Guidance and Auto-Suggestions",
        "changes": [
            "Added relationship_guidance.py for relationship option recommendations.",
            "Added suggested cardinality, join type, and confidence guidance to the Relationships tab.",
            "Added an Apply Suggested Options button for manual relationship creation.",
            "Added warning guidance for same-table/self-join relationships.",
            "Added logging when suggested relationship options are applied.",
            "Preserved user control by not automatically overwriting relationship form selections."
        ],
    },
    {
        "version": "v2.2.2 Patch",
        "title": "Logs and Errors Page",
        "changes": [
            "Added logger.py for local JSON application logging.",
            "Added ui_logs.py for a Logs & Errors page.",
            "Added Logs & Errors tab to the main Streamlit app.",
            "Added severity, module, and search filters for log review.",
            "Added log download and clear-log actions.",
            "Added erm_error_log.json to .gitignore.",
            "Preserved existing app data model and saved-state compatibility."
        ],
    },
    {
        "version": "v2.2.1 Patch",
        "title": "Remove Residual Development UI Text",
        "changes": [
            "Removed remaining frontend text that referenced removed visual relationship creation.",
            "Removed remaining Streamlit Flow implementation wording from user-facing UI files where detected.",
            "Replaced internal implementation-history messages with clean user guidance.",
            "Preserved existing app behaviour and relationship data model."
        ],
    },
    {
        "version": "v2.2.0 Phase 1",
        "title": "UI Cleanup and Tooltips",
        "changes": [
            "Removed development-history wording from the frontend where detected.",
            "Added a Getting Started workflow guide in the app sidebar.",
            "Added a relationship field guide to the Relationships tab.",
            "Added contextual help text to relationship creation fields where possible.",
            "Improved ERD View wording so technical implementation details are less visible.",
            "Preserved existing relationship data model and saved-state compatibility."
        ],
    },
    {
        "version": "v2.1.7 Patch",
        "title": "ERD Visual Simplification",
        "changes": [
            "Removed Streamlit Flow as the active ERD visual component.",
            "Restored Graphviz as the main ERD visualisation.",
            "Kept Mermaid as text/export only.",
            "Updated Mermaid and Graphviz ERD output to show a maximum of 10 fields per table.",
            "Prioritised primary keys and ID/key-like fields in ERD table schema display.",
            "Removed streamlit-flow-component from requirements.txt."
        ],
    },
    {
        "version": "v2.1.6 Patch",
        "title": "Context-Based Manual Relationship Picklists",
        "changes": [
            "Added context-scoped source table dropdown for manual relationship creation.",
            "Added context-scoped target table dropdown for manual relationship creation.",
            "Added source and target column dropdowns based on the selected context tables.",
            "Added schema filters and table search fields for source and target picklists.",
            "Kept standard and conditional relationship creation in the same Relationships workflow.",
            "Restricted manual relationship creation to tables assigned to the active relationship context."
        ],
    },
    {
        "version": "v2.1.5 Patch",
        "title": "Literal Newline Escape Cleanup",
        "changes": [
            "Fixed config.py where literal backslash-n text was written into APP_CHANGELOG.",
            "Fixed ui_shared.py where literal backslash-n text was appended after a Streamlit warning call.",
            "Repaired Python source formatting after v2.1.4 helper patch.",
            "Re-ran compile validation across the modular project files."
        ],
    },
    {
        "version": "v2.1.4 Patch",
        "title": "UI Tables DataFrame Helper Fix",
        "changes": [
            "Fixed Tables tab failure caused by columns_df not being defined after UI module extraction.",
            "Added columns_df helper to ui_shared.py.",
            "Added tables_df helper to ui_shared.py for completeness.",
            "Preserved modular UI structure from v2.1.0 Phase 3."
        ],
    },
    {
        "version": "v2.1.3 Patch",
        "title": "Importer table_key Fix",
        "changes": [
            "Fixed schema import failure caused by table_key not being defined in importers.py.",
            "Added local table_key helper to importers.py so import logic no longer depends on UI helper modules.",
            "Preserved modular separation between import logic and UI helpers."
        ],
    },
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
