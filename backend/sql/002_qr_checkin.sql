-- Apply this targeted patch to an existing Lifecycle V2 database.
-- Fresh projects should run schema.sql instead.

begin;

-- Atomically verifies two accepted members and preserves any existing arrival
-- timestamp. Locking the group serializes concurrent pair scans.
create or replace function check_in_group_members(
  p_group_id uuid,
  p_scanner_id uuid,
  p_presenter_id uuid,
  p_checked_in_at timestamptz default now()
)
returns table (
  group_id uuid,
  scanner_id uuid,
  presenter_id uuid,
  joined_count bigint,
  checked_in_count bigint,
  scanner_arrived_at timestamptz,
  presenter_arrived_at timestamptz,
  changed_count bigint
)
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  matched_group groups%rowtype;
  accepted_pair_count bigint;
  joined_total bigint;
  checked_total bigint;
  scanner_time timestamptz;
  presenter_time timestamptz;
  changed_total bigint;
  meeting_start timestamptz;
  meeting_end timestamptz;
begin
  if p_checked_in_at is null then
    raise exception 'Check-in timestamp is required'
      using errcode = '22023';
  end if;

  if p_scanner_id = p_presenter_id then
    raise exception 'A member cannot scan their own check-in code'
      using errcode = '22023';
  end if;

  select matched.*
  into matched_group
  from groups as matched
  where matched.id = p_group_id
  for update;

  if not found then
    raise exception 'Group was not found'
      using errcode = 'P0002';
  end if;

  if matched_group.status not in ('confirmed', 'active') then
    raise exception 'Group is not eligible for check-in while %', matched_group.status
      using errcode = 'P0001';
  end if;

  meeting_start :=
    timezone('America/Vancouver', matched_group.on_date + matched_group.start_time);
  meeting_end :=
    timezone('America/Vancouver', matched_group.on_date + matched_group.end_time);

  if p_checked_in_at < meeting_start then
    raise exception 'Check-in opens when the meeting starts'
      using errcode = 'P0001';
  end if;
  if p_checked_in_at >= meeting_end then
    raise exception 'The meeting check-in window has ended'
      using errcode = 'P0001';
  end if;

  -- Stable ordering plus the group lock prevents pair scans from deadlocking.
  perform member.student_id
  from group_members as member
  where member.group_id = p_group_id
    and member.student_id in (p_scanner_id, p_presenter_id)
  order by member.student_id
  for update;

  select count(*)
  into accepted_pair_count
  from group_members as member
  where member.group_id = p_group_id
    and member.student_id in (p_scanner_id, p_presenter_id)
    and member.invitation_status = 'accepted';

  if accepted_pair_count <> 2 then
    raise exception 'Both students must have accepted the invitation before checking in'
      using errcode = 'P0001';
  end if;

  if matched_group.status = 'confirmed' then
    update groups as matched
    set status = 'active',
        status_changed_at = p_checked_in_at
    where matched.id = p_group_id;
  end if;

  update group_members as member
  set arrived_at = p_checked_in_at
  where member.group_id = p_group_id
    and member.student_id in (p_scanner_id, p_presenter_id)
    and member.invitation_status = 'accepted'
    and member.arrived_at is null;
  get diagnostics changed_total = row_count;

  select count(*) filter (where member.invitation_status = 'accepted'),
         count(*) filter (
           where member.invitation_status = 'accepted'
             and member.arrived_at is not null
         )
  into joined_total, checked_total
  from group_members as member
  where member.group_id = p_group_id;

  select member.arrived_at
  into scanner_time
  from group_members as member
  where member.group_id = p_group_id
    and member.student_id = p_scanner_id;

  select member.arrived_at
  into presenter_time
  from group_members as member
  where member.group_id = p_group_id
    and member.student_id = p_presenter_id;

  return query
    select p_group_id,
           p_scanner_id,
           p_presenter_id,
           joined_total,
           checked_total,
           scanner_time,
           presenter_time,
           changed_total;
end;
$$;

revoke all on function check_in_group_members(uuid, uuid, uuid, timestamptz) from public;
revoke all on function check_in_group_members(uuid, uuid, uuid, timestamptz) from anon;
revoke all on function check_in_group_members(uuid, uuid, uuid, timestamptz) from authenticated;
grant execute on function check_in_group_members(uuid, uuid, uuid, timestamptz) to service_role;

comment on function check_in_group_members(uuid, uuid, uuid, timestamptz) is
  'Atomically checks in two accepted members during their Vancouver-local meeting interval.';

commit;
