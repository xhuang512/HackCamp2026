export default function StartGroupForm({ now, mode, buildings, loadingBuildings, buildingError, onRetryBuildings, busy, error, onSubmit, onCancel }) {
  function submit(event) {
    event.preventDefault()
    onSubmit(new FormData(event.currentTarget).get('building'))
  }

  return (
    <section className="start-card" aria-labelledby="start-group-title">
      <h2 className="section__title" id="start-group-title">
        {now ? "I'm free now" : 'Start a group for this gap'}
      </h2>
      <p className="row__meta">Choose a public campus building. It is revealed to the group after three people join.</p>
      <form className="start-form" onSubmit={submit}>
        <label className="field">
          <span className="field__label">Meeting building</span>
          <select className="field__input" name="building" defaultValue={buildings[0]?.id} disabled={loadingBuildings || buildings.length === 0}>
            {buildings.map((building) => <option key={building.id} value={building.id}>{building.label}</option>)}
          </select>
        </label>
        {loadingBuildings && <p className="row__meta">Loading meeting buildings…</p>}
        {buildingError && (
          <div className="inline-error" role="alert">
            <span>{buildingError.message}</span>
            <button type="button" className="btn btn--ghost" onClick={onRetryBuildings}>Try again</button>
          </div>
        )}
        {!loadingBuildings && !buildingError && buildings.length === 0 && <p className="inline-error" role="alert">No meeting buildings are configured yet.</p>}
        {error && <p className="inline-error" role="alert">{error.message}</p>}
        <div className="button-row">
          <button type="submit" className="btn btn--primary btn--lg" disabled={busy || loadingBuildings || buildings.length === 0}>
            {busy ? 'Starting…' : `Start ${mode} group`}
          </button>
          <button type="button" className="btn btn--ghost btn--lg" onClick={onCancel} disabled={busy}>Cancel</button>
        </div>
      </form>
    </section>
  )
}
