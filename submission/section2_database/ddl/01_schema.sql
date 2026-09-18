-- ===========================================================================
-- Section 2 -- e-commerce sales transactions: physical schema.
--
-- Runs first in /docker-entrypoint-initdb.d/, ahead of the generated seed
-- files 02-04. Postgres executes that directory in lexical order, which is the
-- only reason the numeric prefixes exist.
--
-- Everything here is idempotent-free on purpose: the entrypoint only runs these
-- scripts when the data volume is empty, so a re-run means a fresh database.
-- `docker compose down -v` is how you get back to that state.
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- members -- the Section 1 output, loaded verbatim.
--
-- This table is an upstream contract, not a design decision: the columns are
-- exactly what submission/section1_data_pipeline writes to
-- output/successful/successful_applications_<ts>.csv, with `birthday` promoted
-- from a YYYYMMDD string to a real DATE at the boundary.
-- ---------------------------------------------------------------------------
CREATE TABLE members (
    membership_id TEXT    PRIMARY KEY,
    first_name    TEXT    NOT NULL,
    last_name     TEXT    NOT NULL,
    email         TEXT    NOT NULL,
    birthday      DATE    NOT NULL,
    above_18      BOOLEAN NOT NULL,
    mobile        TEXT    NOT NULL,

    -- Section 1 validates this at ingestion; we re-assert it so a hand-written
    -- INSERT cannot smuggle in a badly formatted number.
    CONSTRAINT members_mobile_is_8_digits
        CHECK (mobile ~ '^[0-9]{8}$'),

    -- `above_18` is derivable from `birthday`, so storing it is a deliberate
    -- denormalisation to keep the upstream contract intact. Section 1 owns the
    -- rule ("over 18 as of 1 Jan 2022", read strictly); this CHECK only refuses
    -- a row where the flag contradicts the birthday.
    --
    -- age > 18 on 2022-01-01  <=>  19th birthday on or before 2022-01-01
    --                         <=>  birthday <= 2003-01-01
    --
    -- If Section 1's reference date ever moves, this load fails loudly rather
    -- than drifting silently -- which is the point.
    CONSTRAINT members_above_18_matches_birthday
        CHECK (above_18 = (birthday <= DATE '2003-01-01'))
);

COMMENT ON TABLE  members IS
    'Members of the e-commerce platform, loaded from the Section 1 pipeline output. One row per successful membership application.';
COMMENT ON COLUMN members.membership_id IS
    'Section 1 identifier: <last_name>_<first 5 hex chars of SHA256(YYYYMMDD birthday)>. Unique only per (last_name, birthday) -- see the README assumption on collisions.';
COMMENT ON COLUMN members.first_name IS
    'First token of the applicant name after salutations and post-nominals are stripped.';
COMMENT ON COLUMN members.last_name IS
    'Everything after the first token. Empty string for a mononym; never NULL.';
COMMENT ON COLUMN members.email IS
    'Applicant email. Validated upstream as ending in .com or .net.';
COMMENT ON COLUMN members.birthday IS
    'Date of birth. Arrives from Section 1 as a YYYYMMDD string and is parsed to DATE by the seed generator.';
COMMENT ON COLUMN members.above_18 IS
    'Whether the applicant was over 18 on 2022-01-01. Denormalised from birthday to preserve the Section 1 contract; kept honest by members_above_18_matches_birthday.';
COMMENT ON COLUMN members.mobile IS
    'Eight-digit mobile number, whitespace already stripped by Section 1.';


-- ---------------------------------------------------------------------------
-- items -- the product catalogue.
--
-- The natural key is (item_name, manufacturer_name) and it is enforced as
-- UNIQUE, so 3NF is satisfied. The surrogate `item_id` exists so the junction
-- table carries one narrow bigint instead of two text columns.
-- ---------------------------------------------------------------------------
CREATE TABLE items (
    item_id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_name         TEXT          NOT NULL,
    manufacturer_name TEXT          NOT NULL,
    cost              NUMERIC(10,2) NOT NULL,
    weight_kg         NUMERIC(8,3)  NOT NULL,

    CONSTRAINT items_name_manufacturer_unique
        UNIQUE (item_name, manufacturer_name),

    -- A free item is plausible (a promotion); a negative price is not.
    CONSTRAINT items_cost_non_negative CHECK (cost >= 0),
    -- A weightless physical good is not: zero would break shipping maths.
    CONSTRAINT items_weight_positive   CHECK (weight_kg > 0)
);

COMMENT ON TABLE  items IS
    'Product catalogue. One row per distinct (item_name, manufacturer_name) pair.';
COMMENT ON COLUMN items.item_id IS
    'Surrogate key. The natural key is (item_name, manufacturer_name), enforced by items_name_manufacturer_unique.';
COMMENT ON COLUMN items.item_name IS
    'Product name as listed on the website.';
COMMENT ON COLUMN items.manufacturer_name IS
    'Manufacturer. A lone attribute today, so it lives here rather than in its own table; split it out when the business needs manufacturer attributes (country, lead time, contact).';
