import { Component } from 'react'
import CampusMap from './CampusMap.jsx'

/* Catches anything thrown by the lazily loaded Leaflet map.

   Without this, one bad call inside CampusMapLive unmounts the entire
   React tree, so the whole screen goes blank including the tab bar and
   the student cannot even navigate away. That is not hypothetical: a call
   to a Leaflet method that does not exist did exactly that.

   The static CampusMap takes over, so the tab keeps working and the rest
   of the page is unaffected. */

export default class MapBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error, info) {
    /* No coordinates are ever in scope here, so this is safe to log. */
    console.error('Map failed, falling back to the static view.', error, info)
  }

  render() {
    if (this.state.failed) return <CampusMap full />
    return this.props.children
  }
}
