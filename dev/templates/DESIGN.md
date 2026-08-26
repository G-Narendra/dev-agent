# DESIGN.md — Design Knowledge Base

> This file teaches the agent how to build stunning, modern websites.
> The agent reads this at the start of every session and applies these patterns.
> Update this file with new patterns as you learn them.

---

## 1. Design Token System (shadcn pattern)

Always use CSS custom properties for theming. NEVER use hardcoded colors.

```css
:root {
    /* Radius scale */
    --radius: 0.625rem;
    --radius-sm: calc(var(--radius) * 0.6);
    --radius-md: calc(var(--radius) * 0.8);
    --radius-lg: var(--radius);
    --radius-xl: calc(var(--radius) * 1.4);
    --radius-2xl: calc(var(--radius) * 1.8);

    /* Light theme tokens */
    --background: #ffffff;
    --foreground: #0a0a0a;
    --card: #ffffff;
    --card-foreground: #0a0a0a;
    --primary: #171717;
    --primary-foreground: #fafafa;
    --secondary: #f5f5f5;
    --secondary-foreground: #171717;
    --muted: #f5f5f5;
    --muted-foreground: #737373;
    --accent: #ff9933;
    --accent-foreground: #0a0a0a;
    --destructive: #ef4444;
    --border: #e5e5e5;
    --input: #e5e5e5;
    --ring: #a3a3a3;
}

.dark {
    /* Dark theme tokens */
    --background: #0a0a0a;
    --foreground: #fafafa;
    --card: #171717;
    --card-foreground: #fafafa;
    --primary: #fafafa;
    --primary-foreground: #171717;
    --secondary: #262626;
    --secondary-foreground: #fafafa;
    --muted: #262626;
    --muted-foreground: #a3a3a3;
    --accent: #ff9933;
    --border: #262626;
    --input: #262626;
    --ring: #525252;
}
```

### Token Usage Rules
- `--background` / `--foreground`: Page shell and default text
- `--card` / `--card-foreground`: Elevated surfaces (cards, panels)
- `--primary` / `--primary-foreground`: Main actions, active states
- `--secondary` / `--secondary-foreground`: Supporting surfaces
- `--muted` / `--muted-foreground`: Subtle text, placeholders
- `--accent`: Brand color, highlights, links
- `--border`: All borders and separators
- `--input`: Form control borders
- `--ring`: Focus rings and outlines

---

## 2. Typography System

