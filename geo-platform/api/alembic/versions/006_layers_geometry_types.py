"""Replace layers.geometry_type (scalar) with layers.geometry_types (array, derived)

Revision ID: 006
Revises: 005
Create Date: 2026-04-17

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE layers ADD COLUMN geometry_types TEXT[];")
    op.execute("""
        UPDATE layers
        SET geometry_types = ARRAY[UPPER(geometry_type)]
        WHERE geometry_type IS NOT NULL;
    """)
    op.execute("UPDATE layers SET geometry_types = '{}' WHERE geometry_types IS NULL;")
    op.execute("ALTER TABLE layers ALTER COLUMN geometry_types SET NOT NULL;")
    op.execute("ALTER TABLE layers ALTER COLUMN geometry_types SET DEFAULT '{}';")
    op.execute("""
        ALTER TABLE layers ADD CONSTRAINT layers_geometry_types_valid CHECK (
            geometry_types <@ ARRAY['POINT','LINESTRING','POLYGON',
                                    'MULTIPOINT','MULTILINESTRING','MULTIPOLYGON']
            AND (
                array_length(geometry_types, 1) IS NULL
                OR array_length(geometry_types, 1) = (
                    SELECT count(DISTINCT x) FROM unnest(geometry_types) AS x
                )
            )
        );
    """)
    op.execute("CREATE INDEX layers_geometry_types_idx ON layers USING GIN(geometry_types);")
    op.execute("ALTER TABLE layers DROP COLUMN geometry_type;")


def downgrade() -> None:
    op.execute("ALTER TABLE layers ADD COLUMN geometry_type TEXT;")
    op.execute("""
        UPDATE layers
        SET geometry_type = geometry_types[1]
        WHERE array_length(geometry_types, 1) >= 1;
    """)
    op.execute("UPDATE layers SET geometry_type = 'POINT' WHERE geometry_type IS NULL;")
    op.execute("ALTER TABLE layers ALTER COLUMN geometry_type SET NOT NULL;")
    op.execute("DROP INDEX IF EXISTS layers_geometry_types_idx;")
    op.execute("ALTER TABLE layers DROP CONSTRAINT IF EXISTS layers_geometry_types_valid;")
    op.execute("ALTER TABLE layers DROP COLUMN geometry_types;")
