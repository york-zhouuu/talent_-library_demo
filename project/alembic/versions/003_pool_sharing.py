"""Update talent pools: remove is_public, add sharing mechanism

Revision ID: 003_pool_sharing
Revises: 002_add_ckb_tables
Create Date: 2024-02-28
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '003_pool_sharing'
down_revision = '002_add_ckb_tables'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 创建 pool_shares 表
    op.create_table(
        'pool_shares',
        sa.Column('pool_id', sa.Integer(), sa.ForeignKey('talent_pools.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('user_id', sa.String(100), primary_key=True),
        sa.Column('permission', sa.String(20), default='view'),
    )

    # 修改 talent_pools 表
    # 添加新列
    op.add_column('talent_pools', sa.Column('share_scope', sa.String(20), server_default='private'))
    op.add_column('talent_pools', sa.Column('team_id', sa.String(100), nullable=True))

    # 迁移数据：is_public=True -> share_scope='org'
    op.execute("UPDATE talent_pools SET share_scope = 'org' WHERE is_public = 1")
    op.execute("UPDATE talent_pools SET share_scope = 'private' WHERE is_public = 0 OR is_public IS NULL")

    # 设置 owner_id 默认值（如果为空）
    op.execute("UPDATE talent_pools SET owner_id = 'system' WHERE owner_id IS NULL")

    # 删除 is_public 列 (SQLite 不支持直接删除列，需要重建表)
    # 对于 SQLite，我们保留该列但不再使用
    # 如果是 PostgreSQL/MySQL，可以使用: op.drop_column('talent_pools', 'is_public')


def downgrade() -> None:
    # 恢复 is_public 列的值
    op.execute("UPDATE talent_pools SET is_public = 1 WHERE share_scope = 'org'")
    op.execute("UPDATE talent_pools SET is_public = 0 WHERE share_scope != 'org'")

    # 删除新列
    op.drop_column('talent_pools', 'share_scope')
    op.drop_column('talent_pools', 'team_id')

    # 删除 pool_shares 表
    op.drop_table('pool_shares')
