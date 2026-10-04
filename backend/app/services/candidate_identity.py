"""Compare candidate numbers without changing the original bulletin's spelling."""

from sqlalchemy import func


def candidate_key(number: str) -> str:
    return str(int(number))


def candidate_key_sql(column):
    # Text operations avoid overflow for the accepted 20-digit codes.
    return func.coalesce(func.nullif(func.ltrim(column, "0"), ""), "0")
