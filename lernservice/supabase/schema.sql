-- ════════════════════════════════════════════════════════════════════
--  Datenbank einrichten
--  Supabase → SQL Editor → "New query" → ALLES einfügen → "Run"
--  Du kannst das Skript gefahrlos mehrmals ausführen.
-- ════════════════════════════════════════════════════════════════════

-- ── Tabellen ─────────────────────────────────────────────────────────
create table if not exists public.profiles (
  id          uuid primary key references auth.users(id) on delete cascade,
  name        text not null default '',
  email       text not null default '',
  is_admin    boolean not null default false,
  created_at  timestamptz not null default now()
);
-- Empfehlungsprogramm: eigener Code + wer hat mich geworben
alter table public.profiles add column if not exists ref_code text unique;
alter table public.profiles add column if not exists referred_by uuid references public.profiles(id) on delete set null;

create table if not exists public.orders (
  id                bigint generated always as identity (start with 1001) primary key,
  user_id           uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  kind              text not null check (kind in ('bild', 'text')),
  product           text not null check (product in ('powerpoint','lernzettel','zusammenfassung','karteikarten','mindmap','uebungsfragen','text','handout','paket_referat','paket_pruefung','paket_verstehen','paket_lektuere')),
  subject           text check (char_length(subject) <= 60),
  grade             text check (char_length(grade) <= 30),
  wish              text check (char_length(wish) <= 5000),
  text_content      text check (char_length(text_content) <= 100000),
  due_date          date,
  status            text not null default 'unbezahlt' check (status in ('unbezahlt','neu','in_arbeit','fertig','archiv')),
  price_cents       integer not null default 499,
  paid_at           timestamptz,
  stripe_session_id text,
  draft_message     text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
-- Produktliste aktualisieren (Einzel-Leistungen + Kombi-Pakete)
alter table public.orders drop constraint if exists orders_product_check;
alter table public.orders add constraint orders_product_check check (product in ('powerpoint','lernzettel','zusammenfassung','karteikarten','mindmap','uebungsfragen','text','handout','paket_referat','paket_pruefung','paket_verstehen','paket_lektuere'));
alter table public.orders alter column price_cents set default 499;
alter table public.orders add column if not exists paid_via text check (paid_via in ('stripe', 'guthaben', 'manuell'));
create index if not exists orders_user_idx   on public.orders (user_id);
create index if not exists orders_status_idx on public.orders (status);

create table if not exists public.messages (
  id          bigint generated always as identity primary key,
  order_id    bigint not null references public.orders(id) on delete cascade,
  from_admin  boolean not null default false,
  body        text not null default '' check (char_length(body) <= 10000),
  created_at  timestamptz not null default now(),
  read_at     timestamptz
);
create index if not exists messages_order_idx on public.messages (order_id);

create table if not exists public.order_files (
  id          bigint generated always as identity primary key,
  order_id    bigint not null references public.orders(id) on delete cascade,
  message_id  bigint references public.messages(id) on delete set null,
  path        text not null unique,
  name        text not null check (char_length(name) <= 255),
  mime        text not null default '',
  size        bigint not null default 0,
  from_admin  boolean not null default false,
  created_at  timestamptz not null default now()
);
create index if not exists files_order_idx on public.order_files (order_id);

-- ── Hilfsfunktionen ─────────────────────────────────────────────────
create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = public as $$
  select coalesce((select is_admin from public.profiles where id = auth.uid()), false);
$$;

-- Profil automatisch anlegen, wenn sich jemand registriert
create or replace function public.handle_new_user() returns trigger
language plpgsql security definer set search_path = public as $$
declare ref uuid;
begin
  -- Empfehlungscode aus dem Link (?ref=CODE) wird bei der Registrierung mitgeschickt
  select id into ref from public.profiles
   where ref_code = upper(trim(coalesce(new.raw_user_meta_data->>'ref', '')));
  insert into public.profiles (id, name, email, ref_code, referred_by)
  values (new.id, left(coalesce(new.raw_user_meta_data->>'name', ''), 100), coalesce(new.email, ''), public.new_ref_code(), ref)
  on conflict (id) do nothing;
  return new;
end $$;
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function public.handle_new_user();
-- Profile für bereits vorhandene Konten nachtragen
insert into public.profiles (id, name, email)
  select id, left(coalesce(raw_user_meta_data->>'name', ''), 100), coalesce(email, '') from auth.users
  on conflict (id) do nothing;

-- ── PREISE ── Einzel-Leistung 4,99 €, Kombi-Paket (paket_…) 12,99 €
-- Hier ändern, wenn du die Preise anpasst (und die Stripe-Links + config.js auch).
create or replace function public.product_price_cents(p text) returns integer
language sql immutable as $$
  select case when p like 'paket\_%' then 1299 else 499 end;
$$;

-- Schüler dürfen Status/Preis nicht selbst setzen
create or replace function public.orders_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'INSERT' and not public.is_admin() then
    new.user_id := auth.uid();
    new.status := 'unbezahlt';
    new.price_cents := public.product_price_cents(new.product);
    new.paid_at := null;
    new.stripe_session_id := null;
    new.draft_message := null;
    new.paid_via := null;
    new.created_at := now();
  end if;
  new.updated_at := now();
  return new;
end $$;
drop trigger if exists orders_guard on public.orders;
create trigger orders_guard before insert or update on public.orders
  for each row execute function public.orders_guard();

-- Absender von Nachrichten/Dateien wird vom Server festgelegt, nicht vom Browser
create or replace function public.sender_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  new.from_admin := public.is_admin();
  new.created_at := now();
  if tg_table_name = 'messages' then
    new.read_at := null;
  elsif new.message_id is not null and not exists (
    select 1 from public.messages m where m.id = new.message_id and m.order_id = new.order_id
  ) then
    raise exception 'Nachricht gehört nicht zu diesem Auftrag';
  end if;
  return new;
end $$;
drop trigger if exists messages_guard on public.messages;
create trigger messages_guard before insert on public.messages
  for each row execute function public.sender_guard();
drop trigger if exists files_guard on public.order_files;
create trigger files_guard before insert on public.order_files
  for each row execute function public.sender_guard();

-- Nachrichten als gelesen markieren (jeweils die der Gegenseite)
create or replace function public.mark_read(p_order bigint) returns void
language plpgsql security definer set search_path = public as $$
declare adm boolean := public.is_admin();
begin
  if not adm and not exists (select 1 from public.orders where id = p_order and user_id = auth.uid()) then
    return;
  end if;
  update public.messages set read_at = now()
   where order_id = p_order and read_at is null and from_admin = (not adm);
end $$;

-- ── Rechte ──────────────────────────────────────────────────────────
revoke all on public.profiles, public.orders, public.messages, public.order_files from anon;
grant select on public.profiles to authenticated;
revoke update on public.profiles from authenticated;
grant update (name) on public.profiles to authenticated;         -- nur den Namen, nie is_admin
grant select, insert, update, delete on public.orders, public.messages, public.order_files to authenticated;
revoke execute on function public.mark_read(bigint) from public, anon;
grant execute on function public.mark_read(bigint) to authenticated;

alter table public.profiles    enable row level security;
alter table public.orders      enable row level security;
alter table public.messages    enable row level security;
alter table public.order_files enable row level security;

drop policy if exists "profil lesen" on public.profiles;
create policy "profil lesen" on public.profiles for select to authenticated
  using (id = auth.uid() or public.is_admin());
drop policy if exists "profil aendern" on public.profiles;
create policy "profil aendern" on public.profiles for update to authenticated
  using (id = auth.uid()) with check (id = auth.uid());

drop policy if exists "auftraege lesen" on public.orders;
create policy "auftraege lesen" on public.orders for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
drop policy if exists "auftraege anlegen" on public.orders;
create policy "auftraege anlegen" on public.orders for insert to authenticated
  with check (user_id = auth.uid());
drop policy if exists "auftraege admin aendern" on public.orders;
create policy "auftraege admin aendern" on public.orders for update to authenticated
  using (public.is_admin()) with check (public.is_admin());
drop policy if exists "auftraege admin loeschen" on public.orders;
create policy "auftraege admin loeschen" on public.orders for delete to authenticated
  using (public.is_admin());

drop policy if exists "nachrichten lesen" on public.messages;
create policy "nachrichten lesen" on public.messages for select to authenticated
  using (public.is_admin() or exists (select 1 from public.orders o where o.id = order_id and o.user_id = auth.uid()));
drop policy if exists "nachrichten schreiben" on public.messages;
create policy "nachrichten schreiben" on public.messages for insert to authenticated
  with check (public.is_admin() or exists (select 1 from public.orders o where o.id = order_id and o.user_id = auth.uid() and o.status <> 'unbezahlt'));
drop policy if exists "nachrichten admin" on public.messages;
create policy "nachrichten admin" on public.messages for delete to authenticated
  using (public.is_admin());

drop policy if exists "dateien lesen" on public.order_files;
create policy "dateien lesen" on public.order_files for select to authenticated
  using (public.is_admin() or exists (select 1 from public.orders o where o.id = order_id and o.user_id = auth.uid()));
drop policy if exists "dateien anlegen" on public.order_files;
create policy "dateien anlegen" on public.order_files for insert to authenticated
  with check (public.is_admin() or (
    exists (select 1 from public.orders o where o.id = order_id and o.user_id = auth.uid())
    and path like auth.uid()::text || '/' || order_id::text || '/%'
  ));
drop policy if exists "dateien admin loeschen" on public.order_files;
create policy "dateien admin loeschen" on public.order_files for delete to authenticated
  using (public.is_admin());

-- ── Dateispeicher (privat, max. 25 MB pro Datei) ─────────────────────
insert into storage.buckets (id, name, public, file_size_limit)
values ('dateien', 'dateien', false, 26214400)
on conflict (id) do update set public = false, file_size_limit = 26214400;

drop policy if exists "dateien speicher lesen" on storage.objects;
create policy "dateien speicher lesen" on storage.objects for select to authenticated
  using (bucket_id = 'dateien' and ((storage.foldername(name))[1] = auth.uid()::text or public.is_admin()));
drop policy if exists "dateien speicher hochladen" on storage.objects;
create policy "dateien speicher hochladen" on storage.objects for insert to authenticated
  with check (bucket_id = 'dateien' and ((storage.foldername(name))[1] = auth.uid()::text or public.is_admin()));
drop policy if exists "dateien speicher loeschen" on storage.objects;
create policy "dateien speicher loeschen" on storage.objects for delete to authenticated
  using (bucket_id = 'dateien' and public.is_admin());

-- ════════════════════════════════════════════════════════════════════
--  EMPFEHLUNGSPROGRAMM
--  Wer einen Freund wirbt, bekommt Guthaben, sobald der Freund seinen
--  ERSTEN Auftrag bezahlt. Betrag + Mindest-Auszahlung hier ändern:
-- ════════════════════════════════════════════════════════════════════
create or replace function public.referral_bonus_cents() returns integer
language sql immutable as $$ select 299 $$;     -- 2,99 € pro geworbenem Freund
create or replace function public.min_payout_cents() returns integer
language sql immutable as $$ select 1000 $$;    -- Auszahlung ab 10,00 €

-- Zufälliger 6-stelliger Code ohne verwechselbare Zeichen (kein 0/O, 1/I)
create or replace function public.new_ref_code() returns text
language plpgsql volatile set search_path = public as $$
declare c text; chars text := 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
begin
  loop
    c := '';
    for i in 1..6 loop c := c || substr(chars, 1 + floor(random() * length(chars))::int, 1); end loop;
    exit when not exists (select 1 from public.profiles where ref_code = c);
  end loop;
  return c;
end $$;
update public.profiles set ref_code = public.new_ref_code() where ref_code is null;

create table if not exists public.payouts (
  id            bigint generated always as identity primary key,
  user_id       uuid not null references public.profiles(id) on delete cascade,
  amount_cents  integer not null check (amount_cents > 0),
  method        text not null check (method in ('paypal', 'ueberweisung')),
  details       text not null check (char_length(details) between 3 and 200),
  status        text not null default 'offen' check (status in ('offen', 'ausgezahlt', 'abgelehnt')),
  created_at    timestamptz not null default now(),
  done_at       timestamptz
);

-- Guthaben-Konto: jede Buchung eine Zeile, Kontostand = Summe
create table if not exists public.credits (
  id              bigint generated always as identity primary key,
  user_id         uuid not null references public.profiles(id) on delete cascade,
  amount_cents    integer not null,
  kind            text not null check (kind in ('empfehlung', 'bezahlung', 'auszahlung', 'korrektur')),
  source_user_id  uuid references public.profiles(id) on delete set null,   -- der geworbene Freund
  order_id        bigint references public.orders(id) on delete set null,
  payout_id       bigint references public.payouts(id) on delete set null,
  reverses_id     bigint unique references public.credits(id) on delete set null,
  note            text,
  created_at      timestamptz not null default now()
);
create index if not exists credits_user_idx on public.credits (user_id);
-- pro geworbenem Freund höchstens EIN Bonus
create unique index if not exists credits_one_bonus_per_friend on public.credits (source_user_id) where kind = 'empfehlung';

create or replace function public.credit_balance(p_user uuid) returns integer
language sql stable security definer set search_path = public as $$
  select coalesce(sum(amount_cents), 0)::int from public.credits where user_id = p_user;
$$;

-- Bonus automatisch gutschreiben, wenn ein geworbener Freund bezahlt (nicht bei Zahlung mit Guthaben)
create or replace function public.orders_referral_bonus() returns trigger
language plpgsql security definer set search_path = public as $$
declare ref uuid;
begin
  if old.status = 'unbezahlt' and new.status <> 'unbezahlt' and coalesce(new.paid_via, '') <> 'guthaben' then
    select referred_by into ref from public.profiles where id = new.user_id;
    if ref is not null and ref <> new.user_id then
      insert into public.credits (user_id, amount_cents, kind, source_user_id, order_id, note)
      values (ref, public.referral_bonus_cents(), 'empfehlung', new.user_id, new.id, 'Empfehlung')
      on conflict do nothing;
    end if;
  end if;
  return null;
end $$;
drop trigger if exists orders_referral on public.orders;
create trigger orders_referral after update of status on public.orders
  for each row execute function public.orders_referral_bonus();

-- Übersicht für den Schüler
create or replace function public.my_referral_info() returns json
language sql stable security definer set search_path = public as $$
  select json_build_object(
    'code', p.ref_code,
    'has_referrer', p.referred_by is not null,
    'can_set_referrer', p.referred_by is null and not exists (select 1 from public.orders o where o.user_id = p.id and o.status <> 'unbezahlt'),
    'balance_cents', public.credit_balance(p.id),
    'invited', (select count(*) from public.profiles f where f.referred_by = p.id),
    'bought', (select count(*) from public.credits c where c.user_id = p.id and c.kind = 'empfehlung'),
    'earned_cents', (select coalesce(sum(amount_cents), 0) from public.credits c where c.user_id = p.id and c.kind = 'empfehlung'),
    'bonus_cents', public.referral_bonus_cents(),
    'min_payout_cents', public.min_payout_cents()
  ) from public.profiles p where p.id = auth.uid();
$$;

-- Code nachträglich eintragen (nur vor dem ersten bezahlten Auftrag)
create or replace function public.set_referrer(p_code text) returns void
language plpgsql security definer set search_path = public as $$
declare ref uuid; ref_of_ref uuid;
begin
  if auth.uid() is null then raise exception 'Bitte melde dich an.'; end if;
  select id, referred_by into ref, ref_of_ref from public.profiles where ref_code = upper(trim(p_code));
  if ref is null then raise exception 'Diesen Empfehlungscode gibt es nicht.'; end if;
  if ref = auth.uid() then raise exception 'Du kannst dich nicht selbst empfehlen.'; end if;
  if ref_of_ref = auth.uid() then raise exception 'Ihr könnt euch nicht gegenseitig empfehlen.'; end if;
  if exists (select 1 from public.orders where user_id = auth.uid() and status <> 'unbezahlt') then
    raise exception 'Ein Code kann nur vor dem ersten Kauf eingetragen werden.';
  end if;
  update public.profiles set referred_by = ref where id = auth.uid() and referred_by is null;
  if not found then raise exception 'Du hast schon einen Empfehlungscode eingetragen.'; end if;
end $$;

-- Auftrag mit Guthaben bezahlen
create or replace function public.pay_with_credit(p_order bigint) returns void
language plpgsql security definer set search_path = public as $$
declare o public.orders;
begin
  if auth.uid() is null then raise exception 'Bitte melde dich an.'; end if;
  perform pg_advisory_xact_lock(hashtext(auth.uid()::text));
  select * into o from public.orders where id = p_order and user_id = auth.uid() for update;
  if not found then raise exception 'Auftrag nicht gefunden.'; end if;
  if o.status <> 'unbezahlt' then raise exception 'Dieser Auftrag ist schon bezahlt.'; end if;
  if public.credit_balance(auth.uid()) < o.price_cents then raise exception 'Nicht genug Guthaben.'; end if;
  insert into public.credits (user_id, amount_cents, kind, order_id, note)
  values (auth.uid(), -o.price_cents, 'bezahlung', o.id, 'Auftrag mit Guthaben bezahlt');
  update public.orders set status = 'neu', paid_at = now(), paid_via = 'guthaben' where id = o.id;
end $$;

-- Auszahlung anfordern (ganzes Guthaben)
create or replace function public.request_payout(p_method text, p_details text) returns void
language plpgsql security definer set search_path = public as $$
declare bal int; pid bigint;
begin
  if auth.uid() is null then raise exception 'Bitte melde dich an.'; end if;
  perform pg_advisory_xact_lock(hashtext(auth.uid()::text));
  bal := public.credit_balance(auth.uid());
  if bal < public.min_payout_cents() then raise exception 'Auszahlung ist erst ab dem Mindestbetrag möglich.'; end if;
  insert into public.payouts (user_id, amount_cents, method, details)
  values (auth.uid(), bal, p_method, trim(p_details)) returning id into pid;
  insert into public.credits (user_id, amount_cents, kind, payout_id, note)
  values (auth.uid(), -bal, 'auszahlung', pid, 'Auszahlung angefordert');
end $$;

-- Admin: Auszahlung erledigt / abgelehnt (abgelehnt = Guthaben zurück)
create or replace function public.admin_finish_payout(p_id bigint, p_paid boolean) returns void
language plpgsql security definer set search_path = public as $$
declare pay public.payouts;
begin
  if not public.is_admin() then raise exception 'Dafür fehlt dir die Berechtigung.'; end if;
  select * into pay from public.payouts where id = p_id for update;
  if not found or pay.status <> 'offen' then raise exception 'Diese Auszahlung ist schon erledigt.'; end if;
  update public.payouts set status = case when p_paid then 'ausgezahlt' else 'abgelehnt' end, done_at = now() where id = p_id;
  if not p_paid then
    insert into public.credits (user_id, amount_cents, kind, payout_id, note)
    values (pay.user_id, pay.amount_cents, 'korrektur', p_id, 'Auszahlung abgelehnt – Guthaben zurückgebucht');
  end if;
end $$;

-- Admin: Empfehlungs-Bonus stornieren (z. B. nach Rückerstattung)
create or replace function public.admin_reverse_credit(p_id bigint) returns void
language plpgsql security definer set search_path = public as $$
declare c public.credits;
begin
  if not public.is_admin() then raise exception 'Dafür fehlt dir die Berechtigung.'; end if;
  select * into c from public.credits where id = p_id;
  if not found or c.kind <> 'empfehlung' then raise exception 'Nur Empfehlungs-Gutschriften können storniert werden.'; end if;
  insert into public.credits (user_id, amount_cents, kind, reverses_id, note)
  values (c.user_id, -c.amount_cents, 'korrektur', c.id, 'Empfehlungs-Bonus storniert')
  on conflict (reverses_id) do nothing;
end $$;

-- Rechte Empfehlungsprogramm
revoke all on public.credits, public.payouts from anon, authenticated;
grant select on public.credits, public.payouts to authenticated;
alter table public.credits enable row level security;
alter table public.payouts enable row level security;
drop policy if exists "guthaben lesen" on public.credits;
create policy "guthaben lesen" on public.credits for select to authenticated
  using (user_id = auth.uid() or public.is_admin());
drop policy if exists "auszahlungen lesen" on public.payouts;
create policy "auszahlungen lesen" on public.payouts for select to authenticated
  using (user_id = auth.uid() or public.is_admin());

revoke execute on function public.credit_balance(uuid), public.new_ref_code() from public, anon, authenticated;
revoke execute on function public.my_referral_info(), public.set_referrer(text), public.pay_with_credit(bigint),
  public.request_payout(text, text), public.admin_finish_payout(bigint, boolean), public.admin_reverse_credit(bigint) from public, anon;
grant execute on function public.my_referral_info(), public.set_referrer(text), public.pay_with_credit(bigint),
  public.request_payout(text, text), public.admin_finish_payout(bigint, boolean), public.admin_reverse_credit(bigint) to authenticated;

-- ════════════════════════════════════════════════════════════════════
--  FERTIG. Danach (Schritt 2 in der Anleitung): auf deiner Website
--  registrieren und dich mit dieser Zeile zum Admin machen:
--
--    update public.profiles set is_admin = true where email = 'deine@email.de';
-- ════════════════════════════════════════════════════════════════════
