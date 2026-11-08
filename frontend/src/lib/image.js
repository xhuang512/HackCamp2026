/* Shrinking a timetable screenshot before it leaves the phone.

   Two reasons, and the second one matters more than the speed.

   A recent phone screenshot is around 1200 by 2700 and a megabyte or two.
   The venue wifi at a hackathon is the worst network the app will ever run
   on, and 10 MB is the backend's cap, so a photo straight from a camera roll
   can fail the upload outright.

   Drawing through a canvas also drops every piece of metadata the file
   carried. A screenshot is harmless, but a student can just as easily pick a
   photo of a printed timetable, and those carry EXIF with the GPS
   coordinates of wherever it was taken. AGENTS.md says the app does no
   location tracking, so sending that to a provider is not something to
   leave to chance. The re-encode happens whether or not a resize is needed,
   which is why there is no "already small enough" shortcut here. */

const LONG_SIDE = 1600
/* Text stays readable well below this. Below about 0.7, the thin strokes in
   a 9pt course code start to break up and Gemini misreads times. */
const QUALITY = 0.85

export class ImageReadError extends Error {
  constructor(message) {
    super(message)
    this.name = 'ImageReadError'
  }
}

async function decode(file) {
  /* createImageBitmap handles HEIC on Safari, where an <img> does not. */
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file)
    } catch {
      /* Fall through. Older Firefox throws here for some types. */
    }
  }
  const url = URL.createObjectURL(file)
  try {
    return await new Promise((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new ImageReadError('decode failed'))
      img.src = url
    })
  } finally {
    URL.revokeObjectURL(url)
  }
}

/** Re-encode `file` as a JPEG at most 1600px on its long side.

    Returns a File the upload can send as-is. Throws ImageReadError when the
    browser cannot decode the chosen file, which is a different problem from
    a readable image that holds no timetable, and reads as its own message. */
export async function shrinkForUpload(file) {
  const source = await decode(file)
  const width = source.width
  const height = source.height
  if (!width || !height) throw new ImageReadError('image has no dimensions')

  const scale = Math.min(1, LONG_SIDE / Math.max(width, height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(width * scale))
  canvas.height = Math.max(1, Math.round(height * scale))

  const context = canvas.getContext('2d')
  if (context === null) throw new ImageReadError('no 2d canvas context')
  /* The default is fine for photos and visibly soft for 10pt type, which is
     all a timetable is. */
  context.imageSmoothingQuality = 'high'
  context.drawImage(source, 0, 0, canvas.width, canvas.height)
  source.close?.()

  const blob = await new Promise((resolve) =>
    canvas.toBlob(resolve, 'image/jpeg', QUALITY),
  )
  if (blob === null) throw new ImageReadError('could not re-encode the image')

  /* The name and type both have to say JPEG. The backend checks the declared
     content type against the actual bytes and refuses a mismatch. */
  return new File([blob], 'timetable.jpg', { type: 'image/jpeg' })
}
