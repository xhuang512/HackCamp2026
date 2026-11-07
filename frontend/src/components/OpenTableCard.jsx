/* One open table on the Map screen. Public listings carry no names, so this
   shows the building, seats left, mode and end time only. */

export default function OpenTableCard({ table, busy = false, onJoin }) {
  const where = table.detail ? `${table.building}, ${table.detail}` : table.building

  return (
    <li className="row">
      <div className="row__text">
        <span className="row__name">{where}</span>
        <span className="row__meta">
          {table.seats} {table.seats === 1 ? 'seat' : 'seats'}, {table.mode}, until {table.until}
        </span>
      </div>
      <button
        type="button"
        className="btn btn--dark"
        disabled={busy}
        onClick={() => onJoin(table.id)}
      >
        Join
        <span className="sr-only"> {where}</span>
      </button>
    </li>
  )
}
