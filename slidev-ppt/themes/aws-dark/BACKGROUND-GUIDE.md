# Background Customization Guide

This guide explains how to customize backgrounds in the AWS Dark Theme.

## Understanding Background Types

The theme has **two types of backgrounds**:

1. **Content Slides** (black background by default)
   - Layouts: `default`, `center`, `intro`, `left-right`, `two-cols`, `image-right`
   - Default: Pure black (`#000000`)
   - Controlled by: `--theme-background` CSS variable

2. **Special Slides** (gradient backgrounds by default)
   - Layouts: `cover`, `section`, `end`
   - Default: AWS gradient (blue to purple)
   - Controlled by: `--theme-gradient-cover`, `--theme-gradient-section`, `--theme-gradient-end`

## Global Background Settings

### Change All Content Slides

Add this to your presentation's frontmatter:

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  /* Change background for all content slides */
  --theme-background: #1a1a1a;  /* Dark gray */
}
</style>

# Your Presentation
```

**Common options:**
- `#000000` - Pure black (default)
- `#141e2c` - AWS dark blue (professional alternative)
- `#1a1a1a` - Dark gray
- `rgb(20, 30, 44)` - Dark blue (original theme color)
- `#0a0a0a` - Very dark gray

### Change All Special Slides

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

### Mix and Match

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  /* Dark blue for content slides */
  --theme-background: rgb(20, 30, 44);
  
  /* Different gradients for each special slide type */
  --theme-gradient-cover: linear-gradient(135deg, #232f3e 0%, #ff9900 100%);  /* Orange */
  --theme-gradient-section: linear-gradient(135deg, #232f3e 0%, #00a1e0 100%); /* Blue */
  --theme-gradient-end: linear-gradient(135deg, #232f3e 0%, #00d4aa 100%);    /* Green */
}
</style>

# Your Presentation
```

## Per-Slide Background Override

Use predefined CSS classes to override background for individual slides:

```yaml
---
layout: default
class: bg-ocean
---

# This slide uses Ocean gradient
```

```yaml
---
layout: center
class: bg-aws-dark-blue
---

# This slide uses AWS dark blue
```

### Available Background Classes

**Gradient Classes:**
- `bg-aws-default`, `bg-aws-blue`, `bg-aws-orange`, `bg-aws-green`, `bg-aws-purple`
- `bg-ocean`, `bg-sunset`, `bg-forest`, `bg-night`, `bg-fire`, `bg-royal`, `bg-tech`

**Solid Color Classes:**
- `bg-black` - Pure black
- `bg-aws-dark-blue` - AWS dark blue (#141e2c)
- `bg-dark-gray` - Dark gray
- `bg-dark-blue` - Dark blue

## Custom Background for One Slide

If you need a unique background for a single slide:

```yaml
---
layout: center
class: custom-bg
---

<style>
.custom-bg {
  background: linear-gradient(135deg, #your-color-1 0%, #your-color-2 100%) !important;
}
</style>

# Custom Background Slide
```

## Examples

### Example 1: All Dark Blue

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  --theme-background: rgb(20, 30, 44);
}
</style>
```

### Example 2: Ocean Theme Throughout

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  --theme-background: #0a4d68;
  --theme-gradient-cover: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-section: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-end: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
}
</style>
```

### Example 3: Corporate Style (Lighter)

```yaml
---
theme: ../theme-aws-dark
---

<style>
:root {
  --theme-background: #1a1a1a;
  --theme-gradient-cover: linear-gradient(135deg, #232f3e 0%, #00a1e0 100%);
  --theme-gradient-section: linear-gradient(135deg, #232f3e 0%, #00a1e0 100%);
  --theme-gradient-end: linear-gradient(135deg, #232f3e 0%, #00a1e0 100%);
}
</style>
```

## Tips

1. **Consistency**: Use the same gradient family for all special slides for a cohesive look
2. **Contrast**: Ensure sufficient contrast between background and text
3. **Testing**: Preview your presentation to verify backgrounds look good
4. **Per-slide overrides**: Use `class:` for slides that need special emphasis
5. **Keep it simple**: Too many different backgrounds can be distracting

## Troubleshooting

### Background not changing

1. Check CSS syntax in `<style>` block
2. Ensure `:root` selector is used
3. Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
4. Restart Slidev server

### Class not working

1. Verify class name is correct (e.g., `bg-ocean` not `ocean`)
2. Check that class is in the slide frontmatter: `class: bg-ocean`
3. Ensure theme CSS is loaded

### Gradient looks wrong

1. Check gradient syntax: `linear-gradient(135deg, color1 0%, color2 100%)`
2. Verify color values are valid hex or rgb
3. Test gradient in browser dev tools first

## Need Help?

- See `CUSTOMIZATION.md` for more customization options
- Check `ppt-aws-theme-demo/slides.md` for working examples
- Review `theme-aws-dark/styles/index.css` for all available classes
