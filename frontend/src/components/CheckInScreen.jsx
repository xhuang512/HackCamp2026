import { useCallback, useState } from 'react'
import CheckInCode from './CheckInCode.jsx'
import CheckInScanner from './CheckInScanner.jsx'
import { formatDay, formatRange } from '../lib/format.js'

/* The redesign's two check-in frames, "Scan to check in" and "Your check-in
   code", on one screen: every member both shows a code and scans one, and
   the backend checks the pair in together.

   The frames' six-digit manual code is not built. The backend accepts only
   the signed hc1 token, so the typed field takes that. */

export default function CheckInScreen({ group, gap, onBack, onCheckedIn }) {
  const [available, setAvailable] = useState(false)
  const setCheckinState = useCallback((_groupId, ok) => setAvailable(ok), [])
  const modeName = group.mode === 'study' ? 'Study' : 'Social'

  return (
    <>
      <button type="button" className="rd-back" onClick={onBack}>‹ Your group</button>
      <header className="rd-head rd-head--tight">
        <h1 className="rd-title">Check in</h1>
      </header>
      <p className="rd-sub rd-sub--sm">
        {modeName} group{gap ? ` · ${formatDay(gap.day)}, ${formatRange(gap)}` : ''}
      </p>

      <div className="checkin-grid">
        {available && <CheckInScanner groupId={group.id} onCheckedIn={onCheckedIn} />}
        <CheckInCode
          groupId={group.id}
          meetingStart={gap?.start}
          onAvailabilityChange={setCheckinState}
        />
      </div>

      <button type="button" className="rd-back rd-back--bottom" onClick={onBack}>Back to meetup</button>
    </>
  )
}
