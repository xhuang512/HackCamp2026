/* Course codes, normalised the way the backend normalises them.

   POST /students accepts up to ten. The backend's normalize_course_code() in
   backend/app/repositories/reference_data.py strips spaces and hyphens,
   uppercases, then requires 2 to 5 letters followed by 3 digits and an
   optional trailing letter, and stores the result as "STAT 406". A code that
   fails is a 422 for the whole request, which would lose a half-finished
   signup, so the same rule runs here and the student is told before they
   submit.

   Deliberately the same shape as the backend rather than looser. Accepting
   something here that the server rejects is worse than rejecting it here,
   because the rejection arrives after every other answer has been given. */

/** Mirrors COURSE_CODE_PATTERN in reference_data.py. */
const CODE = /^([A-Z]{2,5})([0-9]{3}[A-Z]?)$/

/** The backend's cap, from CreateStudentRequest.courses max_length. */
export const MAX_COURSES = 10

/** "stat 406" or "stat-406" to "STAT 406", or null if it is not a code. */
export function normalizeCourse(value) {
  const compact = String(value).trim().toUpperCase().replace(/[\s-]+/g, '')
  const match = CODE.exec(compact)
  if (match === null) return null
  return `${match[1]} ${match[2]}`
}

/** Add one code to a list, normalised and deduplicated. Returns the list
    unchanged when the code is invalid, already there, or the list is full,
    so the caller can compare identity to see whether anything happened. */
export function addCourse(list, value) {
  const code = normalizeCourse(value)
  if (code === null) return list
  if (list.includes(code)) return list
  if (list.length >= MAX_COURSES) return list
  return [...list, code]
}
