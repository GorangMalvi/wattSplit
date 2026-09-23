-- wattSplit schema for Supabase Postgres.
-- Idempotent: safe to run more than once (python -m app.init_schema, or paste
-- into the Supabase SQL editor).

-- ---------------------------------------------------------------------------
-- Households (a flat) and who belongs to them
-- ---------------------------------------------------------------------------
create table if not exists public.households (
    id          uuid primary key default gen_random_uuid(),
    name        text not null check (length(trim(name)) > 0),
    invite_code text not null unique,
    created_by  uuid references auth.users (id) on delete set null,
    created_at  timestamptz not null default now()
);

create table if not exists public.household_members (
    household_id uuid not null references public.households (id) on delete cascade,
    user_id      uuid not null references auth.users (id) on delete cascade,
    role         text not null default 'member' check (role in ('owner', 'member')),
    joined_at    timestamptz not null default now(),
    primary key (household_id, user_id)
);

create index if not exists household_members_user_idx on public.household_members (user_id);

-- ---------------------------------------------------------------------------
-- Bill data, all scoped to a household
-- ---------------------------------------------------------------------------
create table if not exists public.roommates (
    id           bigint generated always as identity primary key,
    household_id uuid not null references public.households (id) on delete cascade,
    name         text not null check (length(trim(name)) > 0),
    join_date    text not null default '',
    leave_date   text not null default '',
    is_active    boolean not null default true,
    unique (household_id, name),
    unique (household_id, id)
);

-- The login (if any) that is this roommate: drives "My dashboard" and lets a
-- member edit their own readings and payments.
alter table public.roommates
    add column if not exists user_id uuid references auth.users (id) on delete set null;

create unique index if not exists roommates_household_user_idx
    on public.roommates (household_id, user_id) where user_id is not null;

create table if not exists public.months (
    household_id       uuid not null references public.households (id) on delete cascade,
    month              text not null check (month ~ '^\d{4}-\d{2}$'),
    main_start_reading double precision not null default 0,
    main_end_reading   double precision not null default 0,
    monthly_bill       double precision not null default 0,
    dg_bill            double precision not null default 0,
    notes              text not null default '',
    primary key (household_id, month)
);

-- Prepaid main meter money for the month (from the provider's Monthly
-- Consumption Report). monthly_bill = opening + recharge - closing: what the
-- meter actually deducted. Null when the month was entered by hand.
alter table public.months add column if not exists meter_opening_balance double precision;
alter table public.months add column if not exists meter_recharge        double precision;
alter table public.months add column if not exists meter_closing_balance double precision;

create table if not exists public.readings (
    household_id    uuid not null,
    month           text not null,
    roommate_id     bigint not null,
    current_reading double precision not null check (current_reading >= 0),
    primary key (household_id, month, roommate_id),
    foreign key (household_id, month) references public.months (household_id, month) on delete cascade,
    foreign key (household_id, roommate_id) references public.roommates (household_id, id) on delete cascade
);

