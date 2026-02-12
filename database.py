import sqlite3
import json

class Database:
    def __init__(self, db_name='valentine.db'):
        self.db_name = db_name
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._init_db()
    
    def _init_db(self):
        """Инициализация базы данных при создании класса"""
        # Таблица пользователей
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            full_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица ответов - теперь храним JSON
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            answers_json TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id)
        )
        ''')
        
        # Таблица для будущих совпадений (можно добавить позже)
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            similarity_score REAL NOT NULL,
            matched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user1_id) REFERENCES users (id),
            FOREIGN KEY (user2_id) REFERENCES users (id),
            UNIQUE(user1_id, user2_id)
        )
        ''')
        
        self.conn.commit()
        print(f"✅ База данных {self.db_name} инициализирована")
    
    def register_user(self, telegram_id, username, full_name):
        """Регистрируем нового пользователя"""
        try:
            self.cursor.execute('''
            INSERT OR IGNORE INTO users (telegram_id, username, full_name)
            VALUES (?, ?, ?)
            ''', (telegram_id, username, full_name))
            
            self.conn.commit()
            print(f"👤 Зарегистрирован пользователь: {full_name} (ID: {telegram_id})")
            return True
        except Exception as e:
            print(f"❌ Ошибка регистрации: {e}")
            return False
    
    def save_user_answers(self, telegram_id, answers_json):
        """Сохраняем JSON с ответами пользователя"""
        try:
            # Получаем ID пользователя
            self.cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
            user = self.cursor.fetchone()
            
            if not user:
                print(f"❌ Пользователь {telegram_id} не найден")
                return False
            
            user_id = user['id']
            
            # Сохраняем или обновляем ответы
            self.cursor.execute('''
            INSERT OR REPLACE INTO user_answers (user_id, answers_json)
            VALUES (?, ?)
            ''', (user_id, answers_json))
            
            self.conn.commit()
            print(f"💾 Ответы сохранены для пользователя {telegram_id}")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения ответов: {e}")
            return False
    
    def get_user_answers(self, telegram_id):
        """Получаем JSON с ответами пользователя"""
        try:
            self.cursor.execute('''
            SELECT ua.answers_json
            FROM users u
            JOIN user_answers ua ON u.id = ua.user_id
            WHERE u.telegram_id = ?
            ''', (telegram_id,))
            
            result = self.cursor.fetchone()
            return result['answers_json'] if result else None
        except Exception as e:
            print(f"❌ Ошибка получения ответов: {e}")
            return None
    
    def get_all_users_with_answers(self):
        """Получаем всех пользователей с их ответами в JSON"""
        try:
            self.cursor.execute('''
            SELECT u.telegram_id, u.username, u.full_name, ua.answers_json
            FROM users u
            JOIN user_answers ua ON u.id = ua.user_id
            WHERE ua.answers_json IS NOT NULL AND ua.answers_json != ''
            ''')
            
            users = []
            for row in self.cursor.fetchall():
                users.append({
                    'telegram_id': row['telegram_id'],
                    'username': row['username'],
                    'full_name': row['full_name'],
                    'answers_json': row['answers_json']
                })
            
            return users
        except Exception as e:
            print(f"❌ Ошибка получения всех пользователей: {e}")
            return []
    
    def save_match(self, user1_id, user2_id, similarity_score):
        """Сохраняем совпадение пользователей"""
        try:
            # Убедимся, что user1_id < user2_id для уникальности
            if user1_id > user2_id:
                user1_id, user2_id = user2_id, user1_id
            
            self.cursor.execute('''
            INSERT OR REPLACE INTO matches (user1_id, user2_id, similarity_score)
            VALUES (?, ?, ?)
            ''', (user1_id, user2_id, similarity_score))
            
            self.conn.commit()
            print(f"💝 Совпадение сохранено: {user1_id} ↔ {user2_id} ({similarity_score:.2f})")
            return True
        except Exception as e:
            print(f"❌ Ошибка сохранения совпадения: {e}")
            return False
    
    def get_user_matches(self, telegram_id, limit=10):
        """Получаем совпадения пользователя"""
        try:
            self.cursor.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
            user = self.cursor.fetchone()
            
            if not user:
                return []
            
            user_id = user['id']
            
            self.cursor.execute('''
            SELECT 
                CASE 
                    WHEN m.user1_id = ? THEN u2.telegram_id
                    ELSE u1.telegram_id 
                END as matched_user_id,
                CASE 
                    WHEN m.user1_id = ? THEN u2.username
                    ELSE u1.username 
                END as matched_username,
                CASE 
                    WHEN m.user1_id = ? THEN u2.full_name
                    ELSE u1.full_name 
                END as matched_full_name,
                m.similarity_score
            FROM matches m
            JOIN users u1 ON m.user1_id = u1.id
            JOIN users u2 ON m.user2_id = u2.id
            WHERE m.user1_id = ? OR m.user2_id = ?
            ORDER BY m.similarity_score DESC
            LIMIT ?
            ''', (user_id, user_id, user_id, user_id, user_id, limit))
            
            matches = []
            for row in self.cursor.fetchall():
                matches.append({
                    'telegram_id': row['matched_user_id'],
                    'username': row['matched_username'],
                    'full_name': row['matched_full_name'],
                    'similarity': row['similarity_score']
                })
            
            return matches
        except Exception as e:
            print(f"❌ Ошибка получения совпадений: {e}")
            return []
    
    def count_users(self):
        """Считаем количество пользователей"""
        try:
            self.cursor.execute('SELECT COUNT(*) as count FROM users')
            result = self.cursor.fetchone()
            return result['count'] if result else 0
        except Exception as e:
            print(f"❌ Ошибка подсчета пользователей: {e}")
            return 0
    
    def count_users_with_answers(self):
        """Считаем количество пользователей с ответами"""
        try:
            self.cursor.execute('''
            SELECT COUNT(DISTINCT u.id) as count
            FROM users u
            JOIN user_answers ua ON u.id = ua.user_id
            ''')
            result = self.cursor.fetchone()
            return result['count'] if result else 0
        except Exception as e:
            print(f"❌ Ошибка подсчета пользователей с ответами: {e}")
            return 0
        
    def get_user_by_username(self, username):
        """Получает пользователя по username"""
        try:
            # Очищаем username от @
            clean_username = username[1:] if username.startswith('@') else username
            
            self.cursor.execute('''
            SELECT telegram_id, username, full_name 
            FROM users 
            WHERE username = ? OR username = ?
            ''', (clean_username, f"@{clean_username}"))
            
            return self.cursor.fetchone()
        except Exception as e:
            print(f"❌ Ошибка поиска пользователя: {e}")
            return None
    
    def close(self):
        """Закрываем соединение с базой"""
        if self.conn:
            self.conn.close()
            print("✅ Соединение с базой данных закрыто")
    
    def __del__(self):
        """Гарантированное закрытие при удалении объекта"""
        self.close()

# Создаём экземпляр базы данных
db = Database()