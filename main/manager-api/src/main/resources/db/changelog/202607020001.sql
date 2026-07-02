-- liquibase formatted sql

-- changeset khanhnq:202607020001-1
CREATE TABLE IF NOT EXISTS sys_user_oauth_account (
  `id` bigint(20) NOT NULL AUTO_INCREMENT COMMENT 'ID',
  `user_id` bigint(20) NOT NULL COMMENT 'Liên kết với sys_user.id',
  `provider` varchar(50) NOT NULL COMMENT 'Provider name (e.g. google)',
  `provider_account_id` varchar(255) NOT NULL COMMENT 'Account ID from provider (Google Sub / ID)',
  `email` varchar(255) DEFAULT NULL COMMENT 'Email from provider',
  `create_date` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'Created time',
  `creator` bigint(20) DEFAULT NULL COMMENT 'Creator',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_provider_account` (`provider`, `provider_account_id`),
  KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='OAuth account mapping';
