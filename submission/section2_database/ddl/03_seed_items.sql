-- ===========================================================================
-- GENERATED FILE -- do not edit by hand.
--
--   Regenerate with:  python generate_seed.py
--
-- Product catalogue: 20 items across 5 manufacturers.
-- Source: CATALOGUE in generate_seed.py
-- ===========================================================================

BEGIN;

INSERT INTO items (item_id, item_name, manufacturer_name, cost, weight_kg)
OVERRIDING SYSTEM VALUE
VALUES
    ( 1, 'Wireless Earbuds', 'Aurora Audio', 89.90, 0.058),
    ( 2, 'Over-Ear Headphones', 'Aurora Audio', 219.00, 0.295),
    ( 3, 'Portable Speaker', 'Aurora Audio', 64.50, 0.560),
    ( 4, 'Soundbar', 'Aurora Audio', 349.00, 2.850),
    ( 5, 'Ceramic Mug Set', 'Basalt Home', 24.90, 1.420),
    ( 6, 'Linen Bedsheet Set', 'Basalt Home', 129.00, 1.850),
    ( 7, 'Scented Candle', 'Basalt Home', 18.50, 0.340),
    ( 8, 'Storage Basket', 'Basalt Home', 32.00, 0.780),
    ( 9, 'Trail Backpack', 'Cindermill Outdoors', 149.00, 1.120),
    (10, 'Insulated Bottle', 'Cindermill Outdoors', 38.90, 0.395),
    (11, 'Camping Lantern', 'Cindermill Outdoors', 45.00, 0.480),
    (12, 'Two-Person Tent', 'Cindermill Outdoors', 289.00, 3.400),
    (13, 'Fitness Tracker', 'Delta Peak', 159.00, 0.042),
    (14, 'Yoga Mat', 'Delta Peak', 54.00, 1.250),
    (15, 'Resistance Band Set', 'Delta Peak', 29.90, 0.620),
    (16, 'Adjustable Dumbbell', 'Delta Peak', 199.00, 12.500),
    (17, 'Chef Knife', 'Everly Kitchen', 89.00, 0.240),
    (18, 'Cast Iron Skillet', 'Everly Kitchen', 74.50, 2.950),
    (19, 'Espresso Grinder', 'Everly Kitchen', 179.00, 1.680),
    (20, 'Silicone Spatula Set', 'Everly Kitchen', 16.90, 0.180);

-- Fast-forward the identity sequence past the explicit IDs above.
SELECT setval(pg_get_serial_sequence('items', 'item_id'),
              (SELECT MAX(item_id) FROM items));

COMMIT;
