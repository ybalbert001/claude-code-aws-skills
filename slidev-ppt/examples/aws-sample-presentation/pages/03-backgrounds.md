# Background Customization

This section demonstrates background customization options.

---
layout: section
---

# Theme Customization

Customize colors and gradients to match your brand

Learn how to:
- Change global background colors
- Apply per-slide background overrides
- Use predefined gradient presets

<!--
Section slide demonstrating customization options with content below title.
-->

---

# Global Background Settings

## Content Slides (default, center, intro, etc.)

Default: **Pure black (#000000)**

Change globally with CSS variable:

```yaml
<style>
:root {
  --theme-background: #1a1a1a;  /* Dark gray */
}
</style>
```

## Special Slides (cover, section, end)

Default: **Gradient backgrounds**

Change globally with CSS variables:

```yaml
<style>
:root {
  --theme-gradient-cover: linear-gradient(...);
  --theme-gradient-section: linear-gradient(...);
  --theme-gradient-end: linear-gradient(...);
}
</style>
```

<!--
Explains the two types of background settings: content slides vs special slides.
-->

---

# Per-Slide Background Override

Use `class:` to override background for individual slides:

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

# This slide uses AWS dark blue background
```

**Available classes:** `bg-ocean`, `bg-sunset`, `bg-forest`, `bg-night`, `bg-fire`, `bg-royal`, `bg-tech`, `bg-aws-blue`, `bg-aws-orange`, `bg-aws-green`, `bg-black`, `bg-dark-gray`, `bg-dark-blue`, `bg-aws-dark-blue`

<!--
Shows how to override background for individual slides using predefined classes.
-->

---
layout: center
class: bg-ocean
---

# 🌊 Ocean Theme

**Professional • Calm • Trustworthy**

This slide uses `class: bg-ocean`

Perfect for corporate or technical presentations

<!--
Demonstrates Ocean gradient background - professional blue tones.
Simply add class: bg-ocean to any slide.
-->

---
layout: center
class: bg-sunset
---

# 🌅 Sunset Theme

**Warm • Energetic • Creative**

This slide uses `class: bg-sunset`

Great for marketing or creative presentations

<!--
Demonstrates Sunset gradient background - warm orange to pink tones.
Simply add class: bg-sunset to any slide.
-->

---
layout: center
class: bg-forest
---

# 🌲 Forest Theme

**Natural • Growth • Sustainable**

This slide uses `class: bg-forest`

Ideal for environmental or growth-focused topics

<!--
Demonstrates Forest gradient background - natural green tones.
Simply add class: bg-forest to any slide.
-->

---
layout: center
class: bg-royal
---

# 👑 Royal Theme

**Luxury • Creative • Premium**

This slide uses `class: bg-royal`

Perfect for premium products or creative showcases

<!--
Demonstrates Royal gradient background - elegant purple tones.
Simply add class: bg-royal to any slide.
-->

---
layout: center
class: bg-fire
---

# 🔥 Fire Theme

**Bold • Passionate • Dynamic**

This slide uses `class: bg-fire`

Great for high-energy or action-oriented content

<!--
Demonstrates Fire gradient background - bold red to orange tones.
Simply add class: bg-fire to any slide.
-->

---
layout: center
class: bg-tech
---

# 💻 Tech Theme

**Modern • Technical • Innovative**

This slide uses `class: bg-tech`

Perfect for technology or innovation topics

<!--
Demonstrates Tech gradient background - modern cyan to blue tones.
Simply add class: bg-tech to any slide.
-->

---
layout: two-cols
---

::title::
# Predefined Gradient Presets

::left::

## AWS Gradients

- **awsDefault**: Blue to Purple
- **awsBlue**: Dark blue to light blue
- **awsOrange**: Dark to orange
- **awsGreen**: Dark to green
- **awsPurple**: Dark blue to purple

::right::

## Theme Gradients

- **ocean**: Blue gradient 🌊
- **sunset**: Orange to pink 🌅
- **forest**: Green gradient 🌲
- **night**: Dark blue 🌙
- **fire**: Red to orange 🔥
- **royal**: Purple gradient 👑
- **tech**: Cyan to blue 💻

<!--
Lists all available gradient presets for easy selection.
-->

---

# Using Gradient Presets

Copy gradient values from `theme-aws-dark/theme.config.js`:

```css
<style>
:root {
  /* Ocean theme - professional and calm */
  --theme-gradient-cover: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-section: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
  --theme-gradient-end: linear-gradient(135deg, #0a4d68 0%, #088395 50%, #05bfdb 100%);
}
</style>
```

Or mix and match different gradients:

```css
<style>
:root {
  --theme-gradient-cover: linear-gradient(135deg, #232f3e 0%, #ff9900 100%);  /* Orange */
  --theme-gradient-section: linear-gradient(135deg, #232f3e 0%, #00a1e0 100%); /* Blue */
  --theme-gradient-end: linear-gradient(135deg, #232f3e 0%, #00d4aa 100%);    /* Green */
}
</style>
```

<!--
Demonstrates how to apply gradient presets to your presentation.
-->

---

# Other Customization Options

You can also customize:

**Typography:**
- `--theme-font-size-h1`: Main title size (default: 3rem)
- `--theme-font-size-h2`: Section title size (default: 2rem)
- `--theme-font-size-p`: Paragraph text size (default: 1.125rem)

**Colors:**
- `--aws-blue`, `--aws-orange`, `--aws-green`: Brand colors
- `--theme-text`: Main text color (default: #ffffff)

**Spacing:**
- `--theme-padding`: Slide padding (default: 2.5rem 3rem 1.5rem 3rem)
- `--theme-gap`: Column gap (default: 3rem)

See `theme-aws-dark/CUSTOMIZATION.md` for complete guide.

<!--
Overview of other customization options available in the theme.
-->
