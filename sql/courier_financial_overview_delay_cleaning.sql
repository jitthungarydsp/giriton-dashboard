begin;

alter table public.courier_financial_overview_delay
    add column if not exists cleaned_delay_count integer not null default 0,
    add column if not exists uncleaned_delay_count integer not null default 0,
    add column if not exists cleaned_delay_minutes integer not null default 0,
    add column if not exists uncleaned_delay_minutes integer not null default 0,
    add column if not exists has_delay_cleaning boolean not null default false,
    add column if not exists cleaned_reasons jsonb not null default '[]'::jsonb;

create index if not exists courier_financial_overview_delay_cleaning_idx
    on public.courier_financial_overview_delay (courier_id, year, month, has_delay_cleaning);

commit;

notify pgrst, 'reload schema';
