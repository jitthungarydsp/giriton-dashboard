-- Independent complaint drafts. Does not rewrite complaints or settlements.
begin;
create table if not exists settlement.route_delay_form_draft (
 id uuid primary key,
 work_date date not null,
 courier_id text not null,
 courier_name text not null,
 route_id text not null,
 source_filename text not null default '',
 source_row integer not null,
 data jsonb not null,
 content_hash text not null,
 state text not null default 'draft' check (state in ('draft','prepared','sent')),
 confirmation text not null default '',
 submitted_at timestamptz,
 updated_by text not null default '',
 updated_at timestamptz not null default now(),
 unique (work_date,courier_id,route_id),
 check (state <> 'sent' or (submitted_at is not null and length(trim(confirmation)) >= 5))
);
alter table settlement.route_delay_form_draft enable row level security;
revoke all on settlement.route_delay_form_draft from anon, authenticated;
grant select,insert,update on settlement.route_delay_form_draft to service_role;
commit;
