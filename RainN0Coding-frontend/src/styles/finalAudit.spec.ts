import { describe, expect, it, vi } from 'vitest'

async function source(path: string) {
  const { readFileSync } = await vi.importActual<{
    readFileSync: (path: string, encoding: 'utf8') => string
  }>('node:fs')
  return readFileSync(path, 'utf8')
}

describe('final interface audit contracts', () => {
  it('uses one page main landmark and an announced agent status', async () => {
    const chatDetail = await source('src/pages/chat/ChatDetail.vue')
    const agentProgress = await source('src/components/generation/AgentProgress.vue')

    expect(chatDetail).not.toMatch(/<main\s+class="conversation"/)
    expect(chatDetail).toMatch(/<section\s+class="conversation"/)
    expect(agentProgress).toMatch(/role="status"/)
    expect(agentProgress).toMatch(/aria-live="polite"/)
  })

  it('keeps touch targets at least 44px and dialogs scroll-contained', async () => {
    const files = [
      'src/assets/styles/main.css',
      'src/pages/admin/AppManagement.vue',
      'src/pages/admin/UserManagement.vue',
      'src/pages/admin/AppDetailAdmin.vue',
      'src/pages/admin/IntentTreeConfig.vue',
    ]
    const contents = await Promise.all(files.map(source))

    expect(contents.join('\n')).not.toMatch(/min-height:\s*40px/)
    expect(contents[0]).not.toMatch(/\.brand-mark__symbol\s*{[^}]*\b(?:width|height):\s*40px/s)
    for (const content of contents.slice(1)) {
      for (const dialogRule of content.matchAll(/\.confirm-dialog\s*{([^}]*)}/g)) {
        expect(dialogRule[1]).toMatch(/overscroll-behavior:\s*contain/)
      }
    }
  })

  it('gives non-auth form controls stable names and autocomplete behavior', async () => {
    const files = [
      'src/layouts/ChatLayout.vue',
      'src/components/generation/PromptComposer.vue',
      'src/components/projects/ProjectListToolbar.vue',
      'src/pages/chat/ChatDetail.vue',
      'src/pages/admin/AppManagement.vue',
      'src/pages/admin/UserManagement.vue',
      'src/pages/admin/IntentTreeConfig.vue',
    ]
    for (const file of files) {
      const contents = await source(file)
      const controls = contents.match(/<(?:input|textarea|select|a-input)\b[^>]*>/g) ?? []
      for (const control of controls) {
        expect(control, `${file}: ${control}`).toMatch(/\bname=/)
        expect(control, `${file}: ${control}`).toMatch(/\bautocomplete="off"/)
      }
    }
  })

  it('avoids unsafe animation, markup, and focus patterns', async () => {
    const { readdirSync, readFileSync, statSync } = await vi.importActual<{
      readdirSync: (path: string) => string[]
      readFileSync: (path: string, encoding: 'utf8') => string
      statSync: (path: string) => { isDirectory: () => boolean }
    }>('node:fs')
    const { join } = await vi.importActual<{ join: (...paths: string[]) => string }>('node:path')
    const files: string[] = []
    const visit = (directory: string) => {
      for (const entry of readdirSync(directory)) {
        const path = join(directory, entry)
        if (statSync(path).isDirectory()) visit(path)
        else if (/\.(?:vue|css)$/.test(path)) files.push(path)
      }
    }
    visit('src')
    const contents = files.map((file) => readFileSync(file, 'utf8')).join('\n')

    expect(contents).not.toMatch(/transition:\s*all\b/)
    expect(contents).not.toMatch(/\bv-html\b/)
    expect(contents).not.toMatch(/[✅❌⚠✓🚀🤖]/u)
    expect(contents).not.toMatch(/outline:\s*none(?![\s\S]{0,400}:focus-visible)/)
  })

  it('configures the production bundle for Spring without changing dev base', async () => {
    const config = await source('vite.config.ts')

    expect(config).toContain("mode === 'production'")
    expect(config).toContain("base: isProduction ? '/api/' : '/'")
    expect(config).toContain("'../src/main/resources/static'")
    expect(config).toContain('emptyOutDir: true')
  })
})
