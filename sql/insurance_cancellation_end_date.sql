begin;
alter table public.courier_target_reserve
    add column if not exists insurance_end_date date;
comment on column public.courier_target_reserve.insurance_end_date is
    'Inclusive insurance end date. Insurance fees and automatic reserve top-ups stop in the following calendar month.';
notify pgrst, 'reload schema';
commit;
