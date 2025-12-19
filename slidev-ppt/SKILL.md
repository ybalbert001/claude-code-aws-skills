---
name: slidev-ppt
description: Create and edit presentation slides using Slidev framework when user requests slides, presentations, PPT, or deck creation/modification. Supports AWS dark theme (default) and themes from sli.dev/resources/theme-gallery. Use when user asks to create/edit presentations, build slides, make a PPT/deck, or mentions Slidev.
---

# Slidev PPT Creation

## Overview

Create professional presentations using Slidev, a Markdown-based slide maker for developers. Supports code highlighting, Vue components, diagrams, and powerful layouts with AWS dark theme styling by default.

## Quick Start Workflow

When user requests presentation creation:

1. **Read the complete guide** in `references/slidev-guide.md` - This contains all Slidev syntax, layouts, components, and best practices
2. **Create project directory**: `ppt-{sanitized-topic-name}/`
3. **Generate slides.md** with AWS dark theme (`theme: ../themes/aws-dark`)
4. **Organize content**: Use `pages/` directory for presentations with 10+ slides
5. **Provide preview command**: `npm install && npx slidev ppt-{topic-name}/slides.md`

## Key Principles

**ALWAYS read `references/slidev-guide.md` first** - It contains:
- Complete Slidev syntax reference
- Available layouts (cover, section, default, center, two-cols, image-right, end, etc.)
- Content organization patterns (when to split into chapters)
- Design rules (no animations, content density, diagram guidelines)
- AWS dark theme usage instructions

**Content creation rules:**
- Use AWS dark theme by default: `theme: ../themes/aws-dark`
- NO animations (no v-click, v-motion, v-clicks)
- Split content: Use `layout: section` between topics, `pages/` directory for 10+ slides
- Control image sizes: Always use `{width=500px}` or `{width=60%}`
- Keep diagrams simple: 3-5 nodes max, use scale parameter
- Use emoji for icons: 🚀 ✅ ❌ 💡 (safer than icon components)

## Theme Support

### AWS Dark Theme (Default)

Professional dark theme with AWS branding, located in `themes/aws-dark/`:

```yaml
---
theme: ../themes/aws-dark
---
```

**Features:**
- AWS brand colors and gradients (Blue, Green, Purple, Orange)
- Multiple layouts: cover, section, default, center, two-cols, image-right, end
- GradientText component: `<GradientText color="blue-green">text</GradientText>`
- Background classes: `bg-ocean`, `bg-sunset`, `bg-forest`, etc.
- Footer with AWS logo

**Theme documentation:** `themes/aws-dark/README.md`

### Other Slidev Themes

Slidev supports themes from https://sli.dev/resources/theme-gallery:

```yaml
---
theme: seriph
---
```

Popular themes include: `seriph`, `default`, `apple-basic`, `shibainu`, `bricks`, `purplin`, etc.

**Installation for external themes:**
```bash
npm install slidev-theme-{theme-name}
```

## Project Structure

### Short Presentations (< 10 slides)
```
ppt-{topic}/
├── slides.md          # All content in one file
└── public/            # Optional: images, assets
    └── images/
```

### Long Presentations (10+ slides)
```
ppt-{topic}/
├── slides.md          # Main file with cover, sections, imports, end
├── pages/             # Chapter files
│   ├── 01-introduction.md
│   ├── 02-main-content.md
│   └── 03-conclusion.md
└── public/            # Optional: images, assets
    └── images/
```

## Available Layouts

Reference from AWS dark theme (`themes/aws-dark/README.md`):

- **cover**: Title slide with gradient background
- **section**: Section divider with gradient
- **default**: Standard content slide
- **center**: Centered content
- **two-cols**: Two-column with scrolling support (for content > 10 lines)
- **left-right**: Simple left/right split (for short content < 10 lines)
- **image-right**: Content left, image right
- **end**: Closing slide

## Content Guidelines

### Image Usage
- **Prefer external URLs**: `![Image](https://example.com/image.png){width=500px}`
- **Always control size**: Use `{width=500px}` or `{width=60%}` to prevent overflow
- **Local images**: Place in `public/images/` if needed

### Code Blocks
```markdown
\`\`\`typescript {2-4}
// Line 2-4 highlighted
const example = 'code';
\`\`\`
```

### Diagrams (Mermaid)
```markdown
\`\`\`mermaid {scale: 0.8}
graph LR
    A[Start] --> B[End]
\`\`\`
```

**Keep simple**: 3-5 nodes max, use scale to fit, short labels

### Components

**GradientText** (AWS theme):
```html
<GradientText color="blue-green">Highlighted</GradientText>
```

Colors: `blue-green`, `blue-purple`, `orange-pink`

## Common Mistakes to Avoid

❌ **Do NOT:**
- Use animations (v-click, v-motion) - causes content visibility issues
- Use icon components (`<carbon:xxx />`) - use emoji instead
- Overcrowd slides - split content if > 10 bullet points
- Use `two-cols` for short content - use `left-right` instead
- Forget to control image sizes - always add width parameter
- Create complex diagrams - keep to 3-5 nodes

✅ **DO:**
- Read `references/slidev-guide.md` before starting
- Use AWS dark theme by default
- Split long presentations into chapters (pages/ directory)
- Add section dividers with `layout: section`
- Use external image URLs when possible
- Keep diagrams simple and scaled

## Resources

### Complete Documentation
- **`references/slidev-guide.md`**: Comprehensive guide with all Slidev syntax, layouts, components, best practices, and detailed examples. **Read this file before creating any presentation.**

### Theme Assets
- **`themes/aws-dark/`**: Complete AWS dark theme package with layouts, components, and styling
- **`themes/aws-dark/README.md`**: Theme documentation and usage guide
- **Future themes**: `themes/aws-light/`, `themes/custom/` can be added for extensibility

## Preview and Export

**Preview presentation:**
```bash
npm install && npx slidev ppt-{topic-name}/slides.md
```

**Export to PDF:**
```bash
npx slidev export ppt-{topic-name}/slides.md --format pdf
```

**Export to PPTX:**
```bash
npx slidev export ppt-{topic-name}/slides.md --format pptx
```

## Example Usage

**User request:** "Create a presentation about AWS Lambda"

**Agent workflow:**
1. Read `references/slidev-guide.md` to understand all Slidev capabilities
2. Create directory: `ppt-aws-lambda/`
3. Create `ppt-aws-lambda/slides.md` with:
   - AWS dark theme in frontmatter
   - Cover slide with title
   - Section dividers for major topics
   - Content slides with appropriate layouts
   - End slide with summary
4. If 10+ slides: Create `pages/` directory with chapter files
5. Provide command: `npm install && npx slidev ppt-aws-lambda/slides.md`

**Key point:** The detailed guide in `references/slidev-guide.md` contains all syntax, examples, and best practices. Always read it first to ensure correct Slidev usage and avoid common mistakes.
