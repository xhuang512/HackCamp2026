# Design report, 2026-11-08

Figma file: [HackCamp 2026 Design Workshops (Copy) (Copy)](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-)
Page: **Hackercamp (IDEAS)** (`8014:2`). Read only. Nothing in the file was changed.

The design calls the product **Campus Café** in older frames and **UBC Meet** in
newer ones. Our app is **Hangout**. Treated as a working-title difference, not a
rename, per your note.

## Phase 1, map the design

### What is in the file

The page holds 14 top-level boards. Only some are current. Ordered by node id,
which tracks when each was made:

| Board | Node | Fidelity | Use |
| --- | --- | --- | --- |
| Mobile wireframes | `8036:2` | Wireframe | Superseded |
| Desktop web wireframes | `8037:2` | Wireframe | Not our form factor |
| Wireframes from yellow sketches | `8040:2` | Wireframe, 460×620 | **Only source for onboarding** |
| Badge collection / Campus Cat badges / Monthly badge tests | `8047:2` `8048:2` `8052:2` | High | Tier 3 feature |
| Hackathon demo flow | `8055:2` | Mid | Superseded |
| Finder-style website | `8056:2` | Mid | Desktop, not our form factor |
| **Mobile web redesign** | `8064:2` | **High, 390×844** | **Primary source** |
| **Student schedule** | `8068:2` | **High, 390×844** | **Primary source** |
| Student profile stickers | `8096:2` | High | Tier 3 asset set |
| Meetup QR check-in | `8099:2` | High | Check-in copy |
| Kip tribute badge | `8137:2` | High | Tier 3 asset |

Eleven frames are drawn at exactly **390×844**, which matches the width AGENTS.md
names for the app. Those are the real target. Everything else is either an
earlier pass or a desktop exploration.

### Frame map

