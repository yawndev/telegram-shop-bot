-- =====================================================================
-- MySQL schema for Telegram Shop Bot (v2)
-- Full schema — safe to run on a fresh database.
-- For upgrading an existing v1 install, use schema_v2_migration.sql.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS shop_bot
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE shop_bot;

-- ---------- users ----------
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY COMMENT 'Telegram user ID',
    username VARCHAR(64) NULL,
    full_name VARCHAR(255) NULL,
    referrer_id BIGINT NULL COMMENT 'User who invited this one',
    referral_bonus_stars INT DEFAULT 0 COMMENT 'Accumulated referral rewards',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created_at (created_at),
    INDEX idx_referrer (referrer_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- products ----------
CREATE TABLE IF NOT EXISTS products (
    id INT PRIMARY KEY AUTO_INCREMENT,
    title VARCHAR(255) NOT NULL,
    description TEXT NULL,
    price_stars INT NOT NULL COMMENT 'Price in Telegram Stars (XTR)',
    is_active BOOLEAN DEFAULT TRUE,
    delivery_type ENUM('none', 'text', 'file') DEFAULT 'none'
        COMMENT 'What to auto-deliver after payment',
    delivery_text TEXT NULL COMMENT 'Text content for delivery_type=text',
    delivery_file_id VARCHAR(255) NULL COMMENT 'Telegram file_id for delivery_type=file',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- orders ----------
CREATE TABLE IF NOT EXISTS orders (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    amount_stars INT NOT NULL,
    status ENUM('pending', 'paid', 'cancelled', 'refunded') DEFAULT 'pending',
    telegram_payment_charge_id VARCHAR(255) NULL
        COMMENT 'Needed for refund_star_payment',
    delivered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    paid_at TIMESTAMP NULL,
    refunded_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_status (status),
    INDEX idx_user (user_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- order_items ----------
CREATE TABLE IF NOT EXISTS order_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL,
    product_id INT NULL,
    product_title VARCHAR(255) NOT NULL COMMENT 'Snapshot of title at order time',
    price_stars INT NOT NULL COMMENT 'Snapshot of price at order time',
    quantity INT DEFAULT 1,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
    INDEX idx_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- cart_items ----------
CREATE TABLE IF NOT EXISTS cart_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    product_id INT NOT NULL,
    quantity INT DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_user_product (user_id, product_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------- demo products ----------
INSERT INTO products (title, description, price_stars, delivery_type, delivery_text) VALUES
    ('Consultation 30 min', 'One-on-one consultation, 30 minutes.', 50, 'none', NULL),
    ('Consultation 60 min', 'One-on-one consultation, 60 minutes.', 90, 'none', NULL),
    ('Premium access', 'Access to premium content for 30 days.', 150, 'text',
        'Thanks for your purchase! Your access code: DEMO-PREMIUM-2026'),
    ('Custom development', 'Custom script or small project by request.', 500, 'none', NULL);