-- Bring the schema in line with the group rules in docs/AGENTS.md.
--
-- A migration, not an edit to 001, so a teammate who has already applied 001
-- can run this on top. Safe to run twice: every statement is guarded.
--
-- What changes and why:
--
--   groups.status          proposed/active/completed/cancelled had no way to
--                          say "confirmed", so the fact that decides whether
--                          the meeting spot is visible was not stored at all.
--   group_members.response pending/joined/skipped was missing the expiry
--                          state the 10-minutes-before deadline needs.
--   buildings.code_secret  building QR codes are gone from the plan. This
--                          column is a not-null secret nothing reads.
--   student_spots          favourite spots, which docs/SIGNUP.md's
--                          POST /students body already documents and no table
--                          could hold.
--
-- Check-in is NOT a new column. group_members.arrived_at already exists and
-- is the timestamp a check-in writes. A member who has checked in is still a
-- joined member, so the API derives the checked_in state from arrived_at
-- rather than overwriting the fact that they joined.

begin;

-- ---------------------------------------------------------------- groups

alter table groups drop constraint if exists groups_status_check;

update groups set status = 'forming'   where status = 'proposed';
update groups set status = 'dissolved' where status = 'cancelled';

alter table groups
  add constraint groups_status_check
  check (status in ('forming', 'confirmed', 'active', 'completed', 'dissolved'));

alter table groups alter column status set default 'forming';

-- ------------------------------------------------------- group_members

alter table group_members drop constraint if exists group_members_response_check;

update group_members set response = 'invited'  where response = 'pending';
update group_members set response = 'declined' where response = 'skipped';

alter table group_members
  add constraint group_members_response_check
  check (response in ('invited', 'joined', 'declined', 'expired'));

alter table group_members alter column response set default 'invited';

-- ----------------------------------------------------------- buildings

-- The obsolete building-code column. Dropping it removes a stored secret
-- that no longer protects anything.
alter table buildings drop column if exists code_secret;

-- --------------------------------------------------------- favourite spots

-- Up to three per student, enforced in the API rather than here: a check
-- constraint cannot count sibling rows, and a trigger is more machinery than
-- a hackathon needs.
create table if not exists student_spots (
  student_id  uuid not null references students (id) on delete cascade,
  building_id smallint not null references buildings (id),
  rank        smallint not null default 1 check (rank between 1 and 3),
  primary key (student_id, building_id)
);

create index if not exists student_spots_student_idx on student_spots (student_id);

alter table student_spots enable row level security;

commit;
