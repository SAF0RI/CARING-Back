from app.database import engine
from sqlalchemy import text


def ensure_surprise_column() -> None:
    with engine.connect() as conn:
        res = conn.execute(text("SHOW COLUMNS FROM voice_analyze LIKE 'surprise_bps'"))
        row = res.fetchone()
        if row is None:
            print("Adding surprise_bps column...")
            conn.execute(text("ALTER TABLE voice_analyze ADD COLUMN surprise_bps SMALLINT NOT NULL DEFAULT 0"))
            print("Added surprise_bps")
        else:
            print("surprise_bps exists")
        conn.commit()


if __name__ == "__main__":
    ensure_surprise_column()



