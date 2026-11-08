import { NavLink } from 'react-router-dom'

/* Text-only, three labels, as the redesign frames draw the bottom bar. */
const TABS = [
  { to: '/', label: 'Groups' },
  { to: '/map', label: 'Map' },
  { to: '/me', label: 'My profile' },
]

export default function TabBar() {
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map(({ to, label }) => (
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
              {label}
              {isActive && <span className="sr-only"> (current page)</span>}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
