import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.lifecycle import (
    AttendanceStatus,
    GroupLifecycle,
    GroupStatus,
    InvalidLifecycleTransition,
    InvitationStatus,
    MembershipLifecycle,
    active_capacity_count,
    advance_group_for_time,
    attendance_status,
    expire_invitations,
    respond_to_invitation,
    transition_group,
)


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = datetime(2026, 11, 10, 21, 0, tzinfo=timezone.utc)
        self.deadline = self.start - timedelta(minutes=10)
        self.end = self.start + timedelta(hours=1)
        self.before_deadline = self.deadline - timedelta(minutes=5)
        self.group = GroupLifecycle(
            status=GroupStatus.FORMING,
            invitation_deadline=self.deadline,
            meeting_start=self.start,
            meeting_end=self.end,
        )
        self.members = tuple(
            MembershipLifecycle(student_id=f"student-{index}")
            for index in range(1, 6)
        )

    def test_first_and_second_acceptance_leave_group_forming(self) -> None:
        first = self._respond(self.group, self.members, 1, InvitationStatus.ACCEPTED)
        second = self._respond(
            first.group,
            first.memberships,
            2,
            InvitationStatus.ACCEPTED,
        )

        self.assertEqual(first.accepted_count, 1)
        self.assertEqual(second.accepted_count, 2)
        self.assertEqual(first.group.status, GroupStatus.FORMING)
        self.assertEqual(second.group.status, GroupStatus.FORMING)
        self.assertIsNone(second.group.confirmed_at)

    def test_third_acceptance_confirms_group_exactly_at_threshold(self) -> None:
        update = self._accept_first_three()

        self.assertEqual(update.accepted_count, 3)
        self.assertEqual(update.group.status, GroupStatus.CONFIRMED)
        self.assertEqual(update.group.confirmed_at, self.before_deadline)

    def test_additional_acceptance_is_allowed_after_confirmation(self) -> None:
        confirmed = self._accept_first_three()

        fourth = self._respond(
            confirmed.group,
            confirmed.memberships,
            4,
            InvitationStatus.ACCEPTED,
        )

        self.assertEqual(fourth.group.status, GroupStatus.CONFIRMED)
        self.assertEqual(fourth.accepted_count, 4)
        self.assertEqual(fourth.group.confirmed_at, confirmed.group.confirmed_at)

    def test_declined_invitation_does_not_count_or_consume_active_capacity(self) -> None:
        declined = self._respond(
            self.group,
            self.members,
            1,
            InvitationStatus.DECLINED,
        )

        self.assertEqual(declined.accepted_count, 0)
        self.assertEqual(active_capacity_count(declined.memberships), 4)
        self.assertEqual(declined.group.status, GroupStatus.FORMING)

    def test_accepted_member_cannot_revert_to_declined(self) -> None:
        accepted = self._respond(
            self.group,
            self.members,
            1,
            InvitationStatus.ACCEPTED,
        )

        with self.assertRaisesRegex(
            InvalidLifecycleTransition,
            "cannot change an accepted invitation",
        ):
            self._respond(
                accepted.group,
                accepted.memberships,
                1,
                InvitationStatus.DECLINED,
            )

    def test_repeating_same_invitation_response_is_idempotent(self) -> None:
        accepted = self._respond(
            self.group,
            self.members,
            1,
            InvitationStatus.ACCEPTED,
        )

        repeated = self._respond(
            accepted.group,
            accepted.memberships,
            1,
            InvitationStatus.ACCEPTED,
        )

        self.assertEqual(repeated, accepted)

    def test_unanswered_invitations_expire_and_under_threshold_group_dissolves(self) -> None:
        first = self._respond(
            self.group,
            self.members,
            1,
            InvitationStatus.ACCEPTED,
        )
        second = self._respond(
            first.group,
            first.memberships,
            2,
            InvitationStatus.DECLINED,
        )

        expired = expire_invitations(
            second.group,
            second.memberships,
            at=self.deadline,
        )

        self.assertEqual(expired.group.status, GroupStatus.DISSOLVED)
        self.assertEqual(
            [member.invitation_status for member in expired.memberships],
            [
                InvitationStatus.ACCEPTED,
                InvitationStatus.DECLINED,
                InvitationStatus.EXPIRED,
                InvitationStatus.EXPIRED,
                InvitationStatus.EXPIRED,
            ],
        )
        self.assertEqual(active_capacity_count(expired.memberships), 1)

    def test_expiration_is_idempotent_and_does_not_dissolve_confirmed_group(self) -> None:
        confirmed = self._accept_first_three()

        first = expire_invitations(
            confirmed.group,
            confirmed.memberships,
            at=self.deadline,
        )
        repeated = expire_invitations(
            first.group,
            first.memberships,
            at=self.deadline + timedelta(minutes=1),
        )

        self.assertEqual(first.group.status, GroupStatus.CONFIRMED)
        self.assertEqual(first.accepted_count, 3)
        self.assertEqual(first.memberships[3].invitation_status, InvitationStatus.EXPIRED)
        self.assertEqual(repeated, first)

    def test_invalid_group_transitions_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            InvalidLifecycleTransition,
            "confirmation requires 3",
        ):
            transition_group(
                self.group,
                GroupStatus.CONFIRMED,
                at=self.before_deadline,
                accepted_count=2,
            )

        confirmed = replace(
            self.group,
            status=GroupStatus.CONFIRMED,
            confirmed_at=self.before_deadline,
        )
        with self.assertRaisesRegex(
            InvalidLifecycleTransition,
            "cannot become active before it starts",
        ):
            transition_group(
                confirmed,
                GroupStatus.ACTIVE,
                at=self.start - timedelta(seconds=1),
                accepted_count=3,
            )
        with self.assertRaisesRegex(
            InvalidLifecycleTransition,
            "cannot transition group from confirmed to completed",
        ):
            transition_group(
                confirmed,
                GroupStatus.COMPLETED,
                at=self.end,
                accepted_count=3,
            )

    def test_group_time_transitions_are_ordered_and_idempotent(self) -> None:
        confirmed = self._accept_first_three().group

        active = advance_group_for_time(
            confirmed,
            accepted_count=3,
            at=self.start,
        )
        still_active = advance_group_for_time(
            active,
            accepted_count=3,
            at=self.start + timedelta(minutes=10),
        )
        completed = advance_group_for_time(
            active,
            accepted_count=3,
            at=self.end,
        )

        self.assertEqual(active.status, GroupStatus.ACTIVE)
        self.assertEqual(still_active, active)
        self.assertEqual(completed.status, GroupStatus.COMPLETED)

    def test_attendance_is_separate_from_invitation_status(self) -> None:
        accepted = replace(
            self.members[0],
            invitation_status=InvitationStatus.ACCEPTED,
        )
        checked_in = replace(accepted, checked_in_at=self.start)
        declined = replace(
            self.members[1],
            invitation_status=InvitationStatus.DECLINED,
        )
        completed_group = replace(self.group, status=GroupStatus.COMPLETED)

        self.assertEqual(
            attendance_status(self.group, accepted),
            AttendanceStatus.PENDING,
        )
        self.assertEqual(
            attendance_status(self.group, checked_in),
            AttendanceStatus.CHECKED_IN,
        )
        self.assertEqual(
            attendance_status(self.group, declined),
            AttendanceStatus.NOT_APPLICABLE,
        )
        self.assertEqual(
            attendance_status(completed_group, accepted),
            AttendanceStatus.NO_SHOW,
        )
        self.assertEqual(checked_in.invitation_status, InvitationStatus.ACCEPTED)

    def test_non_accepted_member_cannot_have_check_in_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "only an accepted member"):
            MembershipLifecycle(
                student_id="student-1",
                invitation_status=InvitationStatus.INVITED,
                checked_in_at=self.start,
            )

    def test_invitation_cannot_change_at_or_after_deadline(self) -> None:
        with self.assertRaisesRegex(
            InvalidLifecycleTransition,
            "invitation deadline has passed",
        ):
            respond_to_invitation(
                self.group,
                self.members,
                student_id="student-1",
                response=InvitationStatus.ACCEPTED,
                at=self.deadline,
            )

    def test_expired_invitation_cannot_be_accepted(self) -> None:
        expired_members = (
            replace(
                self.members[0],
                invitation_status=InvitationStatus.EXPIRED,
            ),
            *self.members[1:],
        )

        with self.assertRaisesRegex(
            InvalidLifecycleTransition,
            "cannot change an expired invitation",
        ):
            respond_to_invitation(
                self.group,
                expired_members,
                student_id="student-1",
                response=InvitationStatus.ACCEPTED,
                at=self.before_deadline,
            )

    def _accept_first_three(self):
        update = self._respond(
            self.group,
            self.members,
            1,
            InvitationStatus.ACCEPTED,
        )
        update = self._respond(
            update.group,
            update.memberships,
            2,
            InvitationStatus.ACCEPTED,
        )
        return self._respond(
            update.group,
            update.memberships,
            3,
            InvitationStatus.ACCEPTED,
        )

    def _respond(
        self,
        group: GroupLifecycle,
        memberships: tuple[MembershipLifecycle, ...],
        student_number: int,
        response: InvitationStatus,
    ):
        return respond_to_invitation(
            group,
            memberships,
            student_id=f"student-{student_number}",
            response=response,
            at=self.before_deadline,
        )


if __name__ == "__main__":
    unittest.main()
