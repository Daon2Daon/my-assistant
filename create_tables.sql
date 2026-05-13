-- 데이터베이스 테이블 생성 SQL
-- SQLite용

-- users 테이블
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kakao_access_token VARCHAR,
    kakao_refresh_token VARCHAR,
    google_access_token VARCHAR,
    google_refresh_token VARCHAR,
    google_token_expiry DATETIME,
    telegram_chat_id VARCHAR,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- settings 테이블
CREATE TABLE IF NOT EXISTS settings (
    setting_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category VARCHAR NOT NULL,
    notification_time VARCHAR NOT NULL,
    config_json VARCHAR,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- reminders 테이블
CREATE TABLE IF NOT EXISTS reminders (
    reminder_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    message_content VARCHAR NOT NULL,
    target_datetime DATETIME NOT NULL,
    is_sent BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- logs 테이블
CREATE TABLE IF NOT EXISTS logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    message VARCHAR NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- watchlists 테이블
CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    name VARCHAR(100),
    market VARCHAR(10) NOT NULL,
    purchase_price REAL,
    purchase_quantity INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- price_alerts 테이블
CREATE TABLE IF NOT EXISTS price_alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    watchlist_id INTEGER NOT NULL,
    alert_type VARCHAR(20) NOT NULL,
    target_price REAL,
    target_percent REAL,
    is_triggered BOOLEAN DEFAULT 0,
    triggered_at DATETIME,
    is_active BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (watchlist_id) REFERENCES watchlists(watchlist_id)
);

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS ix_users_user_id ON users(user_id);
CREATE INDEX IF NOT EXISTS ix_settings_setting_id ON settings(setting_id);
CREATE INDEX IF NOT EXISTS ix_reminders_reminder_id ON reminders(reminder_id);
CREATE INDEX IF NOT EXISTS ix_reminders_target_datetime ON reminders(target_datetime);
CREATE INDEX IF NOT EXISTS ix_logs_log_id ON logs(log_id);
CREATE INDEX IF NOT EXISTS ix_logs_category ON logs(category);
CREATE INDEX IF NOT EXISTS ix_logs_created_at ON logs(created_at);
CREATE INDEX IF NOT EXISTS ix_watchlists_watchlist_id ON watchlists(watchlist_id);
CREATE INDEX IF NOT EXISTS ix_watchlists_user_id ON watchlists(user_id);
CREATE INDEX IF NOT EXISTS ix_watchlists_ticker ON watchlists(ticker);
CREATE INDEX IF NOT EXISTS ix_price_alerts_alert_id ON price_alerts(alert_id);
CREATE INDEX IF NOT EXISTS ix_price_alerts_user_id ON price_alerts(user_id);
CREATE INDEX IF NOT EXISTS ix_price_alerts_watchlist_id ON price_alerts(watchlist_id);
