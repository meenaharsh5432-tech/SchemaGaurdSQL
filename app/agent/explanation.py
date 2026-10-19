def summarize_result(
    columns: list[str],
    rows: list[list[object]],
    *,
    cache_hit: bool,
) -> str:
    row_count = len(rows)

    if row_count == 0:
        summary = "The query returned no rows."
    elif row_count == 1 and len(columns) == 1:
        label = columns[0].replace("_", " ")
        value = rows[0][0]

        if value is None:
            summary = f"The query returned NULL for {label}."
        else:
            # Bound the amount of result text included in the summary.
            text = str(value)
            if len(text) > 120:
                text = text[:117] + "..."
            summary = f"The query returned {label}: {text}."
    else:
        noun = "row" if row_count == 1 else "rows"
        summary = f"The query returned {row_count} {noun}."

    summary += " Results reflect the query's filters and any row limit."

    if cache_hit:
        summary += " This response uses a cached result."

    return summary