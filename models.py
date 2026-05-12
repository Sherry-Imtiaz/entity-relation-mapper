from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Dict, List, Optional


@dataclass
class ColumnInfo:
    schema_name: str
    table_name: str
    column_name: str
    data_type: str = ""
    nullable: bool = True
    ordinal_position: int = 0
    is_primary_key: bool = False
    comment: str = ""

    @property
    def full_table(self) -> str:
        return f"{self.schema_name}.{self.table_name}" if self.schema_name else self.table_name


@dataclass
class TableInfo:
    schema_name: str
    table_name: str
    row_count: Optional[int] = None
    purpose: str = ""
    module: str = ""
    notes: str = ""
    columns: List[ColumnInfo] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        return f"{self.schema_name}.{self.table_name}" if self.schema_name else self.table_name


@dataclass
class Relationship:
    id: str
    source_schema: str
    source_table: str
    source_column: str
    target_schema: str
    target_table: str
    target_column: str
    context_id: str = ""
    relationship_type: str = "manual"  # explicit_fk, inferred, manual, conditional, imported
    cardinality: str = "many-to-one"   # one-to-one, one-to-many, many-to-one, many-to-many
    join_type: str = "LEFT JOIN"
    active: bool = True
    confidence: float = 1.0
    condition_sql: str = ""            # e.g. src.Item_Type = 3
    extra_join_sql: str = ""           # e.g. src.ValidTo IS NULL
    description: str = ""
    source_alias: str = "src"
    target_alias: str = "tgt"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def source_full_table(self) -> str:
        return f"{self.source_schema}.{self.source_table}" if self.source_schema else self.source_table

    @property
    def target_full_table(self) -> str:
        return f"{self.target_schema}.{self.target_table}" if self.target_schema else self.target_table

    def join_clause(self, left_alias: str = "src", right_alias: str = "tgt") -> str:
        base = (
            f"{self.join_type} {self.target_full_table} {right_alias} "
            f"ON {left_alias}.{self.source_column} = {right_alias}.{self.target_column}"
        )
        conditions = []
        if self.condition_sql.strip():
            conditions.append(self.condition_sql.strip())
        if self.extra_join_sql.strip():
            conditions.append(self.extra_join_sql.strip())
        if conditions:
            base += " AND " + " AND ".join(conditions)
        return base


@dataclass
class RelationshipContext:
    id: str
    name: str
    context_type: str = "Module Relation"
    purpose: str = ""
    business_context: str = ""
    included_tables: List[str] = field(default_factory=list)
    primary_join_path: str = ""
    conditional_logic_notes: str = ""
    query_guidance: str = ""
    comments: str = ""
    owner_reviewer: str = ""
    status: str = "Draft"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass
class ErdState:
    connection_label: str = ""
    database_name: str = ""
    loaded_at: str = ""
    tables: Dict[str, TableInfo] = field(default_factory=dict)
    relationships: Dict[str, Relationship] = field(default_factory=dict)
    relationship_contexts: Dict[str, RelationshipContext] = field(default_factory=dict)
    active_context_id: str = ""
