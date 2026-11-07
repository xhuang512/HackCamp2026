/* "Why this group". These are the only things other students see about you,
   alongside your free block. */

export default function SharedTags({ shared }) {
  return (
    <div className="shared">
      <span className="shared__label" id="why-this-group">Why this group</span>
      <ul className="tags" aria-labelledby="why-this-group">
        {shared.map((tag) => (
          <li key={tag} className="tag">{tag}</li>
        ))}
      </ul>
    </div>
  )
}
