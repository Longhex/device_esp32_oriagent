-- Add oriagent_api_key and oriagent_model_name columns to ai_agent table.
-- These columns store per-agent Oriagent credentials and model override,
-- referenced by AgentEntity, AgentDTO, AgentUpdateDTO, and AgentDao.xml.

-- BỎ QUA CODE NÀY VÌ TRONG DATABASE ĐÃ CÓ SẴN CỘT NÀY RỒI
-- TRÁNH LỖI DUPLICATE COLUMN CHO LIQUIBASE
/*
ALTER TABLE `ai_agent`
    ADD COLUMN `oriagent_api_key`   VARCHAR(255) NULL AFTER `updated_at`,
    ADD COLUMN `oriagent_model_name` VARCHAR(255) NULL AFTER `oriagent_api_key`;
*/
