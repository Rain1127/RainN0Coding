ALTER USER 'root'@'localhost' IDENTIFIED BY '';
CREATE DATABASE IF NOT EXISTS rainn0coding
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'yuai'@'localhost' IDENTIFIED BY '';
GRANT ALL PRIVILEGES ON rainn0coding.* TO 'yuai'@'localhost';
FLUSH PRIVILEGES;
