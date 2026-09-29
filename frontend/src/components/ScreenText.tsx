import { useLayoutEffect, useRef } from 'react'

export function ScreenText({
  text,
  className = '',
  maxSize,
  minSize = 14,
  suffix,
}: {
  text: string
  className?: string
  maxSize: number
  minSize?: number
  suffix?: string
}) {
  const ref = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    let active = true
    function fit() {
      if (!element || !active) return
      let size = maxSize
      element.style.fontSize = `${size}px`
      while (
        size > minSize &&
        (element.scrollWidth > element.clientWidth + 1 ||
          element.scrollHeight > element.clientHeight + 1)
      ) {
        size -= 1
        element.style.fontSize = `${size}px`
      }
    }
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(element)
    // A late font can change text width without resizing the fixed text box.
    document.fonts.addEventListener('loadingdone', fit)
    void document.fonts.ready.then(fit)
    return () => {
      active = false
      observer.disconnect()
      document.fonts.removeEventListener('loadingdone', fit)
    }
  }, [text, maxSize, minSize, suffix])
  return (
    <span ref={ref} className={`screen-fit ${className}`}>
      {suffix ? (
        <>
          <span className="screen-text-value">{text}</span>{' '}
          <span className="screen-text-suffix">{suffix}</span>
        </>
      ) : (
        text
      )}
    </span>
  )
}
