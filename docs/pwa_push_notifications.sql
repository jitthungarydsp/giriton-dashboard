create table if not exists public.pwa_push_subscriptions (
    id bigserial primary key,
    courier_id integer not null,
    courier_name text,
    endpoint text not null unique,
    p256dh text not null,
    auth text not null,
    user_agent text,
    active boolean not null default true,
    last_seen_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_pwa_push_subscriptions_courier_active
    on public.pwa_push_subscriptions (courier_id, active, updated_at desc);

do $$
declare
    constraint_record record;
begin
    for constraint_record in
        select c.conname
        from pg_constraint c
        join pg_class t on t.oid = c.conrelid
        join pg_namespace n on n.oid = t.relnamespace
        where n.nspname = 'public'
          and t.relname = 'pwa_push_subscriptions'
          and c.contype in ('f', 'c')
          and pg_get_constraintdef(c.oid) ilike '%courier_id%'
    loop
        execute format('alter table public.pwa_push_subscriptions drop constraint if exists %I', constraint_record.conname);
    end loop;
end $$;

create table if not exists public.pwa_push_delivery_log (
    id bigserial primary key,
    courier_id integer not null,
    work_date date not null default current_date,
    notification_type text not null,
    status text not null,
    message text,
    sent_at timestamptz not null default now()
);

create index if not exists idx_pwa_push_delivery_log_courier_type
    on public.pwa_push_delivery_log (courier_id, notification_type, sent_at desc);

create index if not exists idx_pwa_push_delivery_log_status
    on public.pwa_push_delivery_log (status, sent_at desc);

grant select, insert, update on public.pwa_push_subscriptions to service_role;
grant usage, select on sequence public.pwa_push_subscriptions_id_seq to service_role;

grant select, insert, update on public.pwa_push_delivery_log to service_role;
grant usage, select on sequence public.pwa_push_delivery_log_id_seq to service_role;
