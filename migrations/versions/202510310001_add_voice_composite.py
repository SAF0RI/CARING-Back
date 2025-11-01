from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '202510310001_add_voice_composite'
down_revision = None  # set to current head in real chain if needed
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'voice_composite',
        sa.Column('voice_composite_id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('voice_id', sa.BigInteger(), sa.ForeignKey('voice.voice_id', ondelete='CASCADE'), nullable=False),
        sa.Column('text_score_bps', sa.SmallInteger(), nullable=True),
        sa.Column('text_magnitude_x1000', sa.Integer(), nullable=True),
        sa.Column('alpha_bps', sa.SmallInteger(), nullable=True),
        sa.Column('beta_bps', sa.SmallInteger(), nullable=True),
        sa.Column('valence_x1000', sa.Integer(), nullable=False),
        sa.Column('arousal_x1000', sa.Integer(), nullable=False),
        sa.Column('intensity_x1000', sa.Integer(), nullable=False),
        sa.Column('happy_bps', sa.SmallInteger(), nullable=False),
        sa.Column('sad_bps', sa.SmallInteger(), nullable=False),
        sa.Column('neutral_bps', sa.SmallInteger(), nullable=False),
        sa.Column('angry_bps', sa.SmallInteger(), nullable=False),
        sa.Column('fear_bps', sa.SmallInteger(), nullable=False),
        sa.Column('surprise_bps', sa.SmallInteger(), nullable=False),
        sa.Column('top_emotion', sa.String(length=16), nullable=True),
        sa.Column('top_emotion_confidence_bps', sa.SmallInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.UniqueConstraint('voice_id', name='uq_vc_voice2')
    )


def downgrade() -> None:
    op.drop_table('voice_composite')
