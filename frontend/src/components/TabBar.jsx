import { NavLink } from 'react-router-dom'
import Icon from './Icon.jsx'

/* The bottom bar: three icons, no visible labels.

   Instagram-minimal, as asked. The label still exists for anyone who cannot
   see the icon: it is in the link's accessible name through an sr-only span,
   so a screen reader reads "Groups, current page" rather than "link".

   The active tab is marked by a FILLED icon, not by colour. That matters
   here more than usual, because with the words gone colour would otherwise
   be the only signal, and this project is entered in the Most Accessible
   Design track. The filled shape reads for everyone; the accent colour is
   reinforcement on top of it. */
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
              <Icon name={icon} size={26} filled={isActive} />
              <span className="sr-only">
                {label}
                {isActive ? ' (current page)' : ''}
              </span>
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
