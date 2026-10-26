-- A PWA MűszakPro-vs-Hub eltérésjelzéséhez szükséges Hub-körszám.
-- Futtasd a Supabase SQL Editorban egyszer.
alter table public.muszakpro_booking_identity_matches
    add column if not exists hub_shift_count integer;

comment on column public.muszakpro_booking_identity_matches.hub_shift_count is
    'Az adott napon és normalizált e-mailnél talált Hub-műszakok száma';
