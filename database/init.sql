BEGIN;

CREATE TABLE public.customers (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE public.orders (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES public.customers(id),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    order_date DATE NOT NULL
);

CREATE INDEX orders_customer_id_idx
    ON public.orders(customer_id);

COMMENT ON TABLE public.customers IS
    'Customers who place orders. Different customers may share a name.';

COMMENT ON TABLE public.orders IS
    'Customer orders. Each row represents one order.';

COMMENT ON COLUMN public.orders.amount IS
    'Order amount in INR.';

INSERT INTO public.customers (name, city)
VALUES
    ('Aarav Sharma', 'Delhi'),
    ('Priya Singh', 'Mumbai'),
    ('Rohan Mehta', 'Pune'),
    ('Neha Gupta', 'Bengaluru');

INSERT INTO public.orders (customer_id, amount, order_date)
VALUES
    (1, 30000.00, '2026-10-01'),
    (1, 25000.00, '2026-10-05'),
    (2, 12000.00, '2026-10-03'),
    (2, 18000.00, '2026-10-10'),
    (3, 70000.00, '2026-10-07');

CREATE ROLE sg_reader
    LOGIN
    PASSWORD 'sg_reader_local_dev_2026'
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION
    NOBYPASSRLS;

REVOKE ALL ON DATABASE schemaguard FROM PUBLIC;
GRANT CONNECT ON DATABASE schemaguard TO sg_reader;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO sg_reader;

REVOKE ALL ON TABLE public.customers, public.orders FROM PUBLIC;
GRANT SELECT ON TABLE public.customers, public.orders TO sg_reader;

ALTER ROLE sg_reader IN DATABASE schemaguard
    SET default_transaction_read_only = on;

ALTER ROLE sg_reader IN DATABASE schemaguard
    SET statement_timeout = '5s';

ALTER ROLE sg_reader IN DATABASE schemaguard
    SET lock_timeout = '1s';

COMMIT;