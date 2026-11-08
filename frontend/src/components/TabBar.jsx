import { NavLink } from 'react-router-dom'
import Icon from './Icon.jsx'

/* The bottom bar: an icon above each label.

   The icon is decorative, not the label. A bar that is icons alone asks
   every new student to guess, and the three destinations here are not
   conventional enough to guess, so the words stay and the icon is
   recognition rather than the only cue.

   The active tab is marked three ways on purpose: colour, weight, and a
   tinted pill behind the icon. Colour alone fails for anyone who cannot
   separate the accent from the muted ink. */
const TABS = [
  { to: '/', label: 'Groups', icon: 'group' },
  { to: '/map', label: 'Map', icon: 'map' },
  { to: '/me', label: 'My profile', icon: 'person' },
]

export default function TabBar() {
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map(({ to, label, icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) =>
            isActive ? 'tabbar__link is-active' : 'tabbar__link'
          }
        >
          {({ isActive }) => (
            <>
              <span className="tabbar__icon">
                <Icon name={icon} size={22} />
              </span>
              <span className="tabbar__label">{label}</span>
              {isActive && <span className="sr-only"> (current page)</span>}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
