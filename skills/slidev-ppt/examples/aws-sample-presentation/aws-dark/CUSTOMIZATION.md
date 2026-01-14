# Theme Customization Guide

This guide explains how to customize the AWS Dark Theme for your presentations.

## Quick Customization

### Method 1: Global Background for All Content Slides

To change the background color for **all content slides** (default, center, intro, left-right, two-cols, image-right):

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  /* Change background for all content slides */
  --theme-background: #1a1a1a;  /* Dark gray instead of pure black */
}
</style>

# Your Presentation
```

This will apply to all content slides but **NOT** to cover, section, and end slides (which use gradients).

### Method 2: Global Background for Special Slides

To change the gradient backgrounds for cover, section, and end slides:

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  /* Change gradient for cover slide */
  --theme-gradient-cover: linear-gradient(135deg, #232f3e 0%, #ff9900 100%);
  
  /* Change gradient for section slides */
  --theme-gradient-section: linear-gradient(135deg, #232f3e 0%, #00a1e0 100%);
  
  /* Change gradient for end slide */
  --theme-gradient-end: linear-gradient(135deg, #232f3e 0%, #00d4aa 100%);
}
</style>

# Your Presentation
```

### Method 3: Customize Everything

Combine both methods to customize all backgrounds:

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  /* Content slides background */
  --theme-background: rgb(20, 30, 44);  /* Dark blue */
  
  /* Special slides gradients - use Ocean theme */
  --theme-gradient-cover: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-section: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-end: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  
  /* Text and brand colors */
  --theme-text: #f0f0f0;
  --aws-blue: #0099ff;
  --aws-orange: #ff6600;
  
  /* Font sizes */
  --theme-font-size-h1: 3.5rem;
  --theme-font-size-h2: 2.5rem;
  --theme-font-size-p: 1.25rem;
  
  /* Spacing */
  --theme-padding: 3rem 4rem 2rem 4rem;
  --theme-gap: 4rem;
}
</style>

# Your Presentation
```

### Method 2: Global Theme Configuration

Edit `theme-aws-dark/theme.config.js` to change defaults for all presentations:

```javascript
export default {
  colors: {
    background: 'rgb(20, 30, 44)',  // Change this
    text: '#ffffff',                 // Change this
    blue: '#00a1e0',                // Change this
    // ... more colors
  },
  typography: {
    fontSize: {
      h1: '3rem',    // Change this
      h2: '2rem',    // Change this
      // ... more sizes
    },
  },
}
```

## Available CSS Variables

### Colors

```css
--aws-orange: #ff9900;           /* AWS brand orange */
--aws-blue: #00a1e0;             /* AWS brand blue */
--aws-dark-blue: #232f3e;        /* AWS dark blue */
--aws-light-blue: #2e6db5;       /* AWS light blue */
--aws-purple: #9d4edd;           /* AWS purple */
--aws-green: #00d4aa;            /* AWS green */

--theme-background: rgb(20, 30, 44);  /* Slide background */
--theme-text: #ffffff;                 /* Main text color */
--theme-text-secondary: #e0e0e0;      /* Footer text color */
```

### Typography

```css
--theme-font-family: 'Amazon Ember', 'Helvetica Neue', Arial, sans-serif;
--theme-font-size-h1: 3rem;      /* Main title size */
--theme-font-size-h2: 2rem;      /* Section title size */
--theme-font-size-h3: 1.5rem;    /* Subsection title size */
--theme-font-size-p: 1.125rem;   /* Paragraph text size */
--theme-font-size-footer: 0.5rem; /* Footer text size */
```

### Spacing

```css
--theme-padding: 2.5rem 3rem 1.5rem 3rem;  /* Slide padding */
--theme-gap: 3rem;                          /* Column gap */
```

## Common Customization Examples

### Example 1: Lighter Background for Content Slides

```css
<style>
:root {
  /* Change from pure black to dark gray */
  --theme-background: #1a1a1a;
}
</style>
```

Or use the original dark blue:

```css
<style>
:root {
  --theme-background: rgb(20, 30, 44);
}
</style>
```

### Example 2: Larger Text

```css
<style>
:root {
  --theme-font-size-h1: 4rem;
  --theme-font-size-h2: 2.5rem;
  --theme-font-size-p: 1.5rem;
}
</style>
```

### Example 3: Different Brand Colors

```css
<style>
:root {
  --aws-blue: #0066cc;
  --aws-orange: #ff8800;
}

a {
  color: var(--aws-blue);
}

a:hover {
  color: var(--aws-orange);
}
</style>
```

### Example 4: Custom Font

```css
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

