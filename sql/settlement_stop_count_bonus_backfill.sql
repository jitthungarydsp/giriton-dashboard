begin;

alter table settlement.jit_row
    add column if not exists courier_other_bonus_huf numeric not null default 0,
    add column if not exists courier_bonus_total_huf numeric not null default 0;

with stop_count_values as (
    select
        j.id,
        j.session_id,
        coalesce((
            select sum(settlement.safe_excel_numeric(item.value))
            from jsonb_each_text(j.normalized_data) as item(key, value)
            where lower(trim(item.key)) in (
                'stop-count bonus',
                'stop count bonus',
                'stop_count_bonus',
                'stopcount bonus',
                'stopcountbonus'
            )
        ), 0) as stop_count_bonus_huf
    from settlement.jit_row j
)
update settlement.jit_row j
set
    courier_other_bonus_huf = case
        when coalesce(j.is_route_primary, true) then stop_count_values.stop_count_bonus_huf
        else 0
    end,
    courier_bonus_total_huf =
        coalesce(j.courier_delay_bonus_huf, 0)
        + coalesce(j.courier_compliance_bonus_huf, 0)
        + case
            when coalesce(j.is_route_primary, true) then stop_count_values.stop_count_bonus_huf
            else 0
        end
from stop_count_values
where j.id = stop_count_values.id;

do $$
declare
    session_record record;
begin
    if to_regprocedure('settlement.refresh_courier_settlement_summary(uuid)') is not null then
        for session_record in
            select distinct session_id
            from settlement.jit_row
            where session_id is not null
        loop
            perform settlement.refresh_courier_settlement_summary(session_record.session_id);
        end loop;
    end if;
end $$;

commit;
