"""Async MySQL database layer using aiomysql."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import aiomysql

from config import Config


@dataclass
class Product:
    id: int
    title: str
    description: Optional[str]
    price_stars: int
    is_active: bool = True
    delivery_type: str = "none"
    delivery_text: Optional[str] = None
    delivery_file_id: Optional[str] = None


@dataclass
class CartLine:
    product_id: int
    title: str
    price_stars: int
    quantity: int

    @property
    def subtotal(self) -> int:
        return self.price_stars * self.quantity


@dataclass
class Order:
    id: int
    user_id: int
    amount_stars: int
    status: str
    created_at: datetime


@dataclass
class OrderItem:
    product_id: Optional[int]
    product_title: str
    price_stars: int
    quantity: int
    delivery_type: str = "none"
    delivery_text: Optional[str] = None
    delivery_file_id: Optional[str] = None


@dataclass
class UserRow:
    id: int
    username: Optional[str]
    full_name: Optional[str]
    referrer_id: Optional[int]
    referral_bonus_stars: int


class Database:
    """Connection pool wrapper around aiomysql."""

    def __init__(self, config: Config):
        self._config = config
        self._pool: Optional[aiomysql.Pool] = None

    async def connect(self) -> None:
        self._pool = await aiomysql.create_pool(
            host=self._config.db_host,
            port=self._config.db_port,
            user=self._config.db_user,
            password=self._config.db_password,
            db=self._config.db_name,
            autocommit=True,
            minsize=1,
            maxsize=10,
            charset="utf8mb4",
        )

    async def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()

    # =================================================================
    # USERS
    # =================================================================

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        full_name: str,
        referrer_id: int | None = None,
    ) -> bool:
        """Returns True if a new user row was inserted (first /start)."""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Check if exists first
                await cur.execute("SELECT 1 FROM users WHERE id = %s", (user_id,))
                exists = await cur.fetchone() is not None

                if exists:
                    await cur.execute(
                        "UPDATE users SET username = %s, full_name = %s WHERE id = %s",
                        (username, full_name, user_id),
                    )
                    return False

                # brand-new user — set referrer only at first /start, ignore self-ref
                safe_ref = referrer_id if referrer_id and referrer_id != user_id else None
                await cur.execute(
                    """
                    INSERT INTO users (id, username, full_name, referrer_id)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, username, full_name, safe_ref),
                )
                return True

    async def get_user(self, user_id: int) -> Optional[UserRow]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, username, full_name, referrer_id, referral_bonus_stars "
                    "FROM users WHERE id = %s",
                    (user_id,),
                )
                row = await cur.fetchone()
                return UserRow(**row) if row else None

    async def count_users(self) -> int:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM users")
                row = await cur.fetchone()
                return int(row[0]) if row else 0

    async def all_user_ids(self) -> list[int]:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT id FROM users ORDER BY id")
                rows = await cur.fetchall()
                return [int(r[0]) for r in rows]

    async def add_referral_bonus(self, referrer_id: int, bonus_stars: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE users SET referral_bonus_stars = referral_bonus_stars + %s "
                    "WHERE id = %s",
                    (bonus_stars, referrer_id),
                )

    async def referral_summary(self, user_id: int) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM users WHERE referrer_id = %s", (user_id,)
                )
                invited = (await cur.fetchone())[0]

                await cur.execute(
                    "SELECT referral_bonus_stars FROM users WHERE id = %s", (user_id,)
                )
                bonus_row = await cur.fetchone()
                bonus = int(bonus_row[0]) if bonus_row else 0

                return {"invited": int(invited), "bonus_stars": bonus}

    # =================================================================
    # PRODUCTS (CRUD)
    # =================================================================

    async def list_products(self, include_inactive: bool = False) -> list[Product]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                query = (
                    "SELECT id, title, description, price_stars, is_active, "
                    "delivery_type, delivery_text, delivery_file_id FROM products"
                )
                if not include_inactive:
                    query += " WHERE is_active = TRUE"
                query += " ORDER BY id"
                await cur.execute(query)
                rows = await cur.fetchall()
                return [Product(**r) for r in rows]

    async def get_product(self, product_id: int) -> Optional[Product]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, title, description, price_stars, is_active, "
                    "delivery_type, delivery_text, delivery_file_id "
                    "FROM products WHERE id = %s",
                    (product_id,),
                )
                row = await cur.fetchone()
                return Product(**row) if row else None

    async def create_product(
        self,
        title: str,
        description: str,
        price_stars: int,
        delivery_type: str = "none",
        delivery_text: Optional[str] = None,
        delivery_file_id: Optional[str] = None,
    ) -> int:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO products
                        (title, description, price_stars, delivery_type,
                         delivery_text, delivery_file_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (title, description, price_stars, delivery_type,
                     delivery_text, delivery_file_id),
                )
                return cur.lastrowid

    async def update_product_field(self, product_id: int, field: str, value) -> None:
        allowed = {
            "title", "description", "price_stars", "is_active",
            "delivery_type", "delivery_text", "delivery_file_id",
        }
        if field not in allowed:
            raise ValueError(f"Field '{field}' is not updatable")
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"UPDATE products SET {field} = %s WHERE id = %s",
                    (value, product_id),
                )

    async def delete_product(self, product_id: int) -> None:
        """Soft-delete — deactivate instead of DELETE to preserve order history."""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE products SET is_active = FALSE WHERE id = %s",
                    (product_id,),
                )

    # =================================================================
    # CART
    # =================================================================

    async def cart_add(self, user_id: int, product_id: int, delta: int = 1) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO cart_items (user_id, product_id, quantity)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE quantity = GREATEST(1, quantity + %s)
                    """,
                    (user_id, product_id, delta, delta),
                )

    async def cart_decrement(self, user_id: int, product_id: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE cart_items SET quantity = quantity - 1 "
                    "WHERE user_id = %s AND product_id = %s",
                    (user_id, product_id),
                )
                await cur.execute(
                    "DELETE FROM cart_items WHERE user_id = %s AND quantity <= 0",
                    (user_id,),
                )

    async def cart_remove(self, user_id: int, product_id: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM cart_items WHERE user_id = %s AND product_id = %s",
                    (user_id, product_id),
                )

    async def cart_clear(self, user_id: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM cart_items WHERE user_id = %s", (user_id,)
                )

    async def cart_lines(self, user_id: int) -> list[CartLine]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT c.product_id, p.title, p.price_stars, c.quantity
                      FROM cart_items c
                      JOIN products p ON p.id = c.product_id
                     WHERE c.user_id = %s AND p.is_active = TRUE
                     ORDER BY c.added_at
                    """,
                    (user_id,),
                )
                rows = await cur.fetchall()
                return [
                    CartLine(
                        product_id=r["product_id"],
                        title=r["title"],
                        price_stars=r["price_stars"],
                        quantity=r["quantity"],
                    ) for r in rows
                ]

    async def cart_total(self, user_id: int) -> int:
        lines = await self.cart_lines(user_id)
        return sum(l.subtotal for l in lines)

    # =================================================================
    # ORDERS
    # =================================================================

    async def create_order_from_cart(self, user_id: int) -> tuple[int, int]:
        """Snapshot the cart into an orders+order_items pair. Returns (order_id, total)."""
        lines = await self.cart_lines(user_id)
        if not lines:
            raise ValueError("Cart is empty")
        total = sum(l.subtotal for l in lines)

        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO orders (user_id, amount_stars, status) "
                    "VALUES (%s, %s, 'pending')",
                    (user_id, total),
                )
                order_id = cur.lastrowid

                for l in lines:
                    await cur.execute(
                        """
                        INSERT INTO order_items
                            (order_id, product_id, product_title, price_stars, quantity)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (order_id, l.product_id, l.title, l.price_stars, l.quantity),
                    )
                return order_id, total

    async def create_order_single(self, user_id: int, product: Product) -> int:
        """Quick 'Buy now' — skip the cart, create a single-item order."""
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO orders (user_id, amount_stars, status) "
                    "VALUES (%s, %s, 'pending')",
                    (user_id, product.price_stars),
                )
                order_id = cur.lastrowid
                await cur.execute(
                    """
                    INSERT INTO order_items
                        (order_id, product_id, product_title, price_stars, quantity)
                    VALUES (%s, %s, %s, %s, 1)
                    """,
                    (order_id, product.id, product.title, product.price_stars),
                )
                return order_id

    async def mark_order_paid(self, order_id: int, telegram_payment_charge_id: str) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE orders
                       SET status = 'paid',
                           telegram_payment_charge_id = %s,
                           paid_at = CURRENT_TIMESTAMP
                     WHERE id = %s
                    """,
                    (telegram_payment_charge_id, order_id),
                )

    async def mark_order_refunded(self, order_id: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE orders
                       SET status = 'refunded',
                           refunded_at = CURRENT_TIMESTAMP
                     WHERE id = %s
                    """,
                    (order_id,),
                )

    async def mark_order_delivered(self, order_id: int) -> None:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE orders SET delivered = TRUE WHERE id = %s", (order_id,)
                )

    async def get_order_full(self, order_id: int) -> Optional[dict]:
        """Return an order with its items and product delivery metadata."""
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT id, user_id, amount_stars, status,
                           telegram_payment_charge_id, delivered, created_at
                      FROM orders WHERE id = %s
                    """,
                    (order_id,),
                )
                order = await cur.fetchone()
                if not order:
                    return None

                await cur.execute(
                    """
                    SELECT oi.product_id, oi.product_title, oi.price_stars, oi.quantity,
                           COALESCE(p.delivery_type, 'none') AS delivery_type,
                           p.delivery_text, p.delivery_file_id
                      FROM order_items oi
                      LEFT JOIN products p ON p.id = oi.product_id
                     WHERE oi.order_id = %s
                    """,
                    (order_id,),
                )
                items = await cur.fetchall()
                order["items"] = [
                    OrderItem(
                        product_id=i["product_id"],
                        product_title=i["product_title"],
                        price_stars=i["price_stars"],
                        quantity=i["quantity"],
                        delivery_type=i["delivery_type"] or "none",
                        delivery_text=i["delivery_text"],
                        delivery_file_id=i["delivery_file_id"],
                    )
                    for i in items
                ]
                return order

    async def list_user_orders(self, user_id: int, limit: int = 10) -> list[Order]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT id, user_id, amount_stars, status, created_at
                      FROM orders WHERE user_id = %s
                     ORDER BY id DESC LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = await cur.fetchall()
                return [Order(**r) for r in rows]

    async def list_recent_orders(self, limit: int = 10) -> list[dict]:
        async with self._pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """
                    SELECT o.id, o.user_id, o.amount_stars, o.status,
                           o.created_at,
                           GROUP_CONCAT(CONCAT(oi.product_title, ' ×', oi.quantity)
                                        SEPARATOR ', ') AS items_summary
                      FROM orders o
                      LEFT JOIN order_items oi ON oi.order_id = o.id
                     GROUP BY o.id
                     ORDER BY o.id DESC LIMIT %s
                    """,
                    (limit,),
                )
                return list(await cur.fetchall())

    async def stats(self) -> dict:
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM users")
                users = (await cur.fetchone())[0]

                await cur.execute(
                    "SELECT COUNT(*), COALESCE(SUM(amount_stars), 0) "
                    "FROM orders WHERE status = 'paid'"
                )
                paid_count, revenue = await cur.fetchone()

                await cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
                pending_count = (await cur.fetchone())[0]

                await cur.execute("SELECT COUNT(*) FROM orders WHERE status = 'refunded'")
                refunded_count = (await cur.fetchone())[0]

                return {
                    "users": int(users),
                    "paid_orders": int(paid_count),
                    "pending_orders": int(pending_count),
                    "refunded_orders": int(refunded_count),
                    "revenue_stars": int(revenue),
                }