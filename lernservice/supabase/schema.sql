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

create table if not exists public.orders (
  id                bigint generated always as identity (start with 1001) primary key,
  user_id           uuid not null default auth.uid() references public.profiles(id) on delete cascade,
  kind              text not null check (kind in ('bild', 'text')),
  product           text not null check (product in ('powerpoint','lernzettel','zusammenfassung','karteikarten','mindmap','uebungsfragen','text','handout')),
  subject           text check (char_length(subject) <= 60),
  grade             text check (char_length(grade) <= 30),
  wish              text check (char_length(wish) <= 5000),
  text_content      text check (char_length(text_content) <= 100000),
  due_date          date,
  status            text not null default 'unbezahlt' check (status in ('unbezahlt','neu','in_arbeit','fertig','archiv')),
  price_cents       integer not null default 799,
  paid_at           timestamptz,
  stripe_session_id text,
  draft_message     text,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now()
);
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
begin
  insert into public.profiles (id, name, email)
  values (new.id, left(coalesce(new.raw_user_meta_data->>'name', ''), 100), coalesce(new.email, ''))
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

-- Schüler dürfen Status/Preis nicht selbst setzen
create or replace function public.orders_guard() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if tg_op = 'INSERT' and not public.is_admin() then
    new.user_id := auth.uid();
    new.status := 'unbezahlt';
    new.price_cents := 799;
    new.paid_at := null;
    new.stripe_session_id := null;
    new.draft_message := null;
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
--  FERTIG. Danach (Schritt 2 in der Anleitung): auf deiner Website
--  registrieren und dich mit dieser Zeile zum Admin machen:
--
--    update public.profiles set is_admin = true where email = 'deine@email.de';
-- ════════════════════════════════════════════════════════════════════
