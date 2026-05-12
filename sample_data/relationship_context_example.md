# Relationship Context Example

## Context Name

Property Ownership Relations

## Context Type

Module Relation

## Purpose

Defines how properties are linked to associates through role-based association records.

## Business Context

CouncilWise / PropertyWise stores reusable association records that link people or organisations to different module items.
For property ownership and occupancy analysis, only association rows where `Item_Type = 3` should be interpreted as property links.

## Included Tables

- `PropertyWise.Properties`
- `PropertyWise.Associations_Role_Based`
- `PropertyWise.Associates`
- `PropertyWise.Association_Roles`
- `PropertyWise.Addresses`

## Primary Join Path

`Associations_Role_Based.Item_Id` → `Properties.Property_Id`

`Associations_Role_Based.Associate_Id` → `Associates.Associate_Id`

## Conditional Logic Notes

`src.Item_Type = 3` means the association row links to a property.

Other known examples:

| Item_Type | Meaning |
|---:|---|
| 3 | Property |
| 1039 | Regulatory Application |
| 1080 | Regulatory Entity |
| 1200 | Animal |

## Query Guidance

Use SELECT preview queries before inserting derived relationships into master link tables.
Always include discriminator conditions for conditional relationships.
