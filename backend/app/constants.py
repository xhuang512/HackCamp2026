"""Group rules that more than one module has to agree on.

MIN_GROUP_SIZE was two separate default arguments before this file existed:
engine.form_groups(min_size=3) and matching's max_size=5. Two copies of one
rule is one copy too many, because AGENTS.md says the team may lower the
minimum to 2 later and that has to be a single edit.
"""

# A group is confirmed once this many members have joined, and the meeting
# spot is revealed at the same moment. The team may lower it to 2 later.
MIN_GROUP_SIZE = 3

# What the matcher aims for. Bigger than the minimum on purpose: one decline
# or one no-show still leaves a group.
MAX_GROUP_SIZE = 5

# How long one check-in code is valid. AGENTS.md: the code changes every 30
# seconds, so a screenshot is useless.
CHECKIN_WINDOW_SECONDS = 30

# Group states, from AGENTS.md. 001_core_schema.sql shipped with
# proposed/active/completed/cancelled, which had no way to say "confirmed"
# and so no way to store the fact that decides whether the spot is visible.
# sql/002_plan_alignment.sql migrates the values.
FORMING = "forming"
CONFIRMED = "confirmed"
ACTIVE = "active"
COMPLETED = "completed"
DISSOLVED = "dissolved"

# States a group can still be joined or shown in. Excludes completed and
# dissolved.
# ``proposed`` is the pre-002 value. Keeping it readable makes a rolling
# deploy safe: the app works while the migration is being applied, while all
# new API responses still use the AGENTS.md state names.
LEGACY_PROPOSED = "proposed"
LEGACY_CANCELLED = "cancelled"
LIVE_GROUP_STATES = (FORMING, CONFIRMED, ACTIVE, LEGACY_PROPOSED)

# Member states. checked_in is deliberately not one of these: a member who
# has checked in is still a joined member, so check-in is the group_members
# .arrived_at timestamp and the API derives the state from it. Storing it as
# a fourth response value would throw away the fact that they joined.
INVITED = "invited"
JOINED = "joined"
DECLINED = "declined"
EXPIRED = "expired"
CHECKED_IN = "checked_in"
