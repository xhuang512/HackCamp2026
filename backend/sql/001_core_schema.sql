-- Core Hangout schema supplied for Issue #7 (sections 1-3 only).
-- All browser access is denied by default: RLS is enabled and this migration
-- intentionally creates no anon/authenticated policies. Backend writes use the
-- service-role key, which must never be exposed to the frontend.

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

create index students_open_idx on students (open_until) where open_until is not null;

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

create table reports (
  id           bigserial primary key,
  reporter_id  uuid not null references students (id) on delete cascade,
  reported_id  uuid not null references students (id) on delete cascade,
  group_id     uuid,
  reason       text not null check (char_length(reason) <= 500),
  status       text not null default 'open'
               check (status in ('open', 'reviewed', 'actioned', 'dismissed')),
  created_at   timestamptz not null default now()
);

create table groups (
  id           uuid primary key default gen_random_uuid(),
  on_date      date not null,
  start_time   time not null,
  end_time     time not null,
  building_id  smallint references buildings (id),
  mode         text not null default 'social' check (mode in ('social', 'study')),
  status       text not null default 'proposed'
               check (status in ('proposed', 'active', 'completed', 'cancelled')),
  created_at   timestamptz not null default now(),
  check (end_time > start_time)
);

create index groups_date_idx on groups (on_date, start_time);

alter table reports
  add constraint reports_group_fk foreign key (group_id) references groups (id) on delete set null;

create table group_members (
  group_id    uuid not null references groups (id) on delete cascade,
  student_id  uuid not null references students (id) on delete cascade,
  response    text not null default 'pending'
              check (response in ('pending', 'joined', 'skipped')),
  arrived_at  timestamptz,
  went        boolean,
  primary key (group_id, student_id)
);

create index group_members_student_idx on group_members (student_id);

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