:root {
  --theme-font-family: 'Inter', sans-serif;
}
</style>
```

### Example 5: More Spacing

```css
<style>
:root {
  --theme-padding: 3rem 4rem 2rem 4rem;
  --theme-gap: 4rem;
}
</style>
```

### Example 6: Custom Gradient Backgrounds

```css
<style>
:root {
  /* AWS Orange gradient for cover */
  --theme-gradient-cover: linear-gradient(135deg, #232f3e 0%, #ff9900 100%);
  
  /* AWS Green gradient for sections */
  --theme-gradient-section: linear-gradient(135deg, #232f3e 0%, #00d4aa 100%);
  
  /* AWS Purple gradient for end */
  --theme-gradient-end: linear-gradient(135deg, #232f3e 0%, #9d4edd 100%);
}
</style>
```

### Example 7: Use Predefined Gradient Presets

```css
<style>
:root {
  /* Ocean theme */
  --theme-gradient-cover: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-section: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-end: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
}
</style>
```

## Predefined Gradient Background Classes

The theme includes predefined CSS classes for gradient backgrounds. Simply add `class:` to your slide frontmatter:

```yaml
---
layout: center
class: bg-ocean
---

# Your Content
```

## Available Background Classes

### AWS Gradient Classes
- `bg-aws-default`: Blue to Purple (default)
- `bg-aws-blue`: Dark blue to light blue
- `bg-aws-orange`: Dark to orange
- `bg-aws-green`: Dark to green
- `bg-aws-purple`: Dark blue to purple

### Theme Gradient Classes
- `bg-ocean`: Blue gradient (professional, calm)
- `bg-sunset`: Orange to pink (warm, energetic)
- `bg-forest`: Green gradient (natural, growth)
- `bg-night`: Dark blue gradient (elegant, sophisticated)
- `bg-fire`: Red to orange (bold, passionate)
- `bg-royal`: Purple gradient (luxury, creative)
- `bg-tech`: Cyan to blue (modern, technical)

### Solid Color Classes
- `bg-black`: Pure black (#000000)
- `bg-dark-gray`: Dark gray (#1a1a1a)
- `bg-dark-blue`: Dark blue (rgb(20, 30, 44))
- `bg-aws-dark-blue`: AWS dark blue (#141e2c)

### How to Use Background Classes

Simply add the class to any slide:

```yaml
---
layout: center
class: bg-ocean
---

# Ocean Themed Slide
```

Works with any layout:

```yaml
---
layout: default
class: bg-sunset
---

# Sunset Themed Content
```

Multiple classes can be combined:

```yaml
---
layout: center
class: bg-royal custom-padding
---

# Custom Styled Slide
```

### Customizing Default Gradients

To change the default gradients for cover, section, and end slides:

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  /* Use Ocean theme for all special slides */
  --theme-gradient-cover: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-section: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-end: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
}
</style>

# Your Presentation
```

## Per-Slide Customization

You can also customize individual slides using frontmatter:

```yaml
---
layout: default
class: custom-slide
---

<style>
.custom-slide {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.custom-slide h1 {
  color: #ffffff;
  font-size: 4rem;
}
</style>

# Custom Styled Slide
```

## Layout-Specific Customization

### Cover Slide

```css
<style>
.slidev-layout.cover {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
}

.cover .title {
  font-size: 4rem;
  color: #00d4aa;
}
</style>
```

### Section Slide

```css
<style>
.slidev-layout.section {
  background: linear-gradient(135deg, #232f3e 0%, #00a1e0 100%);
}
</style>
```

## Tips

1. **Test Changes**: Use `npm install && npx slidev slides.md` to preview changes
2. **Use Variables**: Prefer CSS variables over hardcoded values for consistency
3. **Scope Styles**: Use class names to limit style changes to specific slides
4. **Keep Readable**: Ensure sufficient contrast between text and background
5. **Mobile Friendly**: Test on different screen sizes

## Troubleshooting

### Changes Not Showing

1. Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
2. Restart Slidev server
3. Check CSS syntax for errors

### Styles Not Applied

1. Ensure `<style>` tag is in the correct location
2. Check CSS specificity (use `!important` if needed)
3. Verify variable names are correct

### Font Not Loading

1. Check font URL is accessible
2. Use web-safe fallback fonts
3. Ensure `@import` is at the top of `<style>` block

## Need Help?

- Check `theme-aws-dark/styles/index.css` for all available styles
- See `ppt-aws-theme-demo/slides.md` for examples
- Refer to [Slidev documentation](https://sli.dev/custom/) for advanced customization
