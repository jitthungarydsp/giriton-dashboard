-- All months: zero differences prove that both metric tables roll up together.
select s.period_start,
       s.definition_version,
       count(d.courier_metric_id) as courier_month_count,
       (s.source_counts ->> 'finance_covered_couriers')::int as finance_covered_couriers,
       s.completed_flow_count,
       s.complaint_total,
       sum(d.financial_complaint_count) as detail_complaint_count,
       s.complaint_total - coalesce(sum(d.financial_complaint_count),0) as complaint_difference,
       s.response_count - coalesce(sum(d.responded_complaint_count),0) as response_difference,
       s.deductions_total_huf - coalesce(sum(d.deductions_huf),0) as deduction_difference,
       s.deductions_total_huf,
       s.source_counts ->> 'response_timed_count' as measurable_response_count,
       s.calculated_at
from settlement.monthly_process_metric_summary s
left join settlement.courier_monthly_process_metric d
  on d.summary_id=s.summary_id and d.period_start=s.period_start
group by s.period_start,s.summary_id
order by s.period_start;

-- Missing finance and unmeasurable events are explicit, not inferred as zero time.
select period_start,courier_id,courier_name,
       closure_snapshot ->> 'finance_available' as finance_available,
       closure_snapshot -> 'missing_events' as missing_events,
       closure_snapshot -> 'invalid_stage_order' as invalid_stage_order,
       closure_snapshot ->> 'response_timed_count' as measurable_response_count
from settlement.courier_monthly_process_metric
where closure_snapshot ->> 'finance_available' = 'false'
   or jsonb_array_length(coalesce(closure_snapshot -> 'missing_events','[]'::jsonb)) > 0
order by period_start,courier_name;
