/* The eyebrow plus big title at the top of every tab screen.
   `action` takes one optional control on the right. */

export default function ScreenHeader({ eyebrow, title, small = false, action }) {
  return (
    <header className="screen-head">
      <div className="screen-head__text">
        {eyebrow !== undefined && (
          <span className="screen-head__eyebrow">{eyebrow}</span>
        )}
        <h1 className={small ? 'screen-head__title screen-head__title--sm' : 'screen-head__title'}>
          {title}
        </h1>
      </div>
      {action}
    </header>
  )
}
