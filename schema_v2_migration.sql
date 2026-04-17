-- =====================================================================
-- Migration v1 → v2
-- Run this on an EXISTING v1 database to add cart, referrals, delivery,
-- order_items and refund support. Idempotent where possible.
-- =====================================================================

USE shop_bot;

-- --- users: referrals
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS referrer_id BIGINT NULL AFTER full_name,
    ADD COLUMN IF NOT EXISTS referral_bonus_stars INT DEFAULT 0 AFTER referrer_id,
    ADD INDEX IF NOT EXISTS idx_referrer (referrer_id);

-- --- products: delivery fields
ALTER TABLE products
    ADD COLUMN IF NOT EXISTS delivery_type ENUM('none','text','file') DEFAULT 'none' AFTER is_active,
    ADD COLUMN IF NOT EXISTS delivery_text TEXT NULL AFTER delivery_type,
    ADD COLUMN IF NOT EXISTS delivery_file_id VARCHAR(255) NULL AFTER delivery_text;

-- --- orders: refund + delivered + rename/cleanup
ALTER TABLE orders
    ADD COLUMN IF NOT EXISTS delivered BOOLEAN DEFAULT FALSE AFTER telegram_payment_charge_id,
    ADD COLUMN IF NOT EXISTS refunded_at TIMESTAMP NULL AFTER paid_at;

-- rename legacy telegram_payment_id to telegram_payment_charge_id if needed
-- (MySQL 8 supports RENAME COLUMN directly)
ALTER TABLE orders CHANGE COLUMN telegram_payment_id
    telegram_payment_charge_id VARCHAR(255) NULL;

-- Drop the old single product_id FK — we're switching to order_items.
-- Only drop if it still exists (ignore errors if already removed).
-- Note: you may need to adjust the FK name to match your installation.
-- SHOW CREATE TABLE orders; — look for the FK that references products.
-- Example:  ALTER TABLE orders DROP FOREIGN KEY orders_ibfk_2;
-- Example:  ALTER TABLE orders DROP COLUMN product_id;

-- --- order_items (new)
CREATE TABLE IF NOT EXISTS order_items (
    id INT PRIMARY KEY AUTO_INCREMENT,
    order_id INT NOT NULL,
    product_id INT NULL,
    product_title VARCHAR(255) NOT NULL,
    price_stars INT NOT NULL,
    quantity INT DEFAULT 1,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL,
    INDEX idx_order (order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- --- cart_items (new)
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

-- --- Backfill: convert old single-product orders into order_items
INSERT INTO order_items (order_id, product_id, product_title, price_stars, quantity)
SELECT o.id, o.product_id,
       COALESCE(p.title, 'Unknown product') AS product_title,
       o.amount_stars, 1
  FROM orders o
  LEFT JOIN products p ON p.id = o.product_id
 WHERE NOT EXISTS (SELECT 1 FROM order_items oi WHERE oi.order_id = o.id);