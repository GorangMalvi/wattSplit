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

create table if not exists public.readings (
    household_id    uuid not null,
    month           text not null,
    roommate_id     bigint not null,
    current_reading double precision not null check (current_reading >= 0),
    primary key (household_id, month, roommate_id),
    foreign key (household_id, month) references public.months (household_id, month) on delete cascade,
    foreign key (household_id, roommate_id) references public.roommates (household_id, id) on delete cascade
);

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

-- ---------------------------------------------------------------------------
-- Row Level Security
--
-- The FastAPI backend connects as the table owner and enforces household
-- membership itself. RLS is still required because Supabase exposes the
-- public schema over its REST API to anyone holding the anon key.
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

alter table public.households        enable row level security;
alter table public.household_members enable row level security;
alter table public.roommates         enable row level security;
alter table public.months            enable row level security;
alter table public.readings          enable row level security;
alter table public.recharges         enable row level security;

drop policy if exists "members read household" on public.households;
create policy "members read household" on public.households
    for select to authenticated using (public.is_household_member(id));

drop policy if exists "members read membership" on public.household_members;
create policy "members read membership" on public.household_members
    for select to authenticated using (public.is_household_member(household_id));

drop policy if exists "members manage roommates" on public.roommates;
create policy "members manage roommates" on public.roommates
    for all to authenticated
    using (public.is_household_member(household_id))
    with check (public.is_household_member(household_id));

drop policy if exists "members manage months" on public.months;
create policy "members manage months" on public.months
    for all to authenticated
    using (public.is_household_member(household_id))
    with check (public.is_household_member(household_id));

drop policy if exists "members manage readings" on public.readings;
create policy "members manage readings" on public.readings
    for all to authenticated
    using (public.is_household_member(household_id))
    with check (public.is_household_member(household_id));

drop policy if exists "members manage recharges" on public.recharges;
create policy "members manage recharges" on public.recharges
    for all to authenticated
    using (public.is_household_member(household_id))
    with check (public.is_household_member(household_id));
