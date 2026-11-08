/* Group members' initials, then you. Members of the same group see each
   other's first names, so initials here are a space decision, not a privacy
   one. The full names stay in the title attribute and the screen reader text. */

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
    <ul className="avatars" aria-label={`In this group: ${members.join(', ')}, and you`}>
      {members.map((name, i) => (
        <li
          key={name}
          className={`avatar avatar--${(i % 3) + 1}`}
          title={name}
        >
          <span aria-hidden="true">{initials(name)}</span>
          <span className="sr-only">{name}</span>
        </li>
      ))}
      <li className="avatar avatar--you">You</li>
    </ul>
  )
}
