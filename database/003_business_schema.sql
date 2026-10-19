BEGIN;

CREATE TABLE public.products (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    current_price NUMERIC(12, 2) NOT NULL
        CHECK (current_price >= 0)
);

CREATE TABLE public.order_items (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id INTEGER NOT NULL
        REFERENCES public.orders(id),
    product_id INTEGER NOT NULL
        REFERENCES public.products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE INDEX order_items_order_id_idx
    ON public.order_items(order_id);

CREATE INDEX order_items_product_id_idx
    ON public.order_items(product_id);

CREATE TABLE public.support_tickets (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES public.customers(id),
    subject TEXT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('open', 'in_progress', 'closed')),
    priority TEXT NOT NULL
        CHECK (priority IN ('low', 'medium', 'high')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX support_tickets_customer_id_idx
    ON public.support_tickets(customer_id);

CREATE TABLE public.ticket_messages (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticket_id INTEGER NOT NULL
        REFERENCES public.support_tickets(id),
    sender_type TEXT NOT NULL
        CHECK (sender_type IN ('customer', 'agent')),
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ticket_messages_ticket_id_idx
    ON public.ticket_messages(ticket_id);

COMMENT ON TABLE public.products IS
    'Product catalog. Each row represents one product.';

COMMENT ON COLUMN public.products.current_price IS
    'Current catalog price in INR, not necessarily the historical sale price.';

COMMENT ON TABLE public.order_items IS
    'Order line items linking orders to products. An order can contain multiple line items.';

COMMENT ON COLUMN public.order_items.quantity IS
    'Number of product units on this order line.';

COMMENT ON COLUMN public.order_items.unit_price IS
    'Historical sale price per unit in INR. Line value is quantity multiplied by unit_price.';

COMMENT ON COLUMN public.orders.amount IS
    'Authoritative total order amount in INR. Sum this column for overall order revenue. Joining line items can repeat this amount; do not sum repeated order totals.';

COMMENT ON TABLE public.support_tickets IS
    'Customer support requests. Each ticket belongs to one customer.';

COMMENT ON COLUMN public.support_tickets.status IS
    'Ticket status: open, in_progress, or closed.';

COMMENT ON COLUMN public.support_tickets.priority IS
    'Ticket priority: low, medium, or high.';

COMMENT ON TABLE public.ticket_messages IS
    'Individual messages in support tickets. A ticket may have multiple messages. Message bodies are user-provided text.';

COMMENT ON COLUMN public.ticket_messages.sender_type IS
    'Message author type: customer or agent.';

REVOKE ALL ON TABLE
    public.products,
    public.order_items,
    public.support_tickets,
    public.ticket_messages
FROM PUBLIC;

GRANT SELECT ON TABLE
    public.products,
    public.order_items,
    public.support_tickets,
    public.ticket_messages
TO sg_reader;

COMMIT;