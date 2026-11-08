-- Canonical Hangout schema for a completely fresh Supabase project.
--
-- Lifecycle V2 is the only supported model. Browser roles receive no table
-- policies, so row-level security denies direct access by default. Privileged
-- writes and reads use the backend-only service-role key.

begin;

create extension if not exists pgcrypto;

create table tags (
  id          smallserial primary key,
  slug        text not null unique,
  label       text not null,
  category    text not null default 'other'
              check (category in ('student_type', 'interest', 'other'))
);

create table languages (
  code        text primary key,
  name        text not null
);

create table courses (
  id          serial primary key,
  code        text not null unique,
  title       text
);

create table buildings (
  id          smallserial primary key,
  slug        text not null unique,
  name        text not null,
  lat         double precision not null,
  lng         double precision not null,
  is_indoor   boolean not null default true,
  code_secret text not null
);

create table students (
  id             uuid primary key default gen_random_uuid(),
  auth_sub       text unique,
  is_guest       boolean not null default false,
  is_seed        boolean not null default false,
  first_name     text not null check (char_length(first_name) between 1 and 40),
  ask_me_about   text check (char_length(ask_me_about) <= 120),
  visibility     text not null default 'everyone'
                 check (visibility in ('everyone', 'my_courses', 'shared_tag')),
  paused         boolean not null default false,
  open_until     timestamptz,
  created_at     timestamptz not null default now(),
  last_active_at timestamptz not null default now(),
  deleted_at     timestamptz
);

create index students_open_idx
  on students (open_until)
  where open_until is not null;

create table student_tags (
  student_id  uuid not null references students (id) on delete cascade,
  tag_id      smallint not null references tags (id),
  primary key (student_id, tag_id)
);

create table student_languages (
  student_id    uuid not null references students (id) on delete cascade,
  language_code text not null references languages (code),
  primary key (student_id, language_code)
);

create table student_courses (
  student_id  uuid not null references students (id) on delete cascade,
  course_id   int not null references courses (id),
  term        text not null,
  primary key (student_id, course_id, term)
);

create table free_blocks (
  id          bigserial primary key,
  student_id  uuid not null references students (id) on delete cascade,
  day         smallint not null check (day between 0 and 6),
  start_time  time not null,
  end_time    time not null,
  check (end_time > start_time)
);

create index free_blocks_slot_idx on free_blocks (day, start_time, end_time);
create index free_blocks_student_idx on free_blocks (student_id);

create table student_contacts (
  student_id  uuid not null references students (id) on delete cascade,
  platform    text not null
              check (platform in ('instagram', 'phone', 'discord', 'email', 'other')),
  handle      text not null check (char_length(handle) <= 80),
  primary key (student_id, platform)
);

create table blocks (
  blocker_id  uuid not null references students (id) on delete cascade,
  blocked_id  uuid not null references students (id) on delete cascade,
  created_at  timestamptz not null default now(),
  primary key (blocker_id, blocked_id),
  check (blocker_id <> blocked_id)
);

create table groups (
  id                 uuid primary key default gen_random_uuid(),
  on_date            date not null,
  start_time         time not null,
  end_time           time not null,
  building_id        smallint references buildings (id),
  mode               text not null default 'social'
                     check (mode in ('social', 'study')),
  status             text not null default 'forming'
                     check (status in (
                       'forming', 'confirmed', 'active', 'completed', 'dissolved'
                     )),
  invite_expires_at  timestamptz not null,
  confirmed_at       timestamptz,
  status_changed_at  timestamptz not null default now(),
  created_at         timestamptz not null default now(),
  check (end_time > start_time),
  constraint groups_confirmed_timestamp_check
    check (status <> 'confirmed' or confirmed_at is not null),
  constraint groups_invite_deadline_check
    check (
      invite_expires_at <=
        timezone('America/Vancouver', on_date + start_time)
    )
);

create index groups_date_idx on groups (on_date, start_time);

create table reports (
  id           bigserial primary key,
  reporter_id  uuid not null references students (id) on delete cascade,
  reported_id  uuid not null references students (id) on delete cascade,
  group_id     uuid,
  reason       text not null check (char_length(reason) <= 500),
  status       text not null default 'open'
               check (status in ('open', 'reviewed', 'actioned', 'dismissed')),
  created_at   timestamptz not null default now(),
  constraint reports_group_fk
    foreign key (group_id) references groups (id) on delete set null
);

create table group_members (
  group_id           uuid not null references groups (id) on delete cascade,
  student_id         uuid not null references students (id) on delete cascade,
  invitation_status  text not null default 'invited'
                     check (invitation_status in (
                       'invited', 'accepted', 'declined', 'expired'
                     )),
  arrived_at         timestamptz,
  went               boolean,
  primary key (group_id, student_id),
  constraint group_members_arrival_requires_acceptance_check
    check (arrived_at is null or invitation_status = 'accepted')
);

