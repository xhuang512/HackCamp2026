-- Group lifecycle V2 migration and atomic invitation-response RPC.
--
-- This migration is intentionally not executed by the application. Apply it in
-- a coordinated deployment before starting the V2-only backend. The application
-- does not support the V1 response column or legacy group statuses after this
-- migration is introduced.
--
-- Existing value mapping:
--   groups.proposed  -> forming, confirmed, active, completed, or dissolved
--                       according to accepted count and meeting time
--   groups.active    -> active, or completed when its meeting has ended
--   groups.completed -> completed
--   groups.cancelled -> dissolved
--   group_members.pending -> invited (or expired after its deadline)
--   group_members.joined  -> accepted
--   group_members.skipped -> declined
--
-- Existing arrived_at remains the independent attendance timestamp. It is not
-- folded into invitation_status. The legacy went column is retained until its
-- historical meaning and later attendance API are migrated separately.

begin;

alter table groups
  add column invite_expires_at timestamptz,
  add column confirmed_at timestamptz,
  add column status_changed_at timestamptz not null default now();

update groups
set invite_expires_at =
  ((on_date + start_time) at time zone 'America/Vancouver') - interval '10 minutes';

alter table groups
  alter column invite_expires_at set not null,
  drop constraint groups_status_check;

alter table group_members
  drop constraint group_members_response_check;

alter table group_members
  rename column response to invitation_status;

update group_members
set invitation_status = case invitation_status
  when 'pending' then 'invited'
  when 'joined' then 'accepted'
  when 'skipped' then 'declined'
  else invitation_status
end;

-- A recorded arrival is attendance evidence and therefore implies that the
-- legacy member accepted the invitation.
update group_members
set invitation_status = 'accepted'
where arrived_at is not null
  and invitation_status <> 'accepted';

-- Unanswered invitations whose deadline is already past are migrated as
-- expired rather than remaining actionable forever.
update group_members as member
set invitation_status = 'expired'
from groups as matched_group
where matched_group.id = member.group_id
  and member.invitation_status = 'invited'
  and matched_group.invite_expires_at <= now();

-- Map groups using the migrated accepted memberships. A proposed group that
-- already reached three accepts is treated as confirmed and caught up to active
-- or completed when its meeting time has passed. An under-threshold proposed
-- group past its deadline is dissolved.
update groups as matched_group
set status = case
  when matched_group.status = 'cancelled' then 'dissolved'
  when matched_group.status = 'completed' then 'completed'
  when matched_group.status = 'active'
    and (
      select count(*)
      from group_members as member
      where member.group_id = matched_group.id
        and member.invitation_status = 'accepted'
    ) < 3
    then 'dissolved'
  when matched_group.status = 'active'
    and ((matched_group.on_date + matched_group.end_time)
      at time zone 'America/Vancouver') <= now()
    then 'completed'
  when matched_group.status = 'active' then 'active'
  when matched_group.status = 'proposed'
    and (
      select count(*)
      from group_members as member
      where member.group_id = matched_group.id
        and member.invitation_status = 'accepted'
    ) >= 3
    and ((matched_group.on_date + matched_group.end_time)
      at time zone 'America/Vancouver') <= now()
    then 'completed'
  when matched_group.status = 'proposed'
    and (
      select count(*)
      from group_members as member
      where member.group_id = matched_group.id
        and member.invitation_status = 'accepted'
    ) >= 3
    and ((matched_group.on_date + matched_group.start_time)
      at time zone 'America/Vancouver') <= now()
    then 'active'
  when matched_group.status = 'proposed'
    and (
      select count(*)
      from group_members as member
      where member.group_id = matched_group.id
        and member.invitation_status = 'accepted'
    ) >= 3
    then 'confirmed'
  when matched_group.status = 'proposed'
    and matched_group.invite_expires_at <= now()
    then 'dissolved'
  else 'forming'
end;

-- The exact historical confirmation time is unknowable. For migrated groups
-- that demonstrably reached the threshold, use the earlier of migration time
-- and meeting start as a conservative legacy marker.
update groups as matched_group
set confirmed_at = least(
  now(),
  (matched_group.on_date + matched_group.start_time)
    at time zone 'America/Vancouver'
)
where matched_group.status in ('confirmed', 'active', 'completed')
  and (
    select count(*)
    from group_members as member
    where member.group_id = matched_group.id
      and member.invitation_status = 'accepted'
  ) >= 3;

alter table groups
  add constraint groups_status_check
    check (status in ('forming', 'confirmed', 'active', 'completed', 'dissolved')),
  add constraint groups_confirmed_timestamp_check
    check (status <> 'confirmed' or confirmed_at is not null),
  add constraint groups_invite_deadline_check
    check (
      invite_expires_at <=
        ((on_date + start_time) at time zone 'America/Vancouver')
    );

alter table group_members
  add constraint group_members_invitation_status_check
    check (invitation_status in ('invited', 'accepted', 'declined', 'expired')),
  add constraint group_members_arrival_requires_acceptance_check
    check (arrived_at is null or invitation_status = 'accepted');

create index group_members_active_invitation_idx
  on group_members (student_id, invitation_status)
  where invitation_status in ('invited', 'accepted');

-- This is the only Phase 2 write path for invitation responses. Locking the
-- group before its membership gives concurrent responses a consistent order,
-- and the third acceptance confirms the group in the same transaction.
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
  -- since advanced or the deadline has passed.
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
  'Time the group first reached three accepted invitations; legacy values may be approximate.';
comment on column groups.status_changed_at is
  'Time of the most recent lifecycle transition; mutation code must update this field.';
comment on column group_members.invitation_status is
  'Invitation response only; attendance remains in arrived_at and later check-in records.';
comment on column group_members.arrived_at is
  'Attendance timestamp, independent from invitation_status. QR check-in is not yet implemented.';

commit;
