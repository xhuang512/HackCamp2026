/* Group members' initials. Members of the same group see each
   other's first names, so initials here are a space decision, not a privacy
   one. GET /groups includes the caller in this list, so this component must
   not append a second, duplicate "You" avatar.

   There is deliberately no public variant. The 8138:2 frame puts initials
   on open-group cards the reader has not joined, which AGENTS.md forbids,
   and OpenGroupOut carries no count to draw anonymous circles from either.
   OpenGroupList shows seats left in that corner instead. */

function initials(name) {
  return name
    .split(/[\s-]+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}

export default function AvatarRow({ members }) {
  return (
    <ul className="avatars" aria-label={`In this group: ${members.join(', ')}`}>
      {members.map((name, i) => (
        <li
          key={name}
          className={name === 'You' ? 'avatar avatar--you' : `avatar avatar--${(i % 3) + 1}`}
          title={name}
        >
          <span aria-hidden="true">{initials(name)}</span>
          <span className="sr-only">{name}</span>
        </li>
      ))}
    </ul>
  )
}