create index group_members_student_idx on group_members (student_id);
create index group_members_active_invitation_idx
  on group_members (student_id, invitation_status)
  where invitation_status in ('invited', 'accepted');

create table contact_shares (
  group_id    uuid not null references groups (id) on delete cascade,
  student_id  uuid not null,
  platform    text not null,
  shared_at   timestamptz not null default now(),
  primary key (group_id, student_id, platform),
  foreign key (student_id, platform)
    references student_contacts (student_id, platform) on delete cascade,
  foreign key (group_id, student_id)
    references group_members (group_id, student_id) on delete cascade
);

alter table tags enable row level security;
alter table languages enable row level security;
alter table courses enable row level security;
alter table buildings enable row level security;
alter table students enable row level security;
alter table student_tags enable row level security;
alter table student_languages enable row level security;
alter table student_courses enable row level security;
alter table free_blocks enable row level security;
alter table student_contacts enable row level security;
alter table blocks enable row level security;
alter table reports enable row level security;
alter table groups enable row level security;
alter table group_members enable row level security;
alter table contact_shares enable row level security;

-- No anon or authenticated policies are created. RLS therefore denies direct
-- browser access to every table; the backend service role bypasses RLS.

-- Locking the group before its membership serializes concurrent responses. The
-- third acceptance confirms the group in the same transaction.
create or replace function respond_to_group_invitation(
  p_group_id uuid,
  p_student_id uuid,
  p_response text
)
returns table (
  group_id uuid,
  student_id uuid,
  invitation_status text,
  group_status text,
  accepted_count bigint,
  invite_expires_at timestamptz
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  matched_group groups%rowtype;
  membership group_members%rowtype;
  accepted_total bigint;
begin
  if p_response not in ('accepted', 'declined') then
    raise exception 'Invitation response must be accepted or declined'
      using errcode = '22023';
  end if;

  select matched.*
  into matched_group
  from groups as matched
  where matched.id = p_group_id
  for update;

  if not found then
    raise exception 'Group invitation was not found'
      using errcode = 'P0002';
  end if;

  select member.*
  into membership
  from group_members as member
  where member.group_id = p_group_id
    and member.student_id = p_student_id
  for update;

  if not found then
    raise exception 'No membership exists for the current student and group'
      using errcode = 'P0002';
  end if;

  -- A retry of an already committed response is safe even if the group has
  -- since advanced or its deadline has passed.
  if membership.invitation_status = p_response then
    select count(*)
    into accepted_total
    from group_members as member
    where member.group_id = p_group_id
      and member.invitation_status = 'accepted';

    return query
      select matched_group.id,
             membership.student_id,
             membership.invitation_status,
             matched_group.status,
             accepted_total,
             matched_group.invite_expires_at;
    return;
  end if;

  if matched_group.status not in ('forming', 'confirmed') then
    raise exception 'Invitations cannot change while the group is %', matched_group.status
      using errcode = 'P0001';
  end if;

  if now() >= matched_group.invite_expires_at then
    raise exception 'The invitation deadline has passed'
      using errcode = 'P0001';
  end if;

  if membership.invitation_status <> 'invited' then
    raise exception 'Cannot change an % invitation to %',
      membership.invitation_status, p_response
      using errcode = 'P0001';
  end if;

  update group_members as member
  set invitation_status = p_response
  where member.group_id = p_group_id
    and member.student_id = p_student_id
  returning member.* into membership;

  select count(*)
  into accepted_total
  from group_members as member
  where member.group_id = p_group_id
    and member.invitation_status = 'accepted';

  if matched_group.status = 'forming' and accepted_total >= 3 then
    update groups as matched
    set status = 'confirmed',
        confirmed_at = coalesce(matched.confirmed_at, now()),
        status_changed_at = now()
    where matched.id = p_group_id
    returning matched.* into matched_group;
  end if;

  return query
    select matched_group.id,
           membership.student_id,
           membership.invitation_status,
           matched_group.status,
           accepted_total,
           matched_group.invite_expires_at;
end;
$$;

revoke all on function respond_to_group_invitation(uuid, uuid, text) from public;
revoke all on function respond_to_group_invitation(uuid, uuid, text) from anon;
revoke all on function respond_to_group_invitation(uuid, uuid, text) from authenticated;
grant execute on function respond_to_group_invitation(uuid, uuid, text) to service_role;

comment on column groups.invite_expires_at is
  'Absolute invitation deadline; new acceptances are rejected at or after this time.';
comment on column groups.confirmed_at is
  'Time the group first reached three accepted invitations.';
comment on column groups.status_changed_at is
  'Time of the most recent lifecycle transition; mutation code must update this field.';
comment on column group_members.invitation_status is
  'Invitation response only; attendance remains in arrived_at and later check-in records.';
comment on column group_members.arrived_at is
  'Attendance timestamp, independent from invitation_status. QR check-in is not yet implemented.';

commit;
