-- Start the September 2026 PWA complaints workflow from a clean slate.
-- Deletes complaints and their response documents only.
-- Settlement summaries, finance snapshots and manual adjustments are kept.

begin;

delete from public.peopleforce_documents
where document_month::date = date '2026-09-01'
  and lower(split_part(document_type, ':', 1)) = 'complaint_response';

with deleted_complaints as (
    delete from public.peopleforce_complaints
    where document_month::date = date '2026-09-01'
    returning id
)
select
    'September 2026 complaints cleared' as result,
    count(*) as deleted_complaints
from deleted_complaints;

commit;
