import Icon from './Icon.jsx'

/* The meeting spot: a public campus building, revealed once the group opts in.
   `building` and `walk_min` are the only fields the contract returns. */

export default function SpotRow({ spot }) {
  return (
    <div className="spot">
      <Icon name="pin" size={24} />
      <div className="spot__text">
        <span className="spot__name">{spot.building}</span>
        <span className="spot__meta">{spot.walk_min} min walk for you</span>
      </div>
    </div>
  )
}
