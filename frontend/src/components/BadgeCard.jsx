import Icon from './Icon.jsx'
import communityHost from '../assets/badges/community-host.png'
import socialRegular from '../assets/badges/social-regular.png'
import studyRegular from '../assets/badges/study-regular.png'
import superHost from '../assets/badges/super-host.png'

/* The "Top badges" card from Figma frame 8081:2 (My profile): a white card,
   round medallions in a row, the name in bold under each.

   ART maps a backend badge slug to its Campus Cat illustration (192×192
   Figma exports in src/assets/badges/). The badge names and rules are the
   backend's (app/badges.py); the art is borrowed from the Figma set, ordered
   from friendliest to most accomplished. A slug with no art falls back to the
   feat/badges glyph on a navy disc. */
const ART = {
  community_host: communityHost,
  social_regular: socialRegular,
  study_regular: studyRegular,
  super_host: superHost,
}

function Medal({ badge }) {
  const art = ART[badge.slug]
  return (
    <span className="rd-medal" aria-hidden="true">
      {art ? (
        <img className="rd-medal__art" src={art} alt="" width="52" height="52" />
      ) : (
        <span className="rd-medal__disc">
          <Icon name="badge" size={26} />
        </span>
      )}
      {!badge.earned && (
        <span className="rd-medal__lock">
          <Icon name="lock" size={14} />
        </span>
      )}
    </span>
  )
}

export default function BadgeCard({ badges }) {
  const earned = badges.filter((badge) => badge.earned).length
  return (
    <section className="rd-badges" aria-labelledby="badges-title">
      <div className="rd-badges__head">
        <h2 className="rd-badges__title" id="badges-title">Badges</h2>
        {badges.length > 0 && (
          <span className="rd-badges__count">{earned} of {badges.length} earned</span>
        )}
      </div>

      {badges.length === 0 ? (
        <p className="rd-badges__empty">
          Badges are not available right now. Your check-ins are still saved.
        </p>
      ) : (
        <ul className="rd-badges__list">
          {badges.map((badge) => {
            const { current, target } = badge.progress
            return (
              <li
                key={badge.slug}
                className={badge.earned ? 'rd-badge' : 'rd-badge rd-badge--locked'}
              >
                <Medal badge={badge} />
                <span className="rd-badge__name">{badge.name}</span>
                <span className="rd-badge__desc">{badge.description}</span>
                {badge.earned ? (
                  <span className="rd-badge__status">Earned</span>
                ) : (
                  <>
                    <span
                      className="rd-badge__bar"
                      role="progressbar"
                      aria-label={`${badge.name} progress`}
                      aria-valuemin={0}
                      aria-valuemax={target}
                      aria-valuenow={current}
                    >
                      <span style={{ width: `${(current / target) * 100}%` }} />
                    </span>
                    <span className="rd-badge__status">
                      <span className="sr-only">Locked. </span>
                      {current} of {target} check-ins
                    </span>
                  </>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