### Font Stack
```css
--font: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

### Type Scale
| Token | Size | Weight | Use |
|-------|------|--------|-----|
| `text-xs` | 12px | 400-500 | Labels, captions |
| `text-sm` | 14px | 400-500 | Body small, descriptions |
| `text-base` | 16px | 400 | Body text |
| `text-lg` | 18px | 500 | Lead text, subtitles |
| `text-xl` | 20px | 600 | Section descriptions |
| `text-2xl` | 24px | 700 | Card titles |
| `text-3xl` | 30px | 800 | Section titles |
| `text-4xl` | 36px | 800-900 | Hero subtitles |
| `text-5xl` | 48px | 900 | Hero titles |
| `text-6xl` | 60px | 900 | Display titles |

### Typography Rules
1. **Line height**: 1.1 for headings, 1.6-1.8 for body text
2. **Letter spacing**: -0.02em to -0.03em for large headings
3. **Font weight**: 900 for hero titles, 800 for section titles, 700 for card titles, 500 for body
4. **Max width**: Body text should never exceed 65ch (about 650px)
5. **Contrast**: Body text must have 4.5:1 contrast ratio minimum

---

## 3. Color Palettes

### Indian Tricolor Theme
```css
:root {
    --saffron: #ff9933;
    --white: #ffffff;
    --green: #138808;
    --navy: #000080;
}
```

### Professional Blue Theme
```css
:root {
    --blue-50: #eff6ff;
    --blue-500: #3b82f6;
    --blue-600: #2563eb;
    --blue-900: #1e3a5a;
}
```

### Neutral Professional
```css
:root {
    --gray-50: #fafafa;
    --gray-100: #f5f5f5;
    --gray-200: #e5e5e5;
    --gray-500: #737373;
    --gray-900: #171717;
}
```

### Color Rules
1. **60-30-10 rule**: 60% dominant (background), 30% secondary (cards), 10% accent (brand)
2. **Never use pure black** (#000) for text — use #0a0a0a or #171717
3. **Never use pure white** (#fff) for dark mode backgrounds — use #0a0a0a or #171717
4. **Accent color** should appear in: navigation highlights, buttons, links, badges, dots
5. **Muted colors** for secondary text, descriptions, placeholders

---

## 4. Spacing System

### Base Unit: 4px
All spacing should be a multiple of 4px.

| Token | Value | Use |
|-------|-------|-----|
| `space-1` | 4px | Tight gaps |
| `space-2` | 8px | Element gaps |
| `space-3` | 12px | Small padding |
| `space-4` | 16px | Card padding, gaps |
| `space-5` | 20px | Section gaps |
| `space-6` | 24px | Container padding |
| `space-8` | 32px | Card padding |
| `space-10` | 40px | Section spacing |
| `space-12` | 48px | Large gaps |
| `space-16` | 64px | Section padding |
| `space-20` | 80px | Hero padding |
| `space-24` | 96px | Large section padding |

### Spacing Rules
1. **Container max-width**: 1200px with 24px horizontal padding
2. **Section padding**: 80-100px vertical
3. **Card padding**: 24-32px
4. **Gap between cards**: 16-24px
5. **Element spacing**: Never less than 8px between related elements

---

## 5. Layout Patterns

### Hero Section (Split)
```css
.hero {
    min-height: 100vh;
    display: flex;
    align-items: center;
    gap: 60px;
    padding: 120px 24px 80px;
    max-width: 1200px;
    margin: 0 auto;
}
.hero-content { flex: 1; }
.hero-image { flex: 0 0 380px; }
```

### Card Grid
```css
.grid-3 {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
}
@media (max-width: 768px) {
    .grid-3 { grid-template-columns: 1fr; }
}
```

### Timeline
```css
.timeline { position: relative; padding-left: 40px; }
.timeline::before {
    content: '';
    position: absolute;
    left: 7px; top: 8px; bottom: 8px;
    width: 2px;
    background: var(--border);
}
.tl-dot {
    position: absolute;
    left: -40px; top: 8px;
    width: 16px; height: 16px;
    border-radius: 50%;
    background: var(--accent);
    border: 3px solid var(--background);
    box-shadow: 0 0 0 2px var(--accent);
}
```

### Gallery Grid
```css
.gallery {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
}
.gallery-item {
    position: relative;
    border-radius: var(--radius-xl);
    overflow: hidden;
    aspect-ratio: 4/3;
}
.gallery-item.wide { grid-column: span 2; }
.gallery-item:hover img { transform: scale(1.05); }
```

---

## 6. Component Patterns

### Buttons
```css
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 24px;
    border-radius: var(--radius);
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
    border: none;
}
.btn-primary {
    background: var(--primary);
    color: var(--primary-foreground);
}
.btn-primary:hover {
    opacity: 0.9;
    transform: translateY(-1px);
}
.btn-ghost {
    background: transparent;
    color: var(--foreground);
    border: 1px solid var(--border);
}
```

### Cards
```css
.card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: var(--radius-xl);
    padding: 32px;
    transition: transform 0.2s, box-shadow 0.2s, border-color 0.2s;
}
.card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 40px -8px rgba(0,0,0,0.1);
    border-color: var(--accent);
}
```

### Navigation (Glassmorphism)
```css
.nav {
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 100;
    height: 64px;
    background: color-mix(in srgb, var(--background) 80%, transparent);
    backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
}
```

### Form Inputs
```css
input, textarea {
    width: 100%;
    padding: 10px 14px;
    border: 1px solid var(--input);
    border-radius: var(--radius-md);
    background: var(--background);
    color: var(--foreground);
    font-size: 14px;
    font-family: var(--font);
    transition: border-color 0.2s, box-shadow 0.2s;
    outline: none;
}
input:focus, textarea:focus {
    border-color: var(--ring);
    box-shadow: 0 0 0 3px rgba(163,163,163,0.15);
}
```

---

## 7. Animation Patterns

### Fade In Up (for scroll reveals)
```css
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(24px); }
    to { opacity: 1; transform: translateY(0); }
}
.animate-in { animation: fadeInUp 0.6s ease-out both; }
```

### Hover Transforms
```css
.card:hover { transform: translateY(-4px); }
.gallery-item:hover img { transform: scale(1.05); }
.btn:hover { transform: translateY(-1px); }
```

### Transitions
```css
/* Always use these transitions */
transition: transform 0.2s ease;
transition: opacity 0.3s ease;
transition: border-color 0.2s ease;
transition: box-shadow 0.2s ease;
transition: background 0.3s ease;
```

### Animation Rules
1. **Duration**: 0.2-0.3s for interactions, 0.6s for page loads
2. **Easing**: `ease-out` for entries, `ease-in-out` for loops
3. **Transform**: Only translateY (vertical movement) or scale (zoom)
4. **Never animate**: layout properties (width, height, margin, padding)
5. **Scroll reveals**: Use IntersectionObserver, not scroll events

---

## 8. Dark Mode Pattern

```css
/* Toggle with .dark class on <html> */
.dark { /* override tokens */ }

