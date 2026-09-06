export const resolveBuildTarget = (target: string | undefined) => ({
  base: target === 'standalone' ? '/' : '/api/',
  outDir:
    target === 'standalone'
      ? 'dist'
      : '../src/main/resources/static',
})