| Frame | Node | Matches | Files it affects |
| --- | --- | --- | --- |
| 01 · Campus Café | [`8064:8`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8064-8) | Welcome, signed out | `pages/Welcome.jsx` |
| 02 · Right now | [`8064:26`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8064-26) | Right now, open groups listed | `pages/RightNow.jsx`, `components/OpenGroupList.jsx`, `components/GroupCard.jsx`, `components/ModeToggle.jsx` |
| UBC Meet · Groups examples | [`8138:2`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8138-2) | Right now, four open groups | `components/OpenGroupList.jsx` |
| 06 · You joined the group | [`8064:156`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8064-156) | Right now, `my_state: "joined"` | `components/GroupCard.jsx`, `components/SpotRow.jsx` |
| 03 · Campus map | [`8064:74`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8064-74) | Map | `pages/MapPage.jsx`, `components/CampusMapLive.jsx` |
| My profile · Mobile web | [`8081:2`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8081-2) | Me | `pages/Me.jsx` |
| Settings · Mobile web | [`8081:92`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8081-92) | Me, settings section | `pages/Me.jsx`, `components/PausedBanner.jsx` |
| 01 · Scan to check in | [`8099:8`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8099-8) | Check-in scanner | `components/CheckInScanner.jsx` |
| 02 · Your check-in code | [`8099:27`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8099-27) | Check-in code | `components/CheckInCode.jsx` |
| 07 · Your timetable | [`8068:8`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8068-8) | **No screen exists** | would be new |
| Badge collection · November 2026 | [`8101:250`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8101-250) | **No screen exists** | would be new |
| 01 · Create account … 08 · Badges | [`8040:8`](https://www.figma.com/design/rIG6FVvppwm5Yd2Evpf0Dv/HackCamp-2026-Design-Workshops--Copy---Copy-?node-id=8040-8) through `8040:201` | Onboarding steps 1 to 4 | `pages/Onboarding.jsx`, `components/OnboardStep.jsx` |

Bottom navigation in every frame reads **Groups · Map · My profile**. Ours reads
**Right now · Map · Me** (`components/TabBar.jsx`). A label change only, no
routing change, and worth confirming which wording you want.

### Tokens

**The palette already matches.** `tokens.css` was built from the UBC palette and
the Figma frames use the same hex values. Every colour below is already in the
file under the name shown.

| Figma hex | Where it appears | `tokens.css` |
| --- | --- | --- |
| `#002145` | Headings, chip text, dark avatar | `--navy` → `--c-accent-dark` |
| `#0055b7` | Primary button, active tab, selected chip | `--primary` → `--c-accent` |
| `#eaf4fb` | Chips, nav bar, sunken panels | `--mist` → `--c-sunken` |
| `#d9e2ec` | Card border | `--line` → `--c-border` |
| `#0b1b2e` | Body copy | `--ink` → `--c-ink` |
| `#f7fafc` | **Page background** | `--surface` |
| `#ffffff` | **Card background** | `--bg` |

Four real deltas:

1. **Page and card are inverted.** Figma puts `#f7fafc` on the page and white on
   the card. We do the opposite: `--c-bg` is white and `--c-surface` is
   `#f7fafc`. Swapping the two derived tokens fixes every screen at once, which
   is what the layer-3 indirection was for. Nothing else has to change.
2. **Two new avatar fills.** Figma uses `#97d4e9` and `#e0f5f1`. We use
   `#d6f0fb` and `#fff4dc`. Both Figma values clear 4.5:1 against `#002145`
   (9.90:1 and 14.19:1), so they can be adopted as-is in light mode. Dark-mode
   partners do not exist in the file and would stay ours.
3. **Radii do not line up.** Figma uses 8px (button), 10px (card), 14px (screen)
   and 20px (pill). We have `--r-sm: 9px` and `--r-md: 12px`, neither of which
   is 8 or 10. Adding `--r-xs: 8px` and retargeting `--r-sm` to 10px covers it.
4. **Two missing type sizes.** Figma uses 11px (card timestamp) and 22px
   (section heading). Neither exists in the scale. 11px is below the 12px floor
   the rest of the app keeps, so I would render that timestamp at `--t-12`
   and note the change rather than add an 11px token.

### Fonts and assets

**Inter is named in `tokens.css` and never actually loaded.** There is no
`@font-face`, no Google Fonts link in `index.html`, and no local file. Every
screen currently renders in the system sans fallback. The design is Inter
throughout, Bold and Regular only, so Phase 2 has to load it for the app to look
like the design at all. This is the single largest visual gap, and it is
invisible on a Mac because the fallback is reasonable.

`--font-display` points at Space Grotesk, which appears nowhere in the Figma
file and is also not loaded. It can go.

Assets to export, all Tier 3 and none needed for the approved work:

| Asset | Frame | Notes |
| --- | --- | --- |
| Mountain and sun illustration | `8064:8` | The one image on Welcome. Flat shapes, exports clean as SVG. |
| Badge stickers (Super Host, Study Regular, Social Regular, Campus Cat, Kip) | `8096:2`, `8047:2`, `8137:2` | Tier 3 |
| Profile avatar illustration | `8081:2` | Tier 3 |

The QR in `8099:27` is a placeholder. We generate ours with `qrcode`, so nothing
to export.

### Design without a feature

Frames and elements for things the app does not do. None of these get built
without you approving them.

| In the design | Tier in AGENTS.md |
| --- | --- |
| Badges, Super Host, badge collection, Campus Cat, Kip tribute, monthly badge tests | **Tier 3** (points, awards, customization) |
| "Meet again next week" card | **Tier 3** (recurring groups) |
| Timetable day view with class blocks | **Tier 2** (schedule parsing). Backend landed today; there is no read endpoint yet, so the view cannot be filled. |
| "Continue with UBC email" as the only sign-in | **Tier 3**, and `docs/signup.md` has UBC-only email paused |
| Six-digit typed check-in code | **Not in AGENTS.md.** See the concern below. |
| Group description free text ("Come join us! We're studying for…") | Not in AGENTS.md |
| "Alex is your captain" | Not in AGENTS.md. No captain or host role exists. |
| "Register by Tuesday, 2:00 PM PDT" | Not in AGENTS.md |
| Pronouns, major, minor, year on the profile | Not in AGENTS.md |
| "Browse buildings" list under the map | Not in AGENTS.md |
| "Joined 26 meetups" | Closest thing to the pitch metric, but no endpoint returns it |
| Desktop and Finder-style boards | Not our form factor |

### Feature without a design

App screens and states with no frame anywhere in the file.

| Not in the design | Where it lives |
| --- | --- |
| **Projector** | `pages/Projector.jsx`. Tier 1, the stage screen, and there is no frame for it at all. |
| **Onboarding at 390px** | Only 460×620 wireframes exist. Steps 1 to 4 would be extrapolated. |
| **Loading, empty and error states** | `components/StateCard.jsx` is used on every screen. The design shows only the happy path. |
| **Dark mode** | Every frame is light. `tokens.css` has a full dark palette with no design source. |
| **Forming group** | The "Waiting for N more to confirm" state, with the spot hidden. The design only ever shows a confirmed group. |
| Paused banner | `components/PausedBanner.jsx` |
| Guest sign-in | The demo path. Welcome shows only the UBC email button. |
| Start a group form | `components/StartGroupForm.jsx` |
| Course entry | `components/CourseInput.jsx` |
| Session expired | The 401 recovery path in `lib/api.js` |
| Open groups empty state | "No open groups yet" |

### Accessibility

**Contrast passes everywhere in light mode.** I resolved each pair and measured
it:

| Foreground | Background | Ratio |
| --- | --- | --- |
| `#002145` | `#f7fafc` page | 15.37:1 |
| `#002145` | `#eaf4fb` chip | 14.45:1 |
| `#0b1b2e` | `#ffffff` card | 17.35:1 |
| `#0b1b2e` | `#eaf4fb` | 15.56:1 |
| `#ffffff` | `#0055b7` button | 7.04:1 |
| `#002145` | `#97d4e9` avatar | 9.90:1 |
| `#002145` | `#e0f5f1` avatar | 14.19:1 |
| `#0055b7` active tab | `#eaf4fb` nav | 6.31:1 |

No pair needs a substitute shade. That is unusual and worth telling the
designers.

**Eleven interactive targets fall under 44px.** AGENTS.md sets 44px as the floor
for the Most Accessible Design track.

| Target | Height | Frame |
| --- | --- | --- |
| "Social" and "✓ Study" mode chips | **34px** | `8198:8`, `8198:10` |
| Filter chips | **36 to 37px** | `8143:3`, `8143:5`, `8040:64` and others |
| "Edit timetable" | **41px** | `8081:103` |
| "Pause suggestions · Off" | **41px** | `8081:98` |

Every primary button is 44 or 46px and passes. The fix for the chips is padding,
not size, so it costs nothing visually: 9px vertical padding becomes 14px.

One more, which the design gets right and is worth keeping: the selected mode
chip carries a **✓** as well as its fill, so colour is not the only thing
marking selection.

### Concerns, where the design and the rules disagree

Three, and the first two are privacy rules rather than preferences.

**1. Initials appear on cards the student has not joined.** Frames `8064:26` and
`8138:2` show "JW", "A", "R", "MK", "SL" on open-group cards, above a Join
button. AGENTS.md: "Anything public (open groups before joining, the map, the
projector) shows no names." Initials identify people in a group of four on a
campus where everyone shares courses. Our `OpenGroupList` shows a count and
shared tags and no initials, which is correct.

