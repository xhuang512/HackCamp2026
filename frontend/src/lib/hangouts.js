/* Shared helpers for map pins. No React, no DOM.

   A pin is a building with a count on it, which is what GET /map returns.
   It is never a person: the endpoint omits any building with fewer than
   three students rather than sending a number somebody could be singled out
   by, and no name reaches this file at all.

   The label is defined once and used in three places: the pin's aria-label,
   the pin's popup, and the sheet's button list. Keeping them identical is
   the point, so a screen-reader user and a sighted user are told the same
   thing. */

/** The accessible name for one building. Carries no student names. */
export function placeLabel(place) {
  const people = place.count === 1 ? '1 student' : `${place.count} students`
  const groups = place.groupsMeeting === 0
    ? ''
    : place.groupsMeeting === 1
      ? '1 group meeting here now'
      : `${place.groupsMeeting} groups meeting here now`
  if (place.mine) {
    return `${place.name}, where your group is meeting${groups ? `, ${groups}` : ''}, ${people} free nearby`
  }
  return `${place.name}${groups ? `, ${groups}` : ''}, ${people} free nearby`
}

/** The short line under the place name in the sheet list. */
export function placeMeta(place) {
  const people = place.count === 1 ? '1 student' : `${place.count} students`
  const groups = place.groupsMeeting === 0 ? '' : place.groupsMeeting === 1 ? '1 group meeting' : `${place.groupsMeeting} groups meeting`
  return place.mine ? `Your group is here${groups ? ` · ${groups}` : ''} · ${people} free` : `${groups ? `${groups} · ` : ''}${people} free nearby`
}

/** GET /map into the pins the map and the sheet both draw.

    The caller's own group building is merged in rather than added twice:
    it is already in `buildings` when enough people are there, and absent
    when it is not, and either way it should appear once and marked. */
export function placesFrom(map) {
  const buildings = map?.buildings ?? []
  const mine = map?.my_group ?? null

  const places = buildings.map((building) => ({
    id: building.slug,
    slug: building.slug,
    name: building.name,
    lat: building.lat,
    lng: building.lng,
    count: building.free_count,
    groupsMeeting: building.groups_meeting ?? 0,
    mine: mine !== null && mine.slug === building.slug,
  }))

  if (mine !== null && !places.some((place) => place.slug === mine.slug)) {
    places.unshift({
      id: mine.slug,
      slug: mine.slug,
      name: mine.name,
      lat: mine.lat,
      lng: mine.lng,
      /* The group's own joined count, which the student is entitled to:
         they are in it. The three-student floor is about other people's
         buildings, not your own meeting spot. */
      count: mine.joined_count,
      groupsMeeting: 1,
      mine: true,
    })
  }

  /* Busiest first, so the sheet list reads top down and the student's own
     building still stands out by its label rather than its position. */
  return places.sort((a, b) => b.count - a.count)
}
