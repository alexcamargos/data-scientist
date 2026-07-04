"""DataFrame column resolution helpers."""

from __future__ import annotations

import pandas as pd


def find_column(
    data: pd.DataFrame,
    candidates: tuple[str, ...],
    required_content: str | None = None,
) -> str:
    """Find a compatible column by normalized candidate names.

    Args:
        data: DataFrame whose columns should be searched.
        candidates: Candidate column names, before normalization.
        required_content: Optional lowercase text that must appear in at least
            one value of the matched column.

    Returns:
        Original DataFrame column name.

    Raises:
        ValueError: If no compatible column is found.
    """

    normalized_columns = {normalize_column(column): column for column in data.columns}
    for candidate in candidates:
        column = normalized_columns.get(normalize_column(candidate))
        if column and (
            required_content is None
            or data[column]
            .fillna("")
            .astype(str)
            .str.lower()
            .str.contains(required_content)
            .any()
        ):
            return column

    candidate_list = ", ".join(candidates)
    raise ValueError(
        f"Could not find a compatible column. Expected one of: {candidate_list}. "
        f"Available columns: {', '.join(map(str, data.columns))}"
    )


def optional_column(data: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    """Find an optional compatible column by normalized candidate names.

    Args:
        data: DataFrame whose columns should be searched.
        candidates: Candidate column names, before normalization.

    Returns:
        Original DataFrame column name when a candidate is present.
    """

    normalized_columns = {normalize_column(column): column for column in data.columns}
    for candidate in candidates:
        column = normalized_columns.get(normalize_column(candidate))
        if column:
            return column
    return None


def normalize_column(column: object) -> str:
    """Normalize a column name for candidate matching.

    Args:
        column: Raw column label.

    Returns:
        Lowercase snake_case-like column name.
    """

    return str(column).strip().lower().replace(" ", "_").replace("-", "_")
