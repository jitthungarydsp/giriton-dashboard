begin;
create table if not exists public.webshop_products (
 id uuid primary key default gen_random_uuid(), name text not null,
 description text not null default '', category text not null default '', active boolean not null default true,
 image_bucket text, image_path text, created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
create table if not exists public.webshop_variants (
 id uuid primary key default gen_random_uuid(), product_id uuid not null references public.webshop_products(id),
 sku text not null, price_huf integer not null check(price_huf >= 0), size text not null,
 type text not null, attributes jsonb not null default '{}', active boolean not null default true
);
create unique index if not exists webshop_sku_unique on public.webshop_variants(lower(sku));
create index if not exists webshop_variant_product_idx on public.webshop_variants(product_id);
create table if not exists public.webshop_attributes (
 id uuid primary key default gen_random_uuid(), name text not null unique,
 "values" jsonb not null default '[]' check(jsonb_typeof("values") = 'array'),
 required boolean not null default false, created_at timestamptz not null default now()
);
create table if not exists public.webshop_requests (
 id uuid primary key default gen_random_uuid(), request_key uuid not null,
 courier_id text not null, courier_name text not null,
 note text not null default '', total_huf bigint not null default 0,
 status text not null default 'received' check(status in ('received','processing','ready','fulfilled','rejected','withdrawn')),
 admin_response text not null default '', created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
 unique(courier_id, request_key)
);
create index if not exists webshop_requests_owner_date_idx on public.webshop_requests(courier_id, created_at desc);
create index if not exists webshop_requests_status_date_idx on public.webshop_requests(status, created_at desc);
create table if not exists public.webshop_request_items (
 id uuid primary key default gen_random_uuid(), request_id uuid not null references public.webshop_requests(id),
 variant_id uuid not null references public.webshop_variants(id), product_name text not null,
 sku text not null, size text not null, type text not null, attributes jsonb not null,
 unit_price_huf integer not null, quantity integer not null check(quantity between 1 and 99)
);
create index if not exists webshop_request_items_parent_idx on public.webshop_request_items(request_id);
create table if not exists public.webshop_request_events (
 id uuid primary key default gen_random_uuid(), request_id uuid not null references public.webshop_requests(id),
 status text not null, message text not null default '', actor text not null, created_at timestamptz not null default now()
);
create index if not exists webshop_events_parent_idx on public.webshop_request_events(request_id, created_at);

-- A product and all its variants are saved in one transaction.
create or replace function public.pwa_save_webshop_product(p_product jsonb, p_variants jsonb)
returns uuid language plpgsql security invoker set search_path=public as $$
declare pid uuid; v jsonb; vid uuid; keep_ids uuid[] := '{}';
begin
 if jsonb_array_length(p_variants) not between 1 and 100 then raise exception 'Legalább egy változat szükséges.'; end if;
 if nullif(p_product->>'id','') is null then
  insert into public.webshop_products(name,description,category,active)
  values(p_product->>'name',p_product->>'description',p_product->>'category',(p_product->>'active')::boolean) returning id into pid;
 else
  pid := (p_product->>'id')::uuid;
  perform 1 from public.webshop_products where id=pid for update;
  if not found then raise exception 'A termék nem található.'; end if;
  update public.webshop_products set name=p_product->>'name',description=p_product->>'description',category=p_product->>'category',
   active=(p_product->>'active')::boolean,updated_at=now() where id=pid;
 end if;
 for v in select * from jsonb_array_elements(p_variants) loop
  if nullif(v->>'id','') is null then
   insert into public.webshop_variants(product_id,sku,price_huf,size,type,attributes,active)
    values(pid,v->>'sku',(v->>'price_huf')::integer,v->>'size',v->>'type',coalesce(v->'attributes','{}'),true) returning id into vid;
  else
   vid := (v->>'id')::uuid;
   update public.webshop_variants set sku=v->>'sku',price_huf=(v->>'price_huf')::integer,size=v->>'size',type=v->>'type',
    attributes=coalesce(v->'attributes','{}'),active=true where id=vid and product_id=pid;
   if not found then raise exception 'A változat nem ehhez a termékhez tartozik.'; end if;
  end if;
  keep_ids := array_append(keep_ids,vid);
 end loop;
 update public.webshop_variants set active=false where product_id=pid and not(id=any(keep_ids));
 return pid;
end; $$;

-- Prices and availability are checked here, never trusted from the basket.
create or replace function public.pwa_create_webshop_request(p_key uuid,p_courier text,p_name text,p_note text,p_items jsonb)
returns uuid language plpgsql security invoker set search_path=public as $$
declare rid uuid; item jsonb; variant public.webshop_variants; product public.webshop_products;
 qty integer; amount bigint := 0;
begin
 perform pg_advisory_xact_lock(hashtextextended(p_courier||':'||p_key::text,0));
 select id into rid from public.webshop_requests where courier_id=p_courier and request_key=p_key;
 if found then return rid; end if;
 if jsonb_array_length(p_items) not between 1 and 50 then raise exception 'A kosár 1–50 tételt tartalmazhat.'; end if;
 if (select count(distinct x->>'variant_id') from jsonb_array_elements(p_items) x) <> jsonb_array_length(p_items)
 then raise exception 'Ismétlődő kosártétel.'; end if;
 insert into public.webshop_requests(request_key,courier_id,courier_name,note) values(p_key,p_courier,p_name,p_note) returning id into rid;
 for item in select * from jsonb_array_elements(p_items) order by value->>'variant_id' loop
  select * into variant from public.webshop_variants where id=(item->>'variant_id')::uuid;
  if not found then raise exception 'A kosárban nem elérhető termék van.'; end if;
  select * into product from public.webshop_products where id=variant.product_id for share;
  select * into variant from public.webshop_variants where id=(item->>'variant_id')::uuid for share;
  if not product.active or not variant.active then raise exception 'A termék már nem igényelhető. Frissítsd a kosarat.'; end if;
  qty := (item->>'quantity')::integer;
  if qty not between 1 and 99 then raise exception 'Érvénytelen darabszám.'; end if;
  if variant.price_huf <> (item->>'expected_price_huf')::integer then raise exception 'Megváltozott az ár. Frissítsd és ellenőrizd a kosarat.'; end if;
  insert into public.webshop_request_items(request_id,variant_id,product_name,sku,size,type,attributes,unit_price_huf,quantity)
   values(rid,variant.id,product.name,variant.sku,variant.size,variant.type,variant.attributes,variant.price_huf,qty);
  amount := amount + variant.price_huf::bigint*qty;
 end loop;
 update public.webshop_requests set total_huf=amount where id=rid;
 insert into public.webshop_request_events(request_id,status,actor) values(rid,'received',p_name);
 return rid;
end; $$;

create or replace function public.pwa_manage_webshop_request(p_id uuid,p_status text,p_response text,p_actor text)
returns setof public.webshop_requests language plpgsql security invoker set search_path=public as $$
declare previous text;
begin
 select status into previous from public.webshop_requests where id=p_id for update;
 if not found then raise exception 'Az igény nem található.'; end if;
 if previous in ('fulfilled','rejected','withdrawn') then raise exception 'Ez az igény már lezárt.'; end if;
 if not (p_status=previous or (previous='received' and p_status in ('processing','ready','rejected'))
 or (previous='processing' and p_status in ('ready','rejected')) or (previous='ready' and p_status in ('fulfilled','rejected')))
 then raise exception 'Nem megengedett státuszváltás.'; end if;
 if p_status='rejected' and length(btrim(p_response)) < 5 then raise exception 'Elutasításhoz indoklás szükséges.'; end if;
 insert into public.webshop_request_events(request_id,status,message,actor) values(p_id,p_status,p_response,p_actor);
 return query update public.webshop_requests set status=p_status,admin_response=p_response,updated_at=now() where id=p_id returning *;
end; $$;

create or replace function public.pwa_save_webshop_attribute(p_attribute jsonb)
returns uuid language plpgsql security invoker set search_path=public as $$
declare aid uuid; old_name text;
begin
 if nullif(p_attribute->>'id','') is not null then
  aid := (p_attribute->>'id')::uuid;
  select name into old_name from public.webshop_attributes where id=aid for update;
  if not found then raise exception 'A tulajdonság nem található.'; end if;
  if old_name <> p_attribute->>'name' then raise exception 'Meglévő tulajdonság neve nem módosítható.'; end if;
  if exists(select 1 from public.webshop_variants v where v.attributes ? old_name
   and not (p_attribute->'values' ? (v.attributes->>old_name)))
   then raise exception 'Használatban lévő tulajdonságérték nem törölhető.'; end if;
  update public.webshop_attributes set "values"=p_attribute->'values',required=(p_attribute->>'required')::boolean where id=aid;
 else
  insert into public.webshop_attributes(name,"values",required)
   values(p_attribute->>'name',p_attribute->'values',(p_attribute->>'required')::boolean) returning id into aid;
 end if;
 return aid;
end; $$;

create or replace function public.pwa_withdraw_webshop_request(p_id uuid,p_courier text)
returns setof public.webshop_requests language plpgsql security invoker set search_path=public as $$
declare r public.webshop_requests;
begin
 select * into r from public.webshop_requests where id=p_id and courier_id=p_courier for update;
 if not found then raise exception 'Az igény nem található.'; end if;
 if r.status='withdrawn' then return next r; return; end if;
 if r.status<>'received' then raise exception 'Csak még fel nem dolgozott igény vonható vissza.'; end if;
 insert into public.webshop_request_events(request_id,status,actor) values(p_id,'withdrawn',r.courier_name);
 return query update public.webshop_requests set status='withdrawn',updated_at=now() where id=p_id returning *;
end; $$;

alter table public.webshop_products enable row level security;
alter table public.webshop_variants enable row level security;
alter table public.webshop_attributes enable row level security;
alter table public.webshop_requests enable row level security;
alter table public.webshop_request_items enable row level security;
alter table public.webshop_request_events enable row level security;
revoke all on public.webshop_products, public.webshop_variants, public.webshop_attributes, public.webshop_requests,
 public.webshop_request_items, public.webshop_request_events from anon, authenticated;
grant select,insert,update on public.webshop_products, public.webshop_variants, public.webshop_attributes, public.webshop_requests,
 public.webshop_request_items, public.webshop_request_events to service_role;
revoke all on function public.pwa_save_webshop_product(jsonb,jsonb), public.pwa_create_webshop_request(uuid,text,text,text,jsonb),
 public.pwa_manage_webshop_request(uuid,text,text,text) from public, anon, authenticated;
grant execute on function public.pwa_save_webshop_product(jsonb,jsonb), public.pwa_create_webshop_request(uuid,text,text,text,jsonb),
 public.pwa_manage_webshop_request(uuid,text,text,text) to service_role;
notify pgrst,'reload schema';
revoke all on function public.pwa_save_webshop_attribute(jsonb),public.pwa_withdraw_webshop_request(uuid,text) from public,anon,authenticated;
grant execute on function public.pwa_save_webshop_attribute(jsonb),public.pwa_withdraw_webshop_request(uuid,text) to service_role;
commit;
