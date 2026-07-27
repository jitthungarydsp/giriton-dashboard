create table if not exists settlement.courier_route_issue_review (
    issue_key text primary key,
    session_id text null,
    courier_id text not null,
    period_start date not null,
    period_end date not null,
    route_id text not null,
    order_id text null,
    issue_type text not null,
    status text not null default 'Vizsgálat',
    note text null,
    updated_by text null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint courier_route_issue_review_status_chk
        check (status in ('Nincs reklamáció', 'Vizsgálat', 'Elfogadva', 'Elutasítva', 'Lezárva'))
);

create index if not exists courier_route_issue_review_courier_period_idx
    on settlement.courier_route_issue_review (courier_id, period_start, period_end);

create index if not exists courier_route_issue_review_route_idx
    on settlement.courier_route_issue_review (route_id);

create table if not exists settlement.courier_route_issue_review_event (
    id bigserial primary key,
    issue_key text not null,
    session_id text null,
    courier_id text not null,
    route_id text not null,
    order_id text null,
    issue_type text not null,
    status text not null,
    note text null,
    performed_by text null,
    created_at timestamptz not null default now()
);

create index if not exists courier_route_issue_review_event_issue_idx
    on settlement.courier_route_issue_review_event (issue_key, created_at desc);

notify pgrst, 'reload schema';
