// Run with @electric-sql/pglite available on NODE_PATH. Uses an isolated,
// in-memory database; no application connection settings are read.
const { PGlite } = require('@electric-sql/pglite');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const assert = require('node:assert/strict');

(async () => {
  const db = new PGlite();
  try {
    await db.exec(`
      create role anon; create role authenticated; create role service_role;
      create schema settlement;
      create table settlement.courier_monthly_closure (courier_id text, period_start date, status text);
      create table settlement.courier_finance_snapshot (courier_id text, period_start date, courier_name text, version int);
      create table settlement.mobile_settlement_period_config (period_start date, visibility_mode text);
      create table public.peopleforce_documents (courier_id text, document_month date, document_type text, note text);
      create table public.peopleforce_card_statuses (
        courier_id text, courier_name text, document_month date, action_key text,
        status text, status_note text, updated_by text, updated_at timestamptz
      );
      create table public.peopleforce_complaints (
        id text primary key, courier_id text, document_month date, document_type text,
        status text, admin_response text, responded_by text, responded_at timestamptz
      );
      insert into settlement.courier_finance_snapshot values ('7244','2026-09-01','Attila',1);
      insert into public.peopleforce_documents values ('7244','2026-09-01','tig','');
    `);
    const migration = readFileSync(resolve(__dirname, '../sql/pwa_dashboard_change_monthly_status.sql'), 'utf8');
    await db.exec(migration);
    await db.exec(migration); // Existing installations can safely rerun it.
    const change = async (target) => (await db.query(
      `select settlement.pwa_change_monthly_status('7244','2026-09-01',$1,'Új számla szükséges','admin') as result`,
      [target]
    )).rows[0].result;
    await db.exec(`
      insert into public.peopleforce_complaints values
        ('invoice','7244','2026-09-01','invoice_check','new',null,null,null),
        ('reply','7244','2026-09-01','settlement','open','Korábbi válasz','old',now()),
        ('null-status','7244','2026-09-01','invoice_submit',null,null,null,null),
        ('tig','7244','2026-09-01','tig','in_progress',null,null,null),
        ('other-courier','9999','2026-09-01','invoice_check','new',null,null,null),
        ('other-month','7244','2026-08-01','invoice_check','new',null,null,null),
        ('other-process','7244','2026-09-01','invoice_check:advance','new',null,null,null),
        ('resolved','7244','2026-09-01','invoice_check','resolved','Kész','old',now());
    `);
    assert.equal((await change('invoice_upload')).closedComplaints, 4);
    const complaints = Object.fromEntries((await db.query('select * from public.peopleforce_complaints')).rows.map(c => [c.id, c]));
    assert.equal(complaints.invoice.status, 'closed');
    assert.equal(complaints.invoice.responded_by, 'admin');
    assert.ok(complaints.invoice.responded_at);
    assert.equal(complaints.reply.admin_response, 'Korábbi válasz\n\nAdmin státuszváltás: invoice_upload. Új számla szükséges');
    for (const id of ['other-courier', 'other-month', 'other-process']) assert.equal(complaints[id].status, 'new');
    assert.equal(complaints.resolved.admin_response, 'Kész');
    const audit = (await db.query('select previous_complaints from pwa_dashboard_read.monthly_status_change_audit')).rows[0];
    assert.equal(audit.previous_complaints.length, 4);
    assert.equal(audit.previous_complaints.find(c => c.id === 'reply').admin_response, 'Korábbi válasz');
    assert.equal((await change('invoice_upload')).closedComplaints, 0);
    // Fail after complaints have been updated: neither closure nor audit survives.
    await db.exec(`
      update public.peopleforce_complaints set status='open', admin_response=null where id='invoice';
      alter table public.peopleforce_card_statuses add constraint reject_test_status check (status_note not like '%invoice_check.%');
    `);
    // Supply the invoice so validation succeeds and the insert constraint fails.
    await db.exec("insert into public.peopleforce_documents values ('7244','2026-09-01','invoice','')");
    await assert.rejects(change('invoice_check'), /reject_test_status/);
    assert.equal((await db.query("select status from public.peopleforce_complaints where id='invoice'")).rows[0].status, 'open');
    assert.equal((await db.query('select count(*)::int as n from pwa_dashboard_read.monthly_status_change_audit')).rows[0].n, 2);
    await db.exec('alter table public.peopleforce_card_statuses drop constraint reject_test_status');
    await db.exec("delete from public.peopleforce_documents where document_type='invoice'");
    await assert.rejects(change('payment_wait'), /Előbb fel kell tölteni/);
    assert.equal((await db.query("select status from public.peopleforce_complaints where id='invoice'")).rows[0].status, 'open');
    await db.exec("insert into settlement.courier_monthly_closure values ('7244','2026-09-01','done')");
    await assert.rejects(change('invoice_upload'), /kifizetés már lezárva/);
    assert.equal((await db.query("select status from public.peopleforce_complaints where id='invoice'")).rows[0].status, 'open');
    console.log('SQL integration passed: closure, scope, replies, audit, repeat save, rollback, invoice and payment guards.');
  } finally {
    await db.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
