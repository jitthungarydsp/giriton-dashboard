begin;

alter table public.complaint_email_responses
    add column if not exists courier_id text,
    add column if not exists courier_name text,
    add column if not exists jitt_internal_id text,
    add column if not exists source_courier_id text,
    add column if not exists source_jitt_internal_id text,
    add column if not exists courier_match_status text;

alter table public.coordinator_shift_email_notices
    add column if not exists courier_name text,
    add column if not exists jitt_internal_id text,
    add column if not exists source_courier_id text,
    add column if not exists source_jitt_internal_id text,
    add column if not exists courier_match_status text;

alter table public.coordinator_shift_email_notices
    drop constraint if exists coordinator_shift_email_notices_check,
    drop constraint if exists coordinator_shift_email_notices_late_occurrence_check,
    add constraint coordinator_shift_email_notices_late_occurrence_check
        check (late_occurrence is null or (late_occurrence > 0 and event_type = 'late'));

create or replace function public.resolve_gmail_archive_courier()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
declare
    label text;
    normalized_name text;
    name_matches integer[];
    short_match integer;
    jitt_match integer;
    matched_courier integer;
begin
    if tg_table_name = 'coordinator_shift_email_notices' then
        label := new.courier_label;
    else
        -- The identifier immediately following the subject prefix belongs to the complaint.
        label := substring(new.subject from
            '(?i)panasz[[:space:]]+elb[íi]r[áa]lva[[:space:]]*:[[:space:]]*(?:\[[^]]+\]|[^[:space:]]+)[[:space:]]+[-–][[:space:]]+(.+?)[[:space:]]+[-–][[:space:]]+[^-–]+$');
    end if;

    new.source_courier_id := coalesce(
        substring(new.body_text from '(?im)^[[:blank:]]*fut[áa]r[[:blank:]-]*(?:azonos[íi]t[óo]|id)[[:blank:]]*:[[:blank:]]*([0-9]{3,8})\M'),
        substring(label from '\m([0-9]{3,8})\M'));
    new.source_jitt_internal_id := coalesce(
        substring(new.body_text from '(?im)^[[:blank:]]*jitt[[:blank:]-]*(?:bels[őo][[:blank:]]+)?(?:azonos[íi]t[óo]|id)[[:blank:]]*:[[:blank:]]*([0-9]{16})\M'),
        substring(label from '\m([0-9]{16})\M'));

    new.courier_name := nullif(btrim(regexp_replace(regexp_replace(regexp_replace(
        label, '[[:space:]]*\([^)]*\)[[:space:]]*$', ''),
        '\m[0-9]{3,16}\M', ' ', 'g'), '[[:space:]]+', ' ', 'g')), '');
    normalized_name := lower(new.courier_name);
    new.courier_id := null;
    new.jitt_internal_id := null;
    new.courier_match_status := 'unresolved';

    if new.source_courier_id is not null then
        select candidate.courier_id into short_match
        from (
            select courier_id from public.courier_master
            where courier_id = new.source_courier_id::integer
            union
            select courier_id from public.courier_hub_courier_identity_raw
            where courier_id = new.source_courier_id::integer
        ) candidate;
    end if;
    if new.source_jitt_internal_id is not null then
        select courier_id into jitt_match
        from public.courier_hub_courier_identity_raw
        where jitt_internal_id = new.source_jitt_internal_id;
    end if;
    if normalized_name is not null then
        select array_agg(distinct candidate.courier_id) into name_matches
        from (
            select courier_id from public.courier_master
            where lower(btrim(regexp_replace(regexp_replace(courier_name,
                '\m[0-9]{3,16}\M', ' ', 'g'), '[[:space:]]+', ' ', 'g'))) = normalized_name
            union
            select courier_id from public.courier_hub_courier_identity_raw
            where lower(btrim(regexp_replace(name_without_identifier, '[[:space:]]+', ' ', 'g'))) = normalized_name
        ) candidate;
    end if;

    matched_courier := coalesce(jitt_match, short_match);
    if (short_match is not null and jitt_match is not null and short_match <> jitt_match)
        or (matched_courier is not null and cardinality(name_matches) = 1 and matched_courier <> name_matches[1]) then
        new.courier_match_status := 'conflict';
        return new;
    end if;

    if matched_courier is not null then
        new.courier_match_status := 'matched_by_id';
    elsif new.source_courier_id is null and new.source_jitt_internal_id is null then
        if cardinality(name_matches) = 1 then
            matched_courier := name_matches[1];
            new.courier_match_status := 'matched_by_name';
        elsif cardinality(name_matches) > 1 then
            new.courier_match_status := 'ambiguous';
        end if;
    end if;

    if matched_courier is not null then
        new.courier_id := matched_courier::text;
        if jitt_match is not null then
            new.jitt_internal_id := new.source_jitt_internal_id;
        else
            select min(jitt_internal_id) into new.jitt_internal_id
            from public.courier_hub_courier_identity_raw
            where courier_id = matched_courier
            having count(distinct jitt_internal_id) = 1;
        end if;
    end if;
    return new;
end;
$$;

revoke execute on function public.resolve_gmail_archive_courier() from public, anon, authenticated;
grant execute on function public.resolve_gmail_archive_courier() to service_role;

drop trigger if exists resolve_gmail_archive_courier on public.complaint_email_responses;
create trigger resolve_gmail_archive_courier
    before insert or update of subject, body_text on public.complaint_email_responses
    for each row execute function public.resolve_gmail_archive_courier();

drop trigger if exists resolve_gmail_archive_courier on public.coordinator_shift_email_notices;
create trigger resolve_gmail_archive_courier
    before insert or update of subject, body_text, courier_label on public.coordinator_shift_email_notices
    for each row execute function public.resolve_gmail_archive_courier();

update public.complaint_email_responses set subject = subject;
update public.coordinator_shift_email_notices set subject = subject;

create index if not exists complaint_email_responses_courier_idx
    on public.complaint_email_responses (courier_id, received_at desc);
create index if not exists coordinator_shift_email_notices_courier_idx
    on public.coordinator_shift_email_notices (courier_id, received_at desc);

commit;
