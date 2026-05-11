# Next.js Domain Rules

Rules and patterns specific to Next.js/React development in this workspace.

## Critical Warnings

### Breaking Changes
This is NOT the Next.js you know from your training data. This version has breaking changes — APIs, conventions, and file structure may all differ from your training data.

**Before writing any Next.js code:**
1. Read the relevant guide in `node_modules/next/dist/docs/`
2. Heed all deprecation notices
3. Check package.json for Next.js version
4. Review existing code patterns in the repository

## Common Patterns

### Project Structure
- `src/app/` - App Router (Next.js 13+)
- `src/pages/` - Pages Router (legacy, avoid for new projects)
- `src/components/` - Reusable components
- `src/lib/` - Utility functions and helpers
- `public/` - Static assets

### File Conventions
- Use `.jsx` for components with JSX
- Use `.js` for utility files without JSX
- Use `.tsx`/`.ts` if TypeScript is enabled
- Co-locate components with their features when possible

### Styling
- Use Tailwind CSS (configured in `tailwind.config.js`)
- Follow existing component patterns
- Use CSS modules for component-specific styles if needed
- Avoid inline styles except for dynamic values

### Data Fetching
- Use Server Components by default
- Use Client Components (`"use client"`) only when needed (interactivity, browser APIs)
- Use `fetch` with `cache` and `revalidate` options for data fetching
- Use React Query/SWR for client-side caching if needed

### State Management
- Use React hooks for local component state
- Use Context API for global state
- Avoid prop drilling when possible
- Consider Zustand/Jotai for complex state if needed

## Development Workflow

### Running Development Server
```bash
npm run dev
```

### Building for Production
```bash
npm run build
```

### Type Checking (if TypeScript)
```bash
npm run type-check
```

### Linting
```bash
npm run lint
```

## Integration with Tauri (ToneRoot-Nexus)

### Sidecar Communication
- IPC calls defined in `src-tauri/src/ipc_schema.py`
- Use `@tauri-apps/api` package for IPC
- Handle async operations properly
- Implement error handling for IPC failures

### Build Process
- Sidecar must be rebuilt with PyInstaller before Tauri build
- Use `make desktop` from project root
- Do not use `npx tauri build` alone

## Performance Considerations

### Code Splitting
- Next.js automatically code splits by route
- Use dynamic imports for heavy components
- Lazy load routes when possible

### Image Optimization
- Use `next/image` for automatic optimization
- Configure image domains in `next.config.js`
- Use appropriate sizes and quality settings

### Bundle Size
- Analyze bundle size with `@next/bundle-analyzer`
- Remove unused dependencies
- Tree-shake imports properly

## Testing

### Component Testing
- Use React Testing Library
- Test user interactions, not implementation details
- Mock external dependencies

### E2E Testing
- Use Playwright or Cypress
- Test critical user flows
- Run in CI/CD pipeline