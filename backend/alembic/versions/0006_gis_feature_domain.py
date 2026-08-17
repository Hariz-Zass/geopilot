"""project-owned GIS feature ingestion domain

Revision ID: 0006
Revises: 0005
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from app.db.spatial import Geometry4326

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gis_features",
        sa.Column("id",sa.Uuid(),nullable=False),
        sa.Column("project_id",sa.Uuid(),nullable=False),
        sa.Column("layer_id",sa.Uuid(),nullable=False),
        sa.Column("source_feature_id",sa.String(length=512),nullable=True),
        sa.Column("geometry",Geometry4326(),nullable=False),
        sa.Column("geometry_type",sa.String(length=32),nullable=False),
        sa.Column("geometry_hash",sa.String(length=64),nullable=False),
        sa.Column("properties",sa.JSON(),nullable=False),
        sa.Column("is_archived",sa.Boolean(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["project_id"],["projects.id"],name=op.f("fk_gis_features_project_id_projects"),ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["layer_id"],["gis_layers.id"],name=op.f("fk_gis_features_layer_id_gis_layers"),ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id",name=op.f("pk_gis_features")),
    )
    op.create_index(op.f("ix_gis_features_project_id"),"gis_features",["project_id"],unique=False)
    op.create_index(op.f("ix_gis_features_layer_id"),"gis_features",["layer_id"],unique=False)
    op.create_index("ix_gis_features_geometry_gist","gis_features",["geometry"],unique=False,postgresql_using="gist")
    op.create_check_constraint("geometry_type_allowed","gis_features","geometry_type IN ('Point','MultiPoint','LineString','MultiLineString','Polygon','MultiPolygon')")
    op.create_check_constraint("geometry_hash_shape","gis_features","geometry_hash ~ '^[0-9a-f]{64}$'")
    op.create_check_constraint("geometry_valid","gis_features","ST_SRID(geometry) = 4326 AND NOT ST_IsEmpty(geometry) AND ST_IsValid(geometry)")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_gis_features_geometry_valid"),"gis_features",type_="check")
    op.drop_constraint(op.f("ck_gis_features_geometry_hash_shape"),"gis_features",type_="check")
    op.drop_constraint(op.f("ck_gis_features_geometry_type_allowed"),"gis_features",type_="check")
    op.drop_index("ix_gis_features_geometry_gist",table_name="gis_features",postgresql_using="gist")
    op.drop_index(op.f("ix_gis_features_layer_id"),table_name="gis_features")
    op.drop_index(op.f("ix_gis_features_project_id"),table_name="gis_features")
    op.drop_table("gis_features")