/* JavaScript toggle */
document.documentElement.classList.toggle('dark');
localStorage.setItem('theme', isDark ? 'dark' : 'light');

/* Respect system preference */
if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
    document.documentElement.classList.add('dark');
}
```

### Dark Mode Rules
1. **Invert the token values**, not the colors
2. **Background**: #0a0a0a (not #000000)
3. **Cards**: #171717 (slightly lighter than background)
4. **Borders**: rgba(255,255,255,0.1) or #262626
5. **Text**: #fafafa (not #ffffff)
6. **Shadows**: Increase opacity in dark mode

---

## 9. Responsive Breakpoints

```css
/* Mobile first */
/* sm: 640px — large phones */
/* md: 768px — tablets */
/* lg: 968px — small laptops */
/* xl: 1200px — desktops */

@media (max-width: 968px) {
    .hero { flex-direction: column; text-align: center; }
    .grid-3 { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
    .grid-3 { grid-template-columns: 1fr; }
    .nav-links { display: none; }
}
```

---

## 10. Anti-Patterns (NEVER DO)

1. **NEVER** use hardcoded colors — always use CSS variables
2. **NEVER** use `!important` — fix specificity instead
3. **NEVER** use inline styles — always use CSS classes
4. **NEVER** use `<font>` or `<center>` tags — use CSS
5. **NEVER** use `float` for layout — use flexbox or grid
6. **NEVER** use fixed pixel sizes for fonts — use rem/em or clamp()
7. **NEVER** create fake binary files (images as text) — use remote URLs
8. **NEVER** write more than 200 lines per file — split into multiple files
9. **NEVER** skip responsive design — always add media queries
10. **NEVER** use Comic Sans, Papyrus, or decorative fonts for body text

---

## 11. Image Guidelines

1. **Use remote URLs** for images (Wikimedia, Unsplash, Pexels)
2. **Never create local image files** — the agent can't generate real images
3. **Always add alt text** for accessibility
4. **Use lazy loading** for below-fold images: `loading="lazy"`
5. **Use aspect-ratio** instead of fixed heights
6. **Cover mode** for hero images: `object-fit: cover`

---

## 12. Learnings

> Add new patterns you discover here. The agent will read and apply them.

<!-- Example:
### 2026-08-27: Glassmorphism Pattern
Discovered that `backdrop-filter: blur(12px)` with semi-transparent background
creates a modern glass effect. Use for navigation bars and modals.
-->