-- start_reading: the sub-meter at the start of the month, for when there's no
-- reading last month to carry forward (e.g. a roommate's first month). With
-- it, a reading row may exist before the month-end reading is entered.
alter table public.readings add column if not exists start_reading double precision
    check (start_reading >= 0);
alter table public.readings alter column current_reading drop not null;

create table if not exists public.recharges (
    id           bigint generated always as identity primary key,
    household_id uuid not null,
    date         date not null,
    roommate_id  bigint not null,
    amount       double precision not null check (amount > 0),
    notes        text not null default '',
    foreign key (household_id, roommate_id) references public.roommates (household_id, id) on delete cascade
);

create index if not exists recharges_household_date_idx on public.recharges (household_id, date);

-- Which meter a payment is for: the main grid meter or the DG (generator).
-- Main payments settle a roommate's energy charge, DG payments their DG share.
alter table public.recharges
    add column if not exists meter text not null default 'main' check (meter in ('main', 'dg'));

-- Personal invites: the owner invites someone by email to be a given roommate.
-- The code goes out in a link (and can be typed into "Join with a code").
create table if not exists public.invites (
    id           bigint generated always as identity primary key,
    household_id uuid not null references public.households (id) on delete cascade,
    roommate_id  bigint not null,
    email        text not null,
    code         text not null unique,
    created_by   uuid references auth.users (id) on delete set null,
    created_at   timestamptz not null default now(),
    expires_at   timestamptz not null default now() + interval '14 days',
    accepted_by  uuid references auth.users (id) on delete set null,
    accepted_at  timestamptz,
    foreign key (household_id, roommate_id) references public.roommates (household_id, id) on delete cascade
);

create index if not exists invites_household_idx on public.invites (household_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- The FastAPI backend connects as the table owner and enforces the same rules
-- itself. RLS is still required because Supabase exposes the public schema
-- over its REST API to anyone holding the anon key.
--
-- Members read everything in their household. The owner changes anything;
-- other members change only readings and payments of their own roommate.
-- ---------------------------------------------------------------------------
create or replace function public.is_household_member(hid uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.household_members m
        where m.household_id = hid and m.user_id = auth.uid()
    );
$$;

create or replace function public.is_household_owner(hid uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.household_members m
        where m.household_id = hid and m.user_id = auth.uid() and m.role = 'owner'
    );
$$;

create or replace function public.is_own_roommate(hid uuid, rid bigint)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.roommates r
        where r.household_id = hid and r.id = rid and r.user_id = auth.uid()
    );
$$;

alter table public.households        enable row level security;
alter table public.household_members enable row level security;
alter table public.roommates         enable row level security;
alter table public.months            enable row level security;
alter table public.readings          enable row level security;
alter table public.recharges         enable row level security;
alter table public.invites           enable row level security;

-- Invite codes are secrets: only the owner can see them over the REST API,
-- and only the backend writes them.
drop policy if exists "owner reads invites" on public.invites;
create policy "owner reads invites" on public.invites
    for select to authenticated using (public.is_household_owner(household_id));

drop policy if exists "members read household" on public.households;
create policy "members read household" on public.households
    for select to authenticated using (public.is_household_member(id));

drop policy if exists "members read membership" on public.household_members;
create policy "members read membership" on public.household_members
    for select to authenticated using (public.is_household_member(household_id));

-- Earlier versions let every member write every table.
drop policy if exists "members manage roommates" on public.roommates;
drop policy if exists "members manage months" on public.months;
drop policy if exists "members manage readings" on public.readings;
drop policy if exists "members manage recharges" on public.recharges;

drop policy if exists "members read roommates" on public.roommates;
create policy "members read roommates" on public.roommates
    for select to authenticated using (public.is_household_member(household_id));

drop policy if exists "owner manages roommates" on public.roommates;
create policy "owner manages roommates" on public.roommates
    for all to authenticated
    using (public.is_household_owner(household_id))
    with check (public.is_household_owner(household_id));

drop policy if exists "members read months" on public.months;
create policy "members read months" on public.months
    for select to authenticated using (public.is_household_member(household_id));

drop policy if exists "owner manages months" on public.months;
create policy "owner manages months" on public.months
    for all to authenticated
    using (public.is_household_owner(household_id))
    with check (public.is_household_owner(household_id));

drop policy if exists "members read readings" on public.readings;
create policy "members read readings" on public.readings
    for select to authenticated using (public.is_household_member(household_id));

drop policy if exists "owner or self manages readings" on public.readings;
create policy "owner or self manages readings" on public.readings
    for all to authenticated
    using (public.is_household_owner(household_id) or public.is_own_roommate(household_id, roommate_id))
    with check (public.is_household_owner(household_id) or public.is_own_roommate(household_id, roommate_id));

drop policy if exists "members read recharges" on public.recharges;
create policy "members read recharges" on public.recharges
    for select to authenticated using (public.is_household_member(household_id));

drop policy if exists "owner or self manages recharges" on public.recharges;
create policy "owner or self manages recharges" on public.recharges
    for all to authenticated
    using (public.is_household_owner(household_id) or public.is_own_roommate(household_id, roommate_id))
    with check (public.is_household_owner(household_id) or public.is_own_roommate(household_id, roommate_id));
