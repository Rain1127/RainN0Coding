import { describe, expect, it } from 'vitest'

import { resolveBuildTarget } from './build-target'

describe('resolveBuildTarget', () => {
  it('builds a standalone image at the web root', () => {
    expect(resolveBuildTarget('standalone')).toEqual({
      base: '/',
      outDir: 'dist',
    })
  })

  it('preserves the Spring static-resource build by default', () => {
    expect(resolveBuildTarget(undefined)).toEqual({
      base: '/api/',
      outDir: '../src/main/resources/static',
    })
  })
})
