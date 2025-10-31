-- MySQL 8.0 schema snapshot (based on current SQLAlchemy models)
-- Engine/charset
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- USER
CREATE TABLE IF NOT EXISTS `user` (
  `user_id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `user_code` VARCHAR(20) NOT NULL UNIQUE,
  `username` VARCHAR(64) NOT NULL UNIQUE,
  `password` VARCHAR(72) NOT NULL,
  `role` VARCHAR(20) NOT NULL,
  `name` VARCHAR(50) NOT NULL,
  `birthdate` DATE NOT NULL,
  `connecting_user_code` VARCHAR(20) NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `check_user_role` CHECK (`role` IN ('USER','CARE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- VOICE
CREATE TABLE IF NOT EXISTS `voice` (
  `voice_id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `voice_key` VARCHAR(1024) NOT NULL,
  `voice_name` VARCHAR(255) NOT NULL,
  `duration_ms` INT NOT NULL,
  `sample_rate` INT NULL,
  `bit_rate` INT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `user_id` BIGINT NOT NULL,
  CONSTRAINT `fk_voice_user` FOREIGN KEY (`user_id`) REFERENCES `user`(`user_id`) ON DELETE CASCADE,
  INDEX `idx_voice_user_created` (`user_id`, `created_at` DESC),
  INDEX `idx_voice_key` (`voice_key`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- VOICE_CONTENT
CREATE TABLE IF NOT EXISTS `voice_content` (
  `voice_content_id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `voice_id` BIGINT NOT NULL,
  `content` MEDIUMTEXT NOT NULL,
  `score_bps` SMALLINT NULL,
  `magnitude_x1000` INT NULL,
  `locale` VARCHAR(10) NULL,
  `provider` VARCHAR(32) NULL,
  `model_version` VARCHAR(32) NULL,
  `confidence_bps` SMALLINT NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_vc_voice` FOREIGN KEY (`voice_id`) REFERENCES `voice`(`voice_id`) ON DELETE CASCADE,
  UNIQUE KEY `uq_vc_voice` (`voice_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- VOICE_ANALYZE
CREATE TABLE IF NOT EXISTS `voice_analyze` (
  `voice_analyze_id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `voice_id` BIGINT NOT NULL,
  `happy_bps` SMALLINT UNSIGNED NOT NULL,
  `sad_bps` SMALLINT UNSIGNED NOT NULL,
  `neutral_bps` SMALLINT UNSIGNED NOT NULL,
  `angry_bps` SMALLINT UNSIGNED NOT NULL,
  `fear_bps` SMALLINT UNSIGNED NOT NULL,
  `surprise_bps` SMALLINT UNSIGNED NOT NULL,
  `top_emotion` VARCHAR(16) NULL,
  `top_confidence_bps` SMALLINT UNSIGNED NULL,
  `model_version` VARCHAR(32) NULL,
  `analyzed_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_va_voice` FOREIGN KEY (`voice_id`) REFERENCES `voice`(`voice_id`) ON DELETE CASCADE,
  UNIQUE KEY `uq_va_voice` (`voice_id`),
  CONSTRAINT `check_emotion_bps_range` CHECK (
    `happy_bps` <= 10000 AND `sad_bps` <= 10000 AND `neutral_bps` <= 10000 AND `angry_bps` <= 10000 AND `fear_bps` <= 10000 AND `surprise_bps` <= 10000
  ),
  CONSTRAINT `check_emotion_bps_sum` CHECK (
    `happy_bps` + `sad_bps` + `neutral_bps` + `angry_bps` + `fear_bps` + `surprise_bps` = 10000
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- VOICE_JOB_PROCESS
CREATE TABLE IF NOT EXISTS `voice_job_process` (
  `voice_id` BIGINT NOT NULL,
  `text_done` TINYINT NOT NULL DEFAULT 0,
  `audio_done` TINYINT NOT NULL DEFAULT 0,
  `locked` TINYINT NOT NULL DEFAULT 0,
  `updated_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `fk_vjp_voice` FOREIGN KEY (`voice_id`) REFERENCES `voice`(`voice_id`) ON DELETE CASCADE,
  PRIMARY KEY (`voice_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- VOICE_COMPOSITE
CREATE TABLE IF NOT EXISTS `voice_composite` (
  `voice_composite_id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `voice_id` BIGINT NOT NULL,
  `text_score_bps` SMALLINT NULL,
  `text_magnitude_x1000` INT NULL,
  `alpha_bps` SMALLINT NULL,
  `beta_bps` SMALLINT NULL,
  `valence_x1000` INT NOT NULL,
  `arousal_x1000` INT NOT NULL,
  `intensity_x1000` INT NOT NULL,
  `happy_bps` SMALLINT UNSIGNED NOT NULL,
  `sad_bps` SMALLINT UNSIGNED NOT NULL,
  `neutral_bps` SMALLINT UNSIGNED NOT NULL,
  `angry_bps` SMALLINT UNSIGNED NOT NULL,
  `fear_bps` SMALLINT UNSIGNED NOT NULL,
  `surprise_bps` SMALLINT UNSIGNED NOT NULL,
  `top_emotion` VARCHAR(16) NULL,
  `top_emotion_confidence_bps` SMALLINT UNSIGNED NULL,
  `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_vc_voice2` FOREIGN KEY (`voice_id`) REFERENCES `voice`(`voice_id`) ON DELETE CASCADE,
  UNIQUE KEY `uq_vc_voice2` (`voice_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- QUESTION
CREATE TABLE IF NOT EXISTS `question` (
  `question_id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `question_category` VARCHAR(50) NOT NULL,
  `