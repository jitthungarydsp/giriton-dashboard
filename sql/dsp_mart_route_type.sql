alter table public.mart_dsp_route_stories
    add column if not exists route_type text not null default 'express'
        check (route_type in ('express', 'normal', 'regional'));

create index if not exists mart_dsp_route_stories_route_type_idx
    on public.mart_dsp_route_stories (work_date desc, route_type);

notify pgrst, 'reload schema';
