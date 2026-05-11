-- 멱등 시드: INSERT OR IGNORE (UNIQUE category+key)
INSERT OR IGNORE INTO youtube_settings (category, key, value, value_enc, value_type, is_secret, description) VALUES
('database', 'host', '', NULL, 'string', 0, 'PG 호스트'),
('database', 'port', '5432', NULL, 'int', 0, 'PG 포트'),
('database', 'dbname', 'youtube_monitor', NULL, 'string', 0, '데이터베이스명'),
('database', 'username', '', NULL, 'string', 0, 'PG 사용자'),
('database', 'password', NULL, NULL, 'string', 1, 'PG 비밀번호 (Fernet)'),
('database', 'schema', 'youtube', NULL, 'string', 0, 'PG 스키마명'),
('database', 'sslmode', 'prefer', NULL, 'string', 0, 'disable/prefer/require'),

('ai_gateway', 'base_url', 'http://litellm:4000', NULL, 'string', 0, 'litellm 엔드포인트'),
('ai_gateway', 'api_key', NULL, NULL, 'string', 1, 'litellm Master Key (Fernet)'),
('ai_gateway', 'primary_model', 'gemini/gemini-2.5-flash', NULL, 'string', 0, '멀티모달 분석'),
('ai_gateway', 'fallback_model', 'gemini/gemini-2.5-flash', NULL, 'string', 0, '텍스트 fallback'),
('ai_gateway', 'tagging_model', 'gemini/gemini-2.5-flash', NULL, 'string', 0, '태그 정제'),
('ai_gateway', 'temperature', '0.3', NULL, 'float', 0, '모델 공통 temperature'),
('ai_gateway', 'max_tokens', '8192', NULL, 'int', 0, 'max_tokens'),
('ai_gateway', 'daily_budget_usd', '2.0', NULL, 'float', 0, '일일 LLM 비용 한도(USD)'),

('polling', 'master_interval_min', '12', NULL, 'int', 0, '마스터 잡 주기(분)'),
('polling', 'default_channel_interval_min', '720', NULL, 'int', 0, '채널 기본 폴링 주기(분)'),
('polling', 'youtube_api_key', NULL, NULL, 'string', 1, 'YouTube Data API 키 (Fernet)'),
('polling', 'youtube_daily_quota', '10000', NULL, 'int', 0, 'YouTube API 일일 unit 한도'),
('polling', 'window_hours', '24', NULL, 'int', 0, '신규 영상 인정 윈도우(시간)'),
('polling', 'max_concurrent_channels', '5', NULL, 'int', 0, '폴링 동시 채널 수'),
('polling', 'max_concurrent_analyses', '3', NULL, 'int', 0, '분석 동시 실행 수'),

('notification', 'telegram_enabled', 'true', NULL, 'bool', 0, 'Telegram 알림 ON/OFF'),
('notification', 'wait_between_messages_sec', '30', NULL, 'int', 0, '채널 간 발송 대기(초)'),
('notification', 'low_confidence_threshold', '0.5', NULL, 'float', 0, '저신뢰도 배지 임계값');
