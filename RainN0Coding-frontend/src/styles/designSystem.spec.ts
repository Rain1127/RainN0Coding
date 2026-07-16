import { describe, expect, it, vi } from 'vitest'

async function readSource(path: string) {
  const { readFileSync } = await vi.importActual<{
    readFileSync: (path: string, encoding: 'utf8') => string
  }>('node:fs')

  return readFileSync(path, 'utf8')
}

describe('design system motion and touch constraints', () => {
  it('keeps all motion within 150–200ms', async () => {
    const tokenStyles = await readSource('src/styles/tokens.css')
    const appSource = await readSource('src/App.vue')
    const duration = Number(tokenStyles.match(/--duration-normal:\s*(\d+)ms/)?.[1])

    expect(duration).toBeGreaterThanOrEqual(150)
    expect(duration).toBeLessThanOrEqual(200)
    expect(appSource).toContain("motionDurationMid: '0.20s'")
  })

  it('keeps the main page as a vertical flex container', async () => {
    const mainStyles = await readSource('src/assets/styles/main.css')
    const rule = mainStyles.match(/\.page-content\s*{([^}]+)}/)?.[1] ?? ''

    expect(rule).toMatch(/display:\s*flex/)
    expect(rule).toMatch(/flex-direction:\s*column/)
    expect(rule).toMatch(/min-width:\s*0/)
    expect(rule).toMatch(/overflow-x:\s*clip/)
  })

  it('gives the compact mobile brand link a 44px touch target', async () => {
    const mainStyles = await readSource('src/assets/styles/main.css')
    const rule = mainStyles.match(/\.mobile-brand-link\s*{([^}]+)}/)?.[1] ?? ''

    expect(rule).toMatch(/min-width:\s*44px/)
    expect(rule).toMatch(/min-height:\s*44px/)
  })
})
