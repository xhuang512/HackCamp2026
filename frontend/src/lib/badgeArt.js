/* The Campus Cat badge artwork, from the design file's Badge Collection.

   Imported rather than referenced by path so the bundler fingerprints each
   file and a missing one fails the build instead of turning into a broken
   image on the Me screen.

   Keyed by the backend's slug. A slug with no art here falls back to null,
   and the screen draws its lock icon instead, so adding a badge server-side
   degrades rather than breaks. */

import communityHost from '../assets/badges/community-host.png'
import socialRegular from '../assets/badges/social-regular.png'
import studyRegular from '../assets/badges/study-regular.png'
import superHost from '../assets/badges/super-host.png'

const ART = {
  community_host: communityHost,
  social_regular: socialRegular,
  study_regular: studyRegular,
  super_host: superHost,
}

export function badgeArt(slug) {
  return ART[slug] ?? null
}
