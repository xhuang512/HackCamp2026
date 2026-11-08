/* What the group shares, as the redesign's chip row. These are the only
   things other students see about you, alongside your free block. */

export default function SharedTags({ shared, label = false }) {
  if (shared.length === 0) return null
  return (
    <div className="shared">
      {label && <span className="shared__label" id="why-this-group">Why this group</span>}
      <ul className="tags" aria-label={label ? undefined : 'What this group shares'} aria-labelledby={label ? 'why-this-group' : undefined}>
        {shared.map((tag) => (
          <li key={tag} className="tag">{tag}</li>
        ))}
      </ul>
    </div>
  )
}
