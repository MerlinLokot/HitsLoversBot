import os
import psycopg
from psycopg.rows import dict_row

class Database:
    def __init__(self):
        DATABASE_URL = os.getenv("DATABASE_URL")

        if not DATABASE_URL:
            raise Exception("❌ DATABASE_URL не найден. Добавьте PostgreSQL в Railway.")
        
        self.conn = psycopg.connect(DATABASE_URL)
        self.cursor = self.conn.cursor(row_factory=psycopg.rows.dict_row)

        self._init_db()

    def _init_db(self):
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_answers (
            id SERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            answers_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id SERIAL PRIMARY KEY,
            user1_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            user2_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            similarity_score REAL NOT NULL,
            matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user1_id, user2_id)
        )
        """)

        self.conn.commit()
        print("✅ PostgreSQL база данных инициализирована")


    def register_user(self, telegram_id, username, full_name):
        try:
            self.cursor.execute("""
                INSERT INTO users (telegram_id, username, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id) DO NOTHING
            """, (telegram_id, username, full_name))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Ошибка регистрации: {e}")
            return False

    def count_users(self):
        self.cursor.execute("SELECT COUNT(*) as count FROM users")
        return self.cursor.fetchone()["count"]

    def count_users_with_answers(self):
        self.cursor.execute("""
            SELECT COUNT(DISTINCT u.id) as count
            FROM users u
            JOIN user_answers ua ON u.id = ua.user_id
        """)
        return self.cursor.fetchone()["count"]

    def is_registered(self, username):
        clean_username = username[1:] if username.startswith('@') else username

        self.cursor.execute("""
            SELECT telegram_id, username, full_name
            FROM users
            WHERE username = %s OR username = %s
        """, (clean_username, f"@{clean_username}"))

        user = self.cursor.fetchone()

        if user:
            return True
        else:
            return False

    def get_user_by_username(self, username):
        clean_username = username[1:] if username.startswith('@') else username

        self.cursor.execute("""
            SELECT telegram_id, username, full_name
            FROM users
            WHERE username = %s OR username = %s
        """, (clean_username, f"@{clean_username}"))

        return self.cursor.fetchone()

    def save_user_answers(self, telegram_id, answers_json):
        try:
            self.cursor.execute(
                "SELECT id FROM users WHERE telegram_id = %s",
                (telegram_id,)
            )
            user = self.cursor.fetchone()

            if not user:
                return False

            user_id = user["id"]

            self.cursor.execute("""
                INSERT INTO user_answers (user_id, answers_json)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    answers_json = EXCLUDED.answers_json,
                    updated_at = CURRENT_TIMESTAMP
            """, (user_id, answers_json))

            self.conn.commit()
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения ответов: {e}")
            return False
    def get_user_answers(self, telegram_id):
        self.cursor.execute("""
            SELECT ua.answers_json
            FROM users u
            JOIN user_answers ua ON u.id = ua.user_id
            WHERE u.telegram_id = %s
        """, (telegram_id,))

        result = self.cursor.fetchone()
        return result["answers_json"] if result else None

    def get_all_users_with_answers(self):
        self.cursor.execute("""
            SELECT u.telegram_id, u.username, u.full_name, ua.answers_json
            FROM users u
            JOIN user_answers ua ON u.id = ua.user_id
            WHERE ua.answers_json IS NOT NULL
        """)

        return self.cursor.fetchall()

    async def get_all_user_ids(self):
        self.cursor.execute('SELECT telegram_id FROM users')

        result = self.cursor.fetchall()

        user_ids = [row['telegram_id'] for row in result]
        
        return user_ids

    def save_match(self, user1_id, user2_id, similarity_score):
        if user1_id > user2_id:
            user1_id, user2_id = user2_id, user1_id

        self.cursor.execute("""
            INSERT INTO matches (user1_id, user2_id, similarity_score)
            VALUES (%s, %s, %s)
            ON CONFLICT (user1_id, user2_id)
            DO UPDATE SET similarity_score = EXCLUDED.similarity_score
        """, (user1_id, user2_id, similarity_score))

        self.conn.commit()
        return True

    def get_user_matches(self, telegram_id, limit=10):
        self.cursor.execute("SELECT id FROM users WHERE telegram_id = %s", (telegram_id,))
        user = self.cursor.fetchone()

        if not user:
            return []

        user_id = user["id"]

        self.cursor.execute("""
            SELECT
                CASE
                    WHEN m.user1_id = %s THEN u2.telegram_id
                    ELSE u1.telegram_id
                END as matched_user_id,
                CASE
                    WHEN m.user1_id = %s THEN u2.username
                    ELSE u1.username
                END as matched_username,
                CASE
                    WHEN m.user1_id = %s THEN u2.full_name
                    ELSE u1.full_name
                END as matched_full_name,
                m.similarity_score
            FROM matches m
            JOIN users u1 ON m.user1_id = u1.id
            JOIN users u2 ON m.user2_id = u2.id
            WHERE m.user1_id = %s OR m.user2_id = %s
            ORDER BY m.similarity_score DESC
            LIMIT %s
        """, (user_id, user_id, user_id, user_id, user_id, limit))

        return [
            {
                "telegram_id": row["matched_user_id"],
                "username": row["matched_username"],
                "full_name": row["matched_full_name"],
                "similarity": row["similarity_score"]
            }
            for row in self.cursor.fetchall()
        ]

    def close(self):
        if self.conn:
            self.conn.close()
            print("✅ Соединение с PostgreSQL закрыто")