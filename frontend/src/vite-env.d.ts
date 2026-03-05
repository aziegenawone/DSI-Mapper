/// <reference types="vite/client" />

// Static asset imports
declare module '*.png' {
  const src: string
  export default src
}
declare module '*.jpg' {
  const src: string
  export default src
}
declare module '*.svg' {
  const src: string
  export default src
}

// CSS module imports (plain .css are side-effect imports, no types needed,
// but TS strict mode needs this declaration)
declare module '*.css' {
  const styles: Record<string, string>
  export default styles
}
