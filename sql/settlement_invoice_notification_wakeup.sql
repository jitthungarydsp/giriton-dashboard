-- Run after settlement_invoice_notifications.sql on Supabase.
begin;
create extension if not exists pg_cron with schema pg_catalog;
create extension if not exists pg_net with schema extensions;

-- Wake the API before the Budapest morning digest or when committed events are waiting.
select cron.schedule('jitt-invoice-notification-wakeup', '* * * * *', $job$
    select net.http_get(url := 'https://futar.jitt.hu/api/health', timeout_milliseconds := 60000)
    where (now() at time zone 'Europe/Budapest')::time between time '07:57' and time '08:02'
       or exists (select 1 from settlement.invoice_notification_delivery where state = 'pending')
       or exists (select 1 from settlement.invoice_notification_event where
                  (requires_immediate and immediate_delivery is null)
                  or (digest_delivery is null and digest_day < (now() at time zone 'Europe/Budapest')::date)
                  or (digest_delivery is null and digest_day = (now() at time zone 'Europe/Budapest')::date
                      and (now() at time zone 'Europe/Budapest')::time >= time '08:00'))
       or ((now() at time zone 'Europe/Budapest')::time >= time '08:00'
           and extract(day from now() at time zone 'Europe/Budapest') >= 19
           and not exists (select 1 from settlement.invoice_notification_delivery
                           where digest_day = (now() at time zone 'Europe/Budapest')::date))
$job$);
commit;
