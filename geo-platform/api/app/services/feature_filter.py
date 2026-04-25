"""Injection-safe DSL expression compiler for feature attribute filtering.

All field names and values go through named SQL parameters — never interpolated
into query strings. Unknown ops or fields raise ValueError → 400 in the caller.
"""

ALLOWED_OPS: frozenset[str] = frozenset({
    "eq", "ne", "gt", "gte", "lt", "lte",
    "between", "contains", "starts_with", "ends_with",
    "in", "not_in", "is_null", "is_not_null",
})
BOOL_OPS: frozenset[str] = frozenset({"AND", "OR"})
MAX_DEPTH = 10
MAX_CONDITIONS = 50


def compile_expression(
    expr: dict,
    schema_fields: set[str],
    params: dict,
    prefix: str = "e",
    depth: int = 0,
    _counter: list[int] | None = None,
) -> str:
    """Recursively compile a DSL expression tree to a parameterized SQL clause.

    Returns a string such as:
        "(properties->>:e_f0 = :e_v0 AND (properties->>:e_f1)::numeric > :e_v1)"

    All field names go as values to `properties->>:f_N` — never interpolated.
    All comparison values go through `params[v_key]` — never interpolated.
    Raises ValueError on unknown op, unknown field, or depth/count limits.
    """
    if _counter is None:
        _counter = [0]

    if depth > MAX_DEPTH:
        raise ValueError(f"Expression too deeply nested (max {MAX_DEPTH} levels)")

    op = expr.get("op")

    if op in BOOL_OPS:
        conditions = expr.get("conditions")
        if not conditions or not isinstance(conditions, list):
            raise ValueError(f"Boolean op '{op}' requires a non-empty 'conditions' list")
        parts = [
            compile_expression(c, schema_fields, params, prefix, depth + 1, _counter)
            for c in conditions
        ]
        joiner = " AND " if op == "AND" else " OR "
        return f"({joiner.join(parts)})"

    if op not in ALLOWED_OPS:
        raise ValueError(f"Unknown op: {op!r}. Allowed: {sorted(ALLOWED_OPS)}")

    field = expr.get("field")
    if field not in schema_fields:
        raise ValueError(f"Unknown field: {field!r}")

    _counter[0] += 1
    if _counter[0] > MAX_CONDITIONS:
        raise ValueError(f"Too many conditions (max {MAX_CONDITIONS})")

    idx = _counter[0]
    f_key = f"{prefix}_f{idx}"
    v_key = f"{prefix}_v{idx}"
    params[f_key] = field  # field name is a param value, never interpolated

    # Helpers that build safe clauses — f_key and v_key are param names, not values
    def prop() -> str:
        return f"properties->>:{f_key}"

    def numeric_prop() -> str:
        return f"(properties->>:{f_key})::numeric"

    if op == "eq":
        params[v_key] = str(expr["value"])
        return f"({prop()} = :{v_key})"

    if op == "ne":
        params[v_key] = str(expr["value"])
        return f"({prop()} <> :{v_key})"

    if op in ("gt", "gte", "lt", "lte"):
        params[v_key] = expr["value"]
        op_sql = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
        return f"({numeric_prop()} {op_sql} :{v_key})"

    if op == "between":
        lo_key = f"{prefix}_lo{idx}"
        hi_key = f"{prefix}_hi{idx}"
        params[lo_key] = expr["lo"]
        params[hi_key] = expr["hi"]
        return f"({numeric_prop()} BETWEEN :{lo_key} AND :{hi_key})"

    if op == "contains":
        params[v_key] = f"%{expr['value']}%"
        return f"({prop()} ILIKE :{v_key})"

    if op == "starts_with":
        params[v_key] = f"{expr['value']}%"
        return f"({prop()} ILIKE :{v_key})"

    if op == "ends_with":
        params[v_key] = f"%{expr['value']}"
        return f"({prop()} ILIKE :{v_key})"

    if op == "in":
        values = expr["value"]
        if not isinstance(values, list) or not values:
            raise ValueError("'in' op requires a non-empty list value")
        any_keys = []
        for i, v in enumerate(values):
            k = f"{prefix}_v{idx}_{i}"
            params[k] = str(v)
            any_keys.append(f":{k}")
        return f"({prop()} = ANY(ARRAY[{', '.join(any_keys)}]))"

    if op == "not_in":
        values = expr["value"]
        if not isinstance(values, list) or not values:
            raise ValueError("'not_in' op requires a non-empty list value")
        all_keys = []
        for i, v in enumerate(values):
            k = f"{prefix}_v{idx}_{i}"
            params[k] = str(v)
            all_keys.append(f":{k}")
        return f"({prop()} <> ALL(ARRAY[{', '.join(all_keys)}]))"

    if op == "is_null":
        return f"({prop()} IS NULL)"

    if op == "is_not_null":
        return f"({prop()} IS NOT NULL)"

    raise ValueError(f"Unhandled op: {op!r}")