COMMENT ON COLUMN items.cost IS
    'CURRENT list price. Historical transactions snapshot their own price in transaction_items.unit_cost_at_purchase and are unaffected when this changes.';
COMMENT ON COLUMN items.weight_kg IS
    'Current shipping weight in kilograms. Snapshotted per line item for the same reason as cost.';


-- ---------------------------------------------------------------------------
-- transactions -- the purchase header.
--
-- total_items_price / total_items_weight are derivable from transaction_items,
-- so they are denormalised. Three reasons they stay: the brief names them as
-- transaction attributes, they are the invoiced figure (a point-in-time
-- snapshot), and the top-10-spending query then reads one table instead of
-- aggregating a junction. The drift risk that normally condemns this is closed
-- by refresh_transaction_totals() below -- the database maintains them, not
-- whoever writes the INSERT.
-- ---------------------------------------------------------------------------
CREATE TABLE transactions (
    transaction_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    membership_id      TEXT          NOT NULL,
    transaction_ts     TIMESTAMPTZ   NOT NULL,
    total_items_price  NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_items_weight NUMERIC(10,3) NOT NULL DEFAULT 0,

    -- RESTRICT, not CASCADE: erasing a member who has sales history would take
    -- the revenue with them. Anonymise the member row instead.
    CONSTRAINT transactions_member_fk
        FOREIGN KEY (membership_id) REFERENCES members (membership_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,

    CONSTRAINT transactions_total_price_non_negative  CHECK (total_items_price  >= 0),
    CONSTRAINT transactions_total_weight_non_negative CHECK (total_items_weight >= 0)
);

COMMENT ON TABLE  transactions IS
    'Purchase header. One row per basket checked out by a member; the items bought hang off transaction_items.';
COMMENT ON COLUMN transactions.transaction_id IS
    'Surrogate key. There is no natural key -- a member can buy the same basket twice in the same second.';
COMMENT ON COLUMN transactions.membership_id IS
    'Purchasing member. ON DELETE RESTRICT so sales history cannot be orphaned.';
COMMENT ON COLUMN transactions.transaction_ts IS
    'When the purchase was made. TIMESTAMPTZ so a move off UTC does not silently reinterpret historical rows.';
COMMENT ON COLUMN transactions.total_items_price IS
    'SUM(quantity * unit_cost_at_purchase) over this transaction. Maintained by refresh_transaction_totals(); do not set it by hand.';
COMMENT ON COLUMN transactions.total_items_weight IS
    'SUM(quantity * unit_weight_at_purchase) over this transaction, in kg. Maintained by refresh_transaction_totals(); do not set it by hand.';


-- ---------------------------------------------------------------------------
-- transaction_items -- the M:N junction between a purchase and the catalogue.
--
-- unit_cost_at_purchase / unit_weight_at_purchase are snapshots, not lookups.
-- items.cost is the *current* price; a transaction from 60 days ago must not
-- reprice itself when marketing runs a sale. Without these columns,
-- `UPDATE items SET cost = ...` silently rewrites every revenue report ever run.
-- ---------------------------------------------------------------------------
CREATE TABLE transaction_items (
    transaction_id          BIGINT        NOT NULL,
    item_id                 BIGINT        NOT NULL,
    quantity                INTEGER       NOT NULL,
    unit_cost_at_purchase   NUMERIC(10,2) NOT NULL,
    unit_weight_at_purchase NUMERIC(8,3)  NOT NULL,

    -- Composite PK: one line per item per transaction. Buying three of
    -- something is quantity = 3, not three rows.
    CONSTRAINT transaction_items_pk
        PRIMARY KEY (transaction_id, item_id),

    -- CASCADE: a line item has no meaning without its header.
    CONSTRAINT transaction_items_transaction_fk
        FOREIGN KEY (transaction_id) REFERENCES transactions (transaction_id)
        ON DELETE CASCADE,

    -- RESTRICT: a catalogue item that has ever sold cannot be deleted.
    -- Discontinue it with a flag instead.
    CONSTRAINT transaction_items_item_fk
        FOREIGN KEY (item_id) REFERENCES items (item_id)
        ON DELETE RESTRICT,

    CONSTRAINT transaction_items_quantity_positive CHECK (quantity > 0),
    CONSTRAINT transaction_items_cost_non_negative CHECK (unit_cost_at_purchase >= 0),
    CONSTRAINT transaction_items_weight_positive   CHECK (unit_weight_at_purchase > 0)
);

COMMENT ON TABLE  transaction_items IS
    'Line items. Resolves the many-to-many between transactions and items, and snapshots the price and weight that applied at purchase time.';
COMMENT ON COLUMN transaction_items.transaction_id IS
    'Parent transaction. ON DELETE CASCADE -- a line cannot outlive its header.';
COMMENT ON COLUMN transaction_items.item_id IS
    'Catalogue item bought. ON DELETE RESTRICT -- an item with sales history stays.';
COMMENT ON COLUMN transaction_items.quantity IS
    'Units of this item in this transaction. Always >= 1.';
COMMENT ON COLUMN transaction_items.unit_cost_at_purchase IS
    'items.cost as it stood when this transaction was made. Immutable history; never re-read from items.';
COMMENT ON COLUMN transaction_items.unit_weight_at_purchase IS
    'items.weight_kg as it stood when this transaction was made.';


-- ---------------------------------------------------------------------------
-- Indexes.
--
-- Postgres indexes a PRIMARY KEY and a UNIQUE constraint automatically but does
-- NOT index a foreign key, so every FK that is joined or filtered on needs one
-- declared by hand.
--
-- transaction_items(transaction_id) is deliberately absent: it is the leading
-- column of transaction_items_pk, so that index already serves it.
-- ---------------------------------------------------------------------------

-- Serves: queries/top10_members_by_spending.sql (members -> transactions join),
-- and "show me this member's order history" generally.
CREATE INDEX transactions_membership_id_idx
    ON transactions (membership_id);
COMMENT ON INDEX transactions_membership_id_idx IS
    'Member -> transactions join. Also covers the FK, which Postgres does not index automatically.';

-- Serves: every date-bounded analytic ("revenue last quarter"), and the
-- partition key if transactions is ever range-partitioned by month.
CREATE INDEX transactions_transaction_ts_idx
    ON transactions (transaction_ts);
COMMENT ON INDEX transactions_transaction_ts_idx IS
    'Date-range analytics over transactions. Becomes the partition key if this table is ever partitioned by month.';

-- Serves: queries/top3_items_by_frequency.sql (grouping the junction by item)
-- and the RESTRICT check when someone tries to delete a catalogue item.
CREATE INDEX transaction_items_item_id_idx
    ON transaction_items (item_id);
COMMENT ON INDEX transaction_items_item_id_idx IS
    'Item -> line items aggregation for the top-3-items query, and the ON DELETE RESTRICT lookup on items.';


-- ---------------------------------------------------------------------------
-- Totals maintenance.
--
-- The trigger RECOMPUTES rather than validates, which means the seed generator
-- never has to compute money: it inserts headers with totals of 0, inserts the
-- line items, and the database fills in the rest. It also means a later
-- hand-written INSERT/UPDATE/DELETE on transaction_items cannot desync the
-- header.
--
-- ponytail: FOR EACH ROW, not FOR EACH STATEMENT. The statement-level form with
-- transition tables is strictly fewer UPDATEs, but Postgres forbids transition
-- tables on a multi-event trigger, so it costs three separate trigger
-- definitions plus TG_OP branching. The real workload is a basket of 1-5 lines,
-- where row-level fires 5 times instead of 1 -- nobody will measure that. The
-- ceiling is bulk loading: an N-line import does N re-aggregations. If a bulk
-- import ever gets slow, split this into three statement-level triggers
-- (INSERT / UPDATE / DELETE) using REFERENCING ... TABLE.
-- ---------------------------------------------------------------------------

CREATE FUNCTION refresh_transaction_totals(p_transaction_id BIGINT)
RETURNS VOID
LANGUAGE sql
AS $$
    UPDATE transactions t
       SET total_items_price  = COALESCE(agg.price,  0),
           total_items_weight = COALESCE(agg.weight, 0)
      FROM (
            SELECT SUM(ti.quantity * ti.unit_cost_at_purchase)   AS price,
                   SUM(ti.quantity * ti.unit_weight_at_purchase) AS weight
              FROM transaction_items ti
             WHERE ti.transaction_id = p_transaction_id
           ) AS agg
     WHERE t.transaction_id = p_transaction_id;
$$;

COMMENT ON FUNCTION refresh_transaction_totals(BIGINT) IS
    'Recompute one transaction header total from its line items. COALESCE to 0 so deleting the last line leaves 0, not NULL. A no-op if the header is already gone (cascade delete).';

CREATE FUNCTION transaction_items_totals_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- On UPDATE both branches run, so re-parenting a line to a different
    -- transaction refreshes the one it left as well as the one it joined.
    IF TG_OP <> 'INSERT' THEN
        PERFORM refresh_transaction_totals(OLD.transaction_id);
    END IF;

    IF TG_OP <> 'DELETE' THEN
        PERFORM refresh_transaction_totals(NEW.transaction_id);
    END IF;

    RETURN NULL;  -- AFTER trigger: the return value is ignored.
END;
$$;

COMMENT ON FUNCTION transaction_items_totals_trigger() IS
    'AFTER ROW trigger body for transaction_items. Dispatches to refresh_transaction_totals() for whichever header(s) the statement touched.';

CREATE TRIGGER transaction_items_maintain_totals
    AFTER INSERT OR UPDATE OR DELETE ON transaction_items
    FOR EACH ROW
    EXECUTE FUNCTION transaction_items_totals_trigger();

COMMENT ON TRIGGER transaction_items_maintain_totals ON transaction_items IS
    'Keeps transactions.total_items_price / total_items_weight equal to the sum over the line items, so the denormalised header cannot drift.';

COMMIT;