Reading the two together, I would keep the avatar row as the design's visual
rhythm but fill it with **anonymous shapes** before joining, swapping to real
initials on `8064:156`, the joined frame, where AGENTS.md allows first names to
group members. That keeps the layout and the rule.

**2. The meeting spot is shown before joining.** Frame `8064:26` prints "The
Nest · Room 2301" on a card whose button still reads "Join group". AGENTS.md:
"Meeting spots are public campus buildings, revealed only once the group is
confirmed", and the backend enforces more than that since the last integration
pass: the spot is `null` until the group is past forming **and** the caller has
joined. The frame shows a room number, which is more precise than a building.

The API cannot return a spot in this state, so the design cannot be built as
drawn. The joined frame `8064:156` shows the spot correctly.

**3. The six-digit typed code weakens check-in.** Frames `8099:8` and `8099:27`
offer "482 716" as a manual alternative to scanning. AGENTS.md: the backend
signs the QR, "it changes every 30 seconds, and it only validates between
members of the same group". A six-digit code that a student reads aloud is
guessable, shareable and screenshot-able, and it checks in someone who is not in
the room, which is the one thing the pitch metric must not allow. Our
`CheckInScanner` is camera only.

I would build the scanner and the QR from these frames and leave the manual code
out. Worth a sentence to the designers about why.

Two smaller mismatches, not rule breaks:

- **Group sizes read "9+ people"** across the frames. AGENTS.md says the matcher
  suggests 4 to 5 and confirms at `MIN_GROUP_SIZE` 3. The cards would show 3 to
  5, so the avatar row never needs an overflow chip.
- **The map shows a dashed walking route** between pins. We have no routing. The
  design's grid-style map also does not match Leaflet tiles.

### Proposed order

Tokens first, then screens in the order a student meets them.

1. **Tokens and fonts.** Load Inter. Swap `--c-bg` and `--c-surface`. Add the
   two avatar fills, `--r-xs: 8px`, `--r-sm: 10px` and `--t-22`. Drop Space
   Grotesk. One commit, no screen changes, and every screen shifts at once.
2. **Welcome** (`8064:8`). First thing a student sees, and the simplest frame.
3. **Right now** (`8064:26`, `8138:2`, `8064:156`). The screen the app is for.
   Three frames, one screen, including the joined state.
4. **Check-in** (`8099:8`, `8099:27`). Scanner and code, camera only.
5. **Map** (`8064:74`). Header and the building sheet. The tiles stay Leaflet.
6. **Me and Settings** (`8081:2`, `8081:92`).
7. **Onboarding** (`8040:8` to `8040:201`). Last, because the source is a
   460×620 wireframe and the most extrapolation is needed.

Not proposed: the projector (no frame), badges (Tier 3), the timetable view (no
read endpoint), and every item under "Design without a feature".

---

*Phases 2 to 4 are appended below once approved.*
