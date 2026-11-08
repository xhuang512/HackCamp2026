import { NavLink } from 'react-router-dom'
import Icon from './Icon.jsx'

const TABS = [
  { to: '/', icon: 'clock', label: 'Groups' },
  { to: '/map', icon: 'map', label: 'Map' },
  { to: '/me', icon: 'person', label: 'My profile' },
]

export default function TabBar() {
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map(({ to, icon, label }) => (
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
              <Icon name={icon} />
              {label}
              {isActive && <span className="sr-only"> (current page)</span>}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  )
}
