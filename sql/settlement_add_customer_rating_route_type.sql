begin;

alter table public.bill_jitt_invoice_customer_rating_bonus
    add column if not exists route_type text not null default 'normal'
    check (route_type in ('normal', 'express', 'regional', 'any'));

alter table settlement.cfg_jitt_customer_rating_rules
    add column if not exists route_type text not null default 'normal'
    check (route_type in ('normal', 'express', 'regional', 'any'));

notify pgrst, 'reload schema';

commit;
