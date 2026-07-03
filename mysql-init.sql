ALTER USER 'root'@'localhost' IDENTIFIED BY '';
CREATE DATABASE IF NOT EXISTS yu_ai_code_mother
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'yuai'@'localhost' IDENTIFIED BY '';
GRANT ALL PRIVILEGES ON yu_ai_code_mother.* TO 'yuai'@'localhost';
FLUSH PRIVILEGES;
