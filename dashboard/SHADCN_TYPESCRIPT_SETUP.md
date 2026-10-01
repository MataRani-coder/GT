# Ghost Trail — shadcn / TypeScript integration

The dashboard is Vite + React and already uses Tailwind CSS. It was not previously a shadcn project and was JavaScript-only, so the integration adds the shadcn-compatible structure without converting the existing dashboard.

## Added structure

- `dashboard/components.json` — shadcn configuration
- `dashboard/src/components/ui/` — reusable shadcn-style components
- `dashboard/src/lib/utils.ts` — `cn()` helper using `clsx` + `tailwind-merge`
- `dashboard/tsconfig.json` — TypeScript support
- `dashboard/src/vite-env.d.ts` — Vite types
- `@/*` alias in `vite.config.js`

The conventional shadcn UI component path is `src/components/ui`. Keeping reusable primitives there makes imports predictable and lets future shadcn CLI components use the same location. The utility path is `src/lib/utils.ts`.

## Dependencies

Added to `dashboard/package.json`:

- `framer-motion`
- `clsx`
- `tailwind-merge`
- `typescript`

The supplied environment could not complete an npm registry download, so run this once locally:

```bash
cd dashboard
npm install
npm run build
```

If starting from a fresh project, the equivalent shadcn setup is:

```bash
npx shadcn@latest init
npm install framer-motion clsx tailwind-merge
```

Choose TypeScript, Tailwind CSS, `src/components/ui` for components, and `src/lib/utils` for utilities when prompted.

## Integrated components

- `src/components/ui/container-scroll-animation.tsx`
- `src/components/ui/image-stream-hero.tsx`
- `src/pages/VisualIntelligencePage.tsx`

Open `/visual-intelligence` after login to view both components together. The Dashboard hero includes a **VISUAL LAB** navigation control.
