"""
Column header mapping logic: matches messy clinic export headers against YAML aliases.
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional
import pandas as pd
from src.continuum.config import get_mapping


def build_alias_lookup(mapping_dict: Dict[str, Any]) -> Dict[str, str]:
    """
    Builds a case-insensitive lookup table mapping every known alias to its canonical field name.
    """
    lookup: Dict[str, str] = {}
    
    for section, fields in mapping_dict.items():
        if not isinstance(fields, dict):
            continue
        for canonical_name, aliases in fields.items():
            # Add canonical name itself as alias
            lookup[canonical_name.strip().lower()] = canonical_name
            if isinstance(aliases, list):
                for alias in aliases:
                    lookup[str(alias).strip().lower()] = canonical_name
                    
    return lookup


def map_dataframe_columns(
    df: pd.DataFrame, 
    mapping_name: str = "mapping_ramraksha.yaml"
) -> pd.DataFrame:
    """
    Renames DataFrame columns to canonical names using the specified mapping YAML.
    Preserves unmapped columns as-is.
    """
    mapping_data = get_mapping(mapping_name)
    alias_lookup = build_alias_lookup(mapping_data)
    
    column_rename_map: Dict[str, str] = {}
    for col in df.columns:
        col_clean = str(col).strip().lower()
        if col_clean in alias_lookup:
            column_rename_map[col] = alias_lookup[col_clean]

    return df.rename(columns=column_rename_map)
