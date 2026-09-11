export function isSentryModule(moduleId: string): boolean {
  return /node_modules[\\/]@sentry[\\/]/.test(moduleId)
}
