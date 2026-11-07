# UBC Study & Social Meetups

A mobile-first web app concept for UBC students to find study groups and social meetups that fit between classes. Students can discover a group during a shared timetable gap or scan a QR code at a campus building to start or join a meetup.

## Why we’re building it

A break between classes is an opportunity to meet classmates, but coordinating schedules and finding somewhere to meet can take longer than the break itself. We’re designing around three details students need to decide whether to join: what the group is doing, when it ends, and whether there’s room.

## How it works

- **Find a group during a class gap.** Students review their free blocks and choose Study or Social. Study suggestions prioritize shared courses. Social suggestions can use shared interests. Each suggestion shows the time and why it matches.
- **Scan a campus QR code.** A code opens the building’s Open Tables page. The app requires verified UBC student sign-in before students can view, host, or join sessions.
- **Start or join an Open Table.** A host chooses Study or Social, adds a topic or activity, sets the number of seats, and picks an end time. Students who opted in and have overlapping availability can receive an invite. The app shares the exact table location after joining and closes the listing at its end time.
- **Earn points for showing up.** Students confirm whether they met up afterward. The proposed rules award 10 points for attending a confirmed meetup or 20 total for hosting one an attendee confirms. A Community Host badge could recognize students who host three confirmed meetups.

| Meetup type | Example |
| --- | --- |
| Study | STAT 302 practice problems at Koerner Library, 1:15–2:00 PM, two seats open |
| Social | Coffee break at the Nest, 1:30–2:00 PM, three seats open |

## HackCamp demo

1. A host scans the Koerner Library QR code and opens a STAT 302 study table.
2. A classmate with a matching free block receives an invite, joins, and sees where to meet.
3. After the session, the classmate confirms the meetup and the host sees the points they earned.

The demo can use one building and sample timetables. The campus map and timetable screenshot import can follow once this flow works.

## Student access and privacy

- QR codes identify a building. Student verification controls access to its sessions.
- Matching uses shared free blocks while keeping full timetables private.
- Meetups take place in public venues. Exact table details are shared with members who join.

## Future direction

Extend Open Tables to public libraries, community centres, and other public venues in nearby municipalities. Commuter students could select areas that work for them and add evening or weekend availability. For example, a student who leaves campus after class could find a STAT 302 study group at a library in Richmond without sharing their home address.
