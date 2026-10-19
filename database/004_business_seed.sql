BEGIN;

DO $$
BEGIN
    IF (
        SELECT COUNT(*)
        FROM public.orders
        WHERE (id, customer_id, amount) IN (
            (1, 1, 30000.00),
            (2, 1, 25000.00),
            (3, 2, 12000.00),
            (4, 2, 18000.00),
            (5, 3, 70000.00)
        )
    ) <> 5 THEN
        RAISE EXCEPTION
            'Expected original sample orders were not found. Seed aborted.';
    END IF;

    IF EXISTS (SELECT 1 FROM public.products)
        OR EXISTS (SELECT 1 FROM public.order_items)
        OR EXISTS (SELECT 1 FROM public.support_tickets)
        OR EXISTS (SELECT 1 FROM public.ticket_messages)
    THEN
        RAISE EXCEPTION
            'New business tables must be empty. Seed aborted.';
    END IF;
END
$$;

INSERT INTO public.products (name, category, current_price)
VALUES
    ('Office Desk', 'Furniture', 32000.00),
    ('Monitor', 'Electronics', 26000.00),
    ('Keyboard', 'Electronics', 6500.00),
    ('Laptop', 'Electronics', 72000.00);

INSERT INTO public.order_items (
    order_id, product_id, quantity, unit_price
)
SELECT seed.order_id, p.id, seed.quantity, seed.unit_price
FROM (
    VALUES
        (1, 'Office Desk', 1, 30000.00),
        (2, 'Monitor', 1, 25000.00),
        (3, 'Keyboard', 2, 6000.00),
        (4, 'Keyboard', 3, 6000.00),
        (5, 'Laptop', 1, 70000.00)
) AS seed(order_id, product_name, quantity, unit_price)
JOIN public.products AS p ON p.name = seed.product_name;

INSERT INTO public.support_tickets (
    customer_id, subject, status, priority, created_at
)
VALUES
    (
        1, 'Monitor flickering', 'open', 'high',
        '2026-10-11 09:00:00+00'
    ),
    (
        2, 'Keyboard replacement', 'in_progress', 'medium',
        '2026-10-12 10:00:00+00'
    ),
    (
        3, 'Laptop setup help', 'closed', 'low',
        '2026-10-13 11:00:00+00'
    );

INSERT INTO public.ticket_messages (
    ticket_id, sender_type, body, created_at
)
SELECT t.id, seed.sender_type, seed.body, seed.created_at
FROM (
    VALUES
        (
            'Monitor flickering',
            'customer',
            'The monitor flickers after a few minutes.',
            TIMESTAMPTZ '2026-10-11 09:00:00+00'
        ),
        (
            'Monitor flickering',
            'agent',
            'Please check the display cable connection.',
            TIMESTAMPTZ '2026-10-11 09:30:00+00'
        ),
        (
            'Keyboard replacement',
            'customer',
            'One keyboard has a faulty key.',
            TIMESTAMPTZ '2026-10-12 10:00:00+00'
        ),
        (
            'Keyboard replacement',
            'agent',
            'A replacement request is being processed.',
            TIMESTAMPTZ '2026-10-12 10:30:00+00'
        ),
        (
            'Laptop setup help',
            'customer',
            'How do I finish the initial setup?',
            TIMESTAMPTZ '2026-10-13 11:00:00+00'
        ),
        (
            'Laptop setup help',
            'agent',
            'Setup completed with the customer.',
            TIMESTAMPTZ '2026-10-13 12:00:00+00'
        )
) AS seed(subject, sender_type, body, created_at)
JOIN public.support_tickets AS t ON t.subject = seed.subject;

COMMIT;