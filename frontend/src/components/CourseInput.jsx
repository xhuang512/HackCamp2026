import { useState } from 'react'
import { MAX_COURSES, addCourse, normalizeCourse } from '../lib/courses.js'

/* The courses a student is taking, for "you both take STAT 302" on a group
   card. Free text rather than a picker: the backend creates a course row for
   any code it has not seen, so there is no catalog to choose from and
   GET /options does not offer one.

   A real <label>, a real <input>, and each added course is a real <button>
   that removes itself, so this works by keyboard with nothing custom. */

export default function CourseInput({ value, onChange }) {
  const [text, setText] = useState('')
  const [problem, setProblem] = useState(null)

  const full = value.length >= MAX_COURSES

  function commit() {
    const raw = text.trim()
    if (raw === '') return
    if (normalizeCourse(raw) === null) {
      setProblem(`"${raw}" is not a course code. They look like STAT 302.`)
      return
    }
    const next = addCourse(value, raw)
    if (next === value) {
      /* Valid, but nothing changed: either a duplicate or the list is full.
         Saying which beats clearing the box and looking broken. */
      setProblem(full ? `That is the most we can take, ${MAX_COURSES}.` : 'You already added that one.')
      return
    }
    setProblem(null)
    setText('')
    onChange(next)
  }

  return (
    <div className="courses">
      <label className="field__label" htmlFor="course-code">
        Courses this term
      </label>
      <p className="courses__helper" id="course-help">
        One at a time, like STAT 302. Students in your group see the ones you
        have in common, never your timetable.
      </p>

      <div className="courses__entry">
        <input
          id="course-code"
          className="field__input"
          type="text"
          inputMode="text"
          autoComplete="off"
          autoCapitalize="characters"
          placeholder="STAT 302"
          aria-describedby="course-help"
          aria-invalid={problem !== null}
          value={text}
          disabled={full}
          onChange={(e) => {
            setText(e.target.value)
            setProblem(null)
          }}
          /* Enter adds a course. The step's own Continue button is a
             different action, so this must not submit the form. */
          onKeyDown={(e) => {
            if (e.key !== 'Enter') return
            e.preventDefault()
            commit()
          }}
        />
        <button
          type="button"
          className="btn btn--outline"
          onClick={commit}
          disabled={full || text.trim() === ''}
        >
          Add
        </button>
      </div>

      {problem !== null && (
        <p className="courses__error" role="alert">{problem}</p>
      )}

      {value.length > 0 && (
        <ul className="tags" aria-label="Courses you added">
          {value.map((code) => (
            <li key={code}>
              <button
                type="button"
                className="chip chip--on chip--removable"
                onClick={() => onChange(value.filter((c) => c !== code))}
              >
                <span>{code}</span>
                <span aria-hidden="true">×</span>
                <span className="sr-only">Remove {code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
