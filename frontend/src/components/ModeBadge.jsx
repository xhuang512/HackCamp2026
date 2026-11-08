/* Whether a group is social or study, from the backend's `mode`, not from
   the Right now toggle. The two disagree whenever the matcher suggests the
   mode the student has not selected, and the server is the one that knows.

   The mode is spelled out rather than only coloured in, because the two
   fills are a pair of tints and telling them apart is not something to ask
   of anyone. */

const LABELS = {
  social: 'Social',
  study: 'Study',
}

export default function ModeBadge({ mode }) {
  /* An unknown mode is possible: `mode` is a plain string in the API, not an
     enum, so a new one added on the backend reaches here before this file
     knows about it. Showing it raw beats showing nothing. */
  const label = LABELS[mode] ?? mode
  if (!label) return null

  return <span className={`mode-badge mode-badge--${mode}`}>{label}</span>
}
